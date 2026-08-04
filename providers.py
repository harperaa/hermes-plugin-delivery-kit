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

# Provider catalog — id, label, env var (None = manual/import only), and the
# key-retrieval instructions shown in the connect modal.
PROVIDERS = [
    {
        "id": "fireflies",
        "label": "Fireflies.ai",
        "env": "FIREFLIES_API_KEY",
        "default": True,
        "instructions": (
            "1. Sign in at app.fireflies.ai\n"
            "2. Open Settings → Developer Settings\n"
            "3. Copy your API key\n"
            "4. Paste it below and hit Save — syncing starts immediately."),
        "url": "https://app.fireflies.ai/settings",
    },
    {
        "id": "fathom",
        "label": "Fathom",
        "env": "FATHOM_API_KEY",
        "instructions": (
            "1. Sign in at fathom.video\n"
            "2. Settings → API (Team plans) → generate a key\n"
            "3. Paste it below and Save. Fathom sync lands in a coming "
            "update — the key is stored now; meanwhile use Import to paste "
            "call summaries."),
        "url": "https://fathom.video/settings",
    },
    {
        "id": "grain",
        "label": "Grain",
        "env": "GRAIN_API_KEY",
        "instructions": (
            "1. Sign in at grain.com\n"
            "2. Settings → Integrations → Personal Access Token\n"
            "3. Paste it below and Save. Grain sync lands in a coming update; "
            "meanwhile use Import."),
        "url": "https://grain.com/app/settings",
    },
    {
        "id": "tldv",
        "label": "tl;dv",
        "env": "TLDV_API_KEY",
        "instructions": (
            "1. Sign in at tldv.io\n"
            "2. Settings → API (Business plan) → create key\n"
            "3. Paste it below and Save. tl;dv sync lands in a coming update; "
            "meanwhile use Import."),
        "url": "https://tldv.io",
    },
    {
        "id": "otter",
        "label": "Otter.ai",
        "env": None,
        "instructions": (
            "Otter has no public API. Export any conversation "
            "(⋯ → Export → Text) and paste it via the Import button — "
            "analysis works identically."),
        "url": "https://otter.ai",
    },
    {
        "id": "zoom",
        "label": "Zoom",
        "env": None,
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
            "connected": bool(p["env"] and get_key(p["env"])),
            "instructions": p["instructions"], "url": p["url"],
        })
    return out


# ---------------------------------------------------------------------------
# Fireflies sync
# ---------------------------------------------------------------------------

_FF_QUERY = """
query Transcripts($limit: Int) {
  transcripts(limit: $limit) {
    id
    title
    date
    duration
    summary { overview action_items keywords }
    sentences { text speaker_name }
  }
}
"""


def fireflies_fetch(limit: int = 25) -> list[dict]:
    key = get_key("FIREFLIES_API_KEY")
    if not key:
        raise RuntimeError("Fireflies is not connected — add your API key first")
    body = json.dumps({"query": _FF_QUERY,
                       "variables": {"limit": max(1, min(limit, 50))}}).encode()
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
        transcript = "\n".join(
            f"{(s.get('speaker_name') or 'Speaker')}: {s.get('text') or ''}"
            for s in sentences)
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
        out.append({
            "externalId": str(t.get("id")),
            "title": t.get("title") or "Untitled meeting",
            "heldAt": held_at,
            "durationMin": duration,
            "transcript": transcript,
            "providerSummary": summary_text,
        })
    return out
