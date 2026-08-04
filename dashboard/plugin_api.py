"""Delivery Kit dashboard plugin — backend API routes.

Mounted at /api/plugins/delivery-kit/. Meeting sync (Fireflies GraphQL),
manual import, per-meeting analysis on the host LLM, provider key storage
straight into $HERMES_HOME/.env, and the aggregated delivery dashboard.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
except Exception:  # allows unit tests without dashboard dependencies
    class APIRouter:  # type: ignore
        def get(self, *a, **k):
            return lambda fn: fn

        def post(self, *a, **k):
            return lambda fn: fn

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code

    class BaseModel:  # type: ignore
        pass

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PKG = "hermes_plugin_pkg_delivery_kit"

if _PKG not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _PKG, str(_PLUGIN_ROOT / "__init__.py"),
        submodule_search_locations=[str(_PLUGIN_ROOT)])
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_PKG] = _mod
    _spec.loader.exec_module(_mod)

store = importlib.import_module(f"{_PKG}.store")
providers = importlib.import_module(f"{_PKG}.providers")
analysis = importlib.import_module(f"{_PKG}.analysis")

router = APIRouter()


class ConnectBody(BaseModel):
    provider: str = ""
    apiKey: str = ""


class ImportBody(BaseModel):
    title: str = ""
    transcript: str = ""
    heldAt: float = 0


class AnalyzeBody(BaseModel):
    meetingId: int = 0


def _public_state() -> dict:
    meetings = store.list_meetings()
    return {
        "providers": providers.provider_status(),
        "meetings": [
            {**m, "hasAnalysis": bool(m.get("analysis"))}
            for m in meetings
        ],
        "dashboard": analysis.dashboard_rollup(meetings),
    }


@router.get("/state")
def get_state():
    return _public_state()


@router.post("/connect")
def connect(body: ConnectBody):
    entry = next((p for p in providers.PROVIDERS
                  if p["id"] == body.provider), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown provider")
    if not entry["env"]:
        raise HTTPException(status_code=400,
                            detail=f"{entry['label']} connects via Import, not a key")
    try:
        providers.store_key(entry["env"], body.apiKey)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": _public_state()}


@router.post("/sync")
def sync():
    try:
        fetched = providers.fireflies_fetch(limit=25)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fireflies sync failed: {exc}")
    created = 0
    for t in fetched:
        _, was_new = store.upsert_meeting(
            "fireflies", t["externalId"], t["title"], t["heldAt"],
            t["durationMin"], t["transcript"], t["providerSummary"])
        created += 1 if was_new else 0
    return {"ok": True, "fetched": len(fetched), "new": created,
            "state": _public_state()}


@router.post("/import")
def manual_import(body: ImportBody):
    if not (body.title or "").strip() or not (body.transcript or "").strip():
        raise HTTPException(status_code=400,
                            detail="title and transcript are both required")
    mid, _ = store.upsert_meeting(
        "import", None, body.title, body.heldAt or None, None,
        body.transcript, "")
    return {"ok": True, "meetingId": mid, "state": _public_state()}


@router.post("/analyze")
def analyze(body: AnalyzeBody):
    if not body.meetingId:
        raise HTTPException(status_code=400, detail="meetingId required")
    try:
        result = analysis.analyze_meeting(body.meetingId)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "analysis": result, "state": _public_state()}


@router.get("/meeting/{meeting_id}")
def meeting_detail(meeting_id: int):
    m = store.get_meeting(meeting_id, with_transcript=True)
    if not m:
        raise HTTPException(status_code=404, detail="meeting not found")
    return m
