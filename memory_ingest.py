"""Capability-negotiated memory-ingest adapters.

The sync cron ships instance content (meetings, docs, briefs, insights) into
whatever memory provider the USER has connected via hermes' native memory
system (``memory.provider`` in config.yaml). Providers differ wildly in what
they can express, so adapters declare capabilities instead of pretending a
lowest common denominator:

  supports_peers     multi-actor attribution (Honcho: yes; most others: no)
  supports_sessions  grouped containers per meeting/channel/doc

No provider configured — the default on every fresh install — resolves to a
``NullAdapter`` whose ``reason`` lands in the sync journal; the cron run
succeeds untouched. A provider we have no adapter for also resolves Null
(with a reason naming it) rather than degrading silently: pretending to
support a turn-capture-only provider would drop content invisibly.

The Honcho adapter reuses the native connector's OWN config resolution
(honcho.json host blocks, ``peerName``, ``userPeerAliases``, env fallbacks),
so ingest lights up the moment a user connects Honcho — zero extra setup.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

_HONCHO_CLOUD_URL = "https://api.honcho.dev"
_SESSION_ID_MAX = 100


def _home() -> Path:
    return Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))


def read_memory_provider() -> str:
    """The user's configured memory provider, '' when none."""
    try:
        import yaml
        cfg = yaml.safe_load((_home() / "config.yaml").read_text()) or {}
        return str((cfg.get("memory") or {}).get("provider") or "").strip()
    except Exception:
        return ""


def _honcho_raw_config() -> dict:
    """Mirror the connector's file resolution: instance-local then global."""
    for path in (_home() / "honcho.json",
                 Path(os.path.expanduser("~/.honcho/config.json"))):
        try:
            return json.loads(path.read_text())
        except Exception:
            continue
    return {}


def sanitize_id(name: str, fallback: str = "unknown") -> str:
    out = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip().lower())
    out = out.strip("-")[:60]
    return out or fallback


class NullAdapter:
    """No usable provider — the cron records ``reason`` and moves on."""

    available = False
    supports_peers = False
    supports_sessions = False

    def __init__(self, reason: str):
        self.reason = reason


class HonchoAdapter:
    """Full-fidelity ingest: peers per actor, sessions per container."""

    available = True
    supports_peers = True
    supports_sessions = True

    def __init__(self, *, base_url: str, api_key: str, workspace: str,
                 user_peer: str, user_aliases: dict,
                 request_fn: Optional[Callable[..., Any]] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.workspace = workspace
        self.user_peer = user_peer
        # lowercase alias -> peer id (from the connector's userPeerAliases)
        self.user_aliases = {str(k).lower(): str(v)
                             for k, v in (user_aliases or {}).items()}
        self._request_fn = request_fn
        self._known_peers: set[str] = set()
        self._known_sessions: set[str] = set()

    # -- transport ----------------------------------------------------------
    def _request(self, method: str, path: str, body=None):
        if self._request_fn is not None:
            return self._request_fn(method, path, body)
        r = urllib.request.Request(self.base_url + path, method=method)
        if self.api_key:
            r.add_header("Authorization", "Bearer " + self.api_key)
        r.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode() if body is not None else None
        resp = urllib.request.urlopen(r, data, timeout=120)
        if resp.status not in (200, 201, 202):
            raise RuntimeError(f"{method} {path} -> {resp.status}")
        return json.loads(resp.read() or b"{}")

    # -- identity -----------------------------------------------------------
    def peer_for_actor(self, display_name: str) -> str:
        """Map a display name (transcript speaker, channel handle) to a peer.

        The user's own identity wins first: explicit ``userPeerAliases``
        entries, an exact match on the configured peer name, or a first-name
        match ("Allen Harper" -> peer "allen"). Everyone else gets a
        sanitized name peer.
        """
        clean = (display_name or "").strip()
        low = clean.lower()
        if low in self.user_aliases:
            return self.user_aliases[low]
        sid = sanitize_id(clean, "unknown-speaker")
        if sid == self.user_peer:
            return self.user_peer
        first = low.split()[0] if low.split() else ""
        if first and sanitize_id(first, "") == self.user_peer:
            return self.user_peer
        return sid

    # -- writes -------------------------------------------------------------
    def ensure_peer(self, peer_id: str) -> None:
        if peer_id in self._known_peers:
            return
        self._request("POST", f"/v3/workspaces/{self.workspace}/peers",
                      {"name": peer_id})
        self._known_peers.add(peer_id)

    def ensure_session(self, session_id: str) -> str:
        session_id = session_id[:_SESSION_ID_MAX]
        if session_id not in self._known_sessions:
            self._request("POST", f"/v3/workspaces/{self.workspace}/sessions",
                          {"name": session_id})
            self._known_sessions.add(session_id)
        return session_id

    def post_messages(self, session_id: str, messages, batch: int = 20,
                      max_chars: int = 18000) -> None:
        """messages = iterable of (peer_id, content)."""
        msgs = [{"peer_id": p, "content": c[:max_chars]}
                for p, c in messages if c and c.strip()]
        for i in range(0, len(msgs), batch):
            self._request(
                "POST",
                f"/v3/workspaces/{self.workspace}/sessions/{session_id}/messages",
                {"messages": msgs[i:i + batch]})


def _build_honcho_adapter(request_fn=None):
    raw = _honcho_raw_config()
    host = os.environ.get("HERMES_HONCHO_HOST", "").strip() or "hermes"
    block = (raw.get("hosts") or {}).get(host, {})
    api_key = (block.get("apiKey") or raw.get("apiKey")
               or os.environ.get("HONCHO_API_KEY", ""))
    base_url = (raw.get("baseUrl") or block.get("baseUrl")
                or os.environ.get("HONCHO_BASE_URL", "")).strip()
    if not base_url:
        if not api_key:
            return NullAdapter("honcho selected but no baseUrl/apiKey configured")
        base_url = _HONCHO_CLOUD_URL
    workspace = block.get("workspace") or raw.get("workspace") or host
    user_peer = sanitize_id(block.get("peerName") or raw.get("peerName")
                            or "user", "user")
    aliases = {}
    for src in (raw.get("userPeerAliases"), block.get("userPeerAliases")):
        if isinstance(src, dict):
            aliases.update(src)
    return HonchoAdapter(base_url=base_url, api_key=api_key,
                         workspace=workspace, user_peer=user_peer,
                         user_aliases=aliases, request_fn=request_fn)


def resolve_adapter(request_fn=None):
    """Detect the configured provider and return its ingest adapter.

    Never raises: any resolution problem returns a NullAdapter whose reason
    explains itself in the sync journal.
    """
    try:
        provider = read_memory_provider()
        if not provider:
            return NullAdapter("no memory provider configured")
        if provider == "honcho":
            return _build_honcho_adapter(request_fn)
        return NullAdapter(
            f"memory provider '{provider}' has no ingest adapter yet")
    except Exception as exc:  # pragma: no cover - absolute backstop
        return NullAdapter(f"adapter resolution failed: {str(exc)[:120]}")
