"""delivery-kit meeting-transcript providers.

Fireflies.ai is the default (GraphQL, Bearer key). Other tools connect via
their own keys where an API exists, or through manual transcript import —
every provider card in the UI carries retrieval instructions and, when the
provider has a usable API, a key field that stores straight into the env.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Optional

FIREFLIES_URL = "https://api.fireflies.ai/graphql"

# Provider catalog — id, label, env var (None = manual/import only),
# canSync (a live fetcher exists below), and the key-retrieval instructions
# shown in the connect modal. API facts verified 2026-08-04.
PROVIDERS = [
    {
        "id": "fireflies",
        "label": "Fireflies.ai",
        "env": "FIREFLIES_API_KEY",
        "default": True,
        "canSync": True,
        "instructions": (
            "1. Sign in at app.fireflies.ai\n"
            "2. Open Settings → Developer Settings\n"
            "3. Copy your API key\n"
            "4. Paste it below and hit Save — then Sync pulls your meetings."),
        "url": "https://app.fireflies.ai/settings",
    },
    {
        "id": "fathom",
        "label": "Fathom",
        "env": "FATHOM_API_KEY",
        "canSync": True,
        "instructions": (
            "1. Sign in at fathom.video\n"
            "2. Settings → API → generate an API key\n"
            "3. Paste it below and Save — then Sync pulls your meetings "
            "(transcripts included, 60 calls/min limit)."),
        "url": "https://fathom.video/settings",
    },
    {
        "id": "grain",
        "label": "Grain",
        "env": "GRAIN_API_KEY",
        "canSync": True,
        "instructions": (
            "1. Sign in at grain.com\n"
            "2. Settings → Integrations → Public API → generate a token\n"
            "3. Paste it below and Save — then Sync pulls your recordings "
            "and transcripts."),
        "url": "https://grain.com/app/settings",
    },
    {
        "id": "tldv",
        "label": "tl;dv",
        "env": "TLDV_API_KEY",
        "canSync": True,
        "instructions": (
            "1. Sign in at tldv.io\n"
            "2. Settings → API (Business plan) → create an API key\n"
            "3. Paste it below and Save — then Sync pulls your meetings and "
            "transcripts. Note: API export requires the organizer's plan to "
            "allow it."),
        "url": "https://tldv.io",
    },
    {
        "id": "plaud",
        "label": "Plaud",
        "env": "PLAUD_API_KEY",
        "canSync": False,
        "instructions": (
            "Plaud (Note/NotePin recorders) now has a developer platform: "
            "docs.plaud.ai — transcripts, summaries, and metadata as JSON.\n"
            "1. Request API access at docs.plaud.ai (developer platform)\n"
            "2. Paste your key below and Save — direct sync lands in a "
            "coming update.\n"
            "Today: route Plaud → Zapier → webhook, or export a transcript "
            "from the Plaud app and paste it via Import."),
        "url": "https://docs.plaud.ai/overview",
    },
    {
        "id": "avoma",
        "label": "Avoma",
        "env": "AVOMA_API_KEY",
        "canSync": False,
        "instructions": (
            "1. Sign in at avoma.com\n"
            "2. Settings → API → generate a key (dev.avoma.com has the docs)\n"
            "3. Paste it below and Save — direct sync lands in a coming "
            "update; meanwhile use Import."),
        "url": "https://help.avoma.com/api-documentation",
    },
    {
        "id": "otter",
        "label": "Otter.ai",
        "env": None,
        "canSync": False,
        "instructions": (
            "Otter's public API is Enterprise-only (enabled by your Otter "
            "account manager). For everyone else: export any conversation "
            "(⋯ → Export → Text) and paste it via Import — analysis works "
            "identically."),
        "url": "https://otter.ai",
    },
    {
        "id": "readai",
        "label": "Read.ai",
        "env": None,
        "canSync": False,
        "instructions": (
            "Read.ai integrates via webhooks/Zapier rather than a pull API. "
            "Export or copy the meeting report and paste it via Import."),
        "url": "https://www.read.ai",
    },
    {
        "id": "granola",
        "label": "Granola",
        "env": None,
        "canSync": False,
        "instructions": (
            "Granola is local-first with no public API. Copy a note/transcript "
            "from the app and paste it via Import."),
        "url": "https://www.granola.ai",
    },
    {
        "id": "zoom",
        "label": "Zoom",
        "env": None,
        "canSync": False,
        "instructions": (
            "Zoom cloud recordings include a transcript (.vtt). Download it "
            "from the recording page and paste via Import — analysis works "
            "identically."),
        "url": "https://zoom.us/recording",
    },
]


def _env_path() -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    root = Path(home) if home else Path.home() / ".hermes"
    return root / ".env"


def get_key(env_var: str) -> str:
    v = (os.environ.get(env_var) or "").strip()
    if v:
        return v
    try:
        for line in _env_path().read_text().splitlines():
            if line.strip().startswith(env_var + "="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def store_key(env_var: str, value: str) -> None:
    """Persist a provider key into $HERMES_HOME/.env (replace-not-duplicate)
    and the process env so it applies without a restart."""
    value = value.strip()
    if not value or "\n" in value:
        raise ValueError("key must be a single non-empty line")
    allowed = {p["env"] for p in PROVIDERS if p["env"]}
    if env_var not in allowed:
        raise ValueError(f"unknown provider env var: {env_var}")
    path = _env_path()
    lines = []
    try:
        lines = [l for l in path.read_text().splitlines()
                 if not l.strip().startswith(env_var + "=")]
    except FileNotFoundError:
        pass
    lines.append(f"{env_var}={value}")
    tmp = path.with_suffix(".dk-tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.environ[env_var] = value


def provider_status() -> list[dict]:
    out = []
    for p in PROVIDERS:
        out.append({
            "id": p["id"], "label": p["label"], "env": p["env"],
            "default": bool(p.get("default")),
            "canSync": bool(p.get("canSync")),
            "connected": bool(p["env"] and get_key(p["env"])),
            "instructions": p["instructions"], "url": p["url"],
        })
    return out


# ---------------------------------------------------------------------------
# Transcript timestamps — providers report sentence offsets in seconds or ms;
# lines render as "[M:SS] Speaker: text" so the dashboard's evidence modal
# (and the analyst) can see WHEN something was said.
# ---------------------------------------------------------------------------

def _fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s2 = divmod(rem, 60)
    return f"[{h}:{m:02d}:{s2:02d}]" if h else f"[{m}:{s2:02d}]"


def _seg_ts(seg: dict) -> Optional[float]:
    for k in ("start_time", "startTime", "start", "offset", "timestamp"):
        v = seg.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _stamp_lines(rows: list, duration_min: Optional[float] = None) -> str:
    """rows = [(ts_or_None, speaker, text)] -> transcript text.

    Offsets whose max exceeds the meeting length (or a day, when duration is
    unknown) are treated as milliseconds — no per-provider unit guessing.
    """
    vals = [t for t, _, _ in rows if t is not None]
    scale = 1.0
    if vals:
        mx = max(vals)
        limit = duration_min * 60 * 3 if duration_min else 86400.0
        if mx > max(limit, 60.0):
            scale = 0.001
    lines = []
    for t, speaker, text in rows:
        prefix = _fmt_ts(t * scale) + " " if t is not None else ""
        lines.append(f"{prefix}{speaker}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fireflies sync
# ---------------------------------------------------------------------------

_FF_QUERY = """
query Transcripts($limit: Int, $skip: Int, $fromDate: DateTime, $toDate: DateTime) {
  transcripts(limit: $limit, skip: $skip, fromDate: $fromDate, toDate: $toDate) {
    id
    title
    date
    duration
    summary { overview action_items keywords }
    sentences { text speaker_name start_time }
  }
}
"""


def _epoch_to_iso(epoch) -> Optional[str]:
    if not epoch:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fireflies_fetch(limit: int = 25, skip: int = 0,
                    from_epoch=None, to_epoch=None) -> list[dict]:
    key = get_key("FIREFLIES_API_KEY")
    if not key:
        raise RuntimeError("Fireflies is not connected — add your API key first")
    variables = {"limit": max(1, min(limit, 50)), "skip": max(0, int(skip))}
    if from_epoch:
        variables["fromDate"] = _epoch_to_iso(from_epoch)
    if to_epoch:
        variables["toDate"] = _epoch_to_iso(to_epoch)
    body = json.dumps({"query": _FF_QUERY,
                       "variables": variables}).encode()
    req = urllib.request.Request(
        FIREFLIES_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        msg = payload["errors"][0].get("message", "Fireflies API error")
        raise RuntimeError(f"Fireflies: {msg}")
    out = []
    for t in (payload.get("data") or {}).get("transcripts") or []:
        sentences = t.get("sentences") or []
        summary = t.get("summary") or {}
        summary_text = "\n".join(filter(None, [
            summary.get("overview") or "",
            ("Action items: " + str(summary.get("action_items")))
            if summary.get("action_items") else "",
        ]))
        held_at = None
        if t.get("date"):
            try:
                held_at = float(t["date"]) / 1000.0
            except (TypeError, ValueError):
                pass
        duration = None
        if t.get("duration") is not None:
            try:
                duration = float(t["duration"])
            except (TypeError, ValueError):
                pass
        transcript = _stamp_lines(
            [(_seg_ts(s), s.get("speaker_name") or "Speaker", s.get("text") or "")
             for s in sentences], duration)
        out.append({
            "externalId": str(t.get("id")),
            "title": t.get("title") or "Untitled meeting",
            "heldAt": held_at,
            "durationMin": duration,
            "transcript": transcript,
            "providerSummary": summary_text,
        })
    return out


def _http_json(url: str, headers: dict, method: str = "GET",
               body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          **headers})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _iso_to_epoch(value) -> Optional[float]:
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fathom sync — GET api.fathom.ai/external/v1/meetings?include_transcript=true
# (X-Api-Key header; verified 2026-08-04)
# ---------------------------------------------------------------------------

def fathom_fetch(limit: int = 15) -> list[dict]:
    key = get_key("FATHOM_API_KEY")
    if not key:
        raise RuntimeError("Fathom is not connected — add your API key first")
    payload = _http_json(
        "https://api.fathom.ai/external/v1/meetings"
        f"?include_transcript=true&limit={max(1, min(limit, 25))}",
        {"X-Api-Key": key})
    out = []
    for m in (payload.get("items") or [])[:limit]:
        rows = []
        for seg in m.get("transcript") or []:
            speaker = seg.get("speaker") or {}
            name = (speaker.get("display_name") if isinstance(speaker, dict)
                    else str(speaker)) or "Speaker"
            rows.append((_seg_ts(seg), name, seg.get("text") or ""))
        start = _iso_to_epoch(m.get("recording_start_time")
                              or m.get("scheduled_start_time"))
        end = _iso_to_epoch(m.get("recording_end_time")
                            or m.get("scheduled_end_time"))
        duration = (end - start) / 60.0 if start and end and end > start else None
        transcript = _stamp_lines(rows, duration)
        out.append({
            "externalId": str(m.get("id") or m.get("recording_id")
                              or m.get("url") or m.get("title")),
            "title": m.get("title") or m.get("meeting_title") or "Untitled meeting",
            "heldAt": start,
            "durationMin": duration,
            "transcript": transcript,
            "providerSummary": str(m.get("summary") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# Grain sync — POST /_/public-api/v2/recordings (list) then GET
# /recordings/:id/transcript (Bearer + Public-Api-Version; verified 2026-08-04)
# ---------------------------------------------------------------------------

_GRAIN_BASE = "https://api.grain.com/_/public-api"
_GRAIN_HEADERS = lambda key: {"Authorization": f"Bearer {key}",
                              "Public-Api-Version": "2025-10-31"}


def grain_fetch(limit: int = 10) -> list[dict]:
    key = get_key("GRAIN_API_KEY")
    if not key:
        raise RuntimeError("Grain is not connected — add your token first")
    listing = _http_json(f"{_GRAIN_BASE}/v2/recordings",
                         _GRAIN_HEADERS(key), method="POST", body={})
    recs = listing.get("recordings") or listing.get("items") or []
    out = []
    for r in recs[:max(1, min(limit, 15))]:
        rid = r.get("id")
        transcript = ""
        try:
            t = _http_json(f"{_GRAIN_BASE}/v2/recordings/{rid}/transcript",
                           _GRAIN_HEADERS(key))
            segs = t.get("transcript") or t.get("segments") or t or []
            if isinstance(segs, list):
                transcript = _stamp_lines(
                    [(_seg_ts(seg), seg.get("speaker") or "Speaker",
                      seg.get("text") or "")
                     for seg in segs if isinstance(seg, dict)])
        except Exception:
            pass
        out.append({
            "externalId": str(rid),
            "title": r.get("title") or "Untitled recording",
            "heldAt": _iso_to_epoch(r.get("start_datetime")),
            "durationMin": None,
            "transcript": transcript,
            "providerSummary": str(r.get("summary") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# tl;dv sync — GET pasta.tldv.io/v1alpha1/meetings then /meetings/{id}/
# transcript (x-api-key header; verified 2026-08-04)
# ---------------------------------------------------------------------------

_TLDV_BASE = "https://pasta.tldv.io/v1alpha1"


def tldv_fetch(limit: int = 10) -> list[dict]:
    key = get_key("TLDV_API_KEY")
    if not key:
        raise RuntimeError("tl;dv is not connected — add your API key first")
    listing = _http_json(f"{_TLDV_BASE}/meetings", {"x-api-key": key})
    meetings = listing.get("results") or listing.get("meetings") or []
    out = []
    for m in meetings[:max(1, min(limit, 15))]:
        mid = m.get("id")
        transcript = ""
        try:
            t = _http_json(f"{_TLDV_BASE}/meetings/{mid}/transcript",
                           {"x-api-key": key})
            segs = t.get("data") or t.get("transcript") or []
            if isinstance(segs, list):
                transcript = _stamp_lines(
                    [(_seg_ts(seg), seg.get("speaker") or "Speaker",
                      seg.get("text") or "")
                     for seg in segs if isinstance(seg, dict)],
                    m.get("duration"))
        except Exception:
            pass
        out.append({
            "externalId": str(mid),
            "title": m.get("name") or "Untitled meeting",
            "heldAt": _iso_to_epoch(m.get("happenedAt")),
            "durationMin": m.get("duration"),
            "transcript": transcript,
            "providerSummary": "",
        })
    return out


SYNCERS = {
    "fireflies": fireflies_fetch,
    "fathom": fathom_fetch,
    "grain": grain_fetch,
    "tldv": tldv_fetch,
}


def sync_provider(provider_id: str, limit: int = 25) -> list[dict]:
    fn = SYNCERS.get(provider_id)
    if fn is None:
        raise RuntimeError(f"{provider_id} has no direct sync yet — use Import")
    return fn(limit)


def fireflies_fetch_window(from_epoch=None, to_epoch=None,
                           max_pages: int = 20) -> list[dict]:
    """Page through a date window (skip-based, 50/page)."""
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(max_pages):
        batch = fireflies_fetch(limit=50, skip=page * 50,
                                from_epoch=from_epoch, to_epoch=to_epoch)
        fresh = [t for t in batch if t["externalId"] not in seen]
        for t in fresh:
            seen.add(t["externalId"])
        out.extend(fresh)
        if len(batch) < 50:
            break
    return out
