"""Instance-content ingest into the connected memory provider.

Sources (each skipped silently when its plugin/data is absent):
  meetings   delivery-kit meetings.db — transcripts split by speaker, each
             speaker a peer (when the adapter supports peers), the user's
             own lines mapped to their configured peer; summary + analysis
             attributed to the user. Sessions ``meet-<id>``. Analyses that
             arrive after the meeting (the cron caps auto-analyze per run)
             ship as follow-ups.
  docs       acvc company-context.md and offer-doc.md — re-sent on change
             (hash-tracked), sessions named for the doc.
  briefs     daily-brief markdown files, one session per brief.
  insights   youtube-insights — attributed to a peer per SOURCE CHANNEL in
             sessions ``yt-<channel>``; incremental via a (first_seen, id)
             watermark.

State lives in $HERMES_HOME/memory-ingest-state.json; advancement happens
only after a successful write, so a failed run retries next hour. A legacy
honcho-import-state.json (the hand-run historical import) migrates in place
so existing installs never re-send.

Without peer support the same content flattens: speaker names inline in the
text, everything written under the user's single identity.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

try:  # loaded as a plugin package by the cron script
    from . import memory_ingest as _mi
except ImportError:  # loaded top-level (tests, tooling)
    import memory_ingest as _mi

CHUNK = 18000
MEETING_SESSION_PREFIX = "meet-"
STATE_NAME = "memory-ingest-state.json"
LEGACY_STATE_NAME = "honcho-import-state.json"


def _home() -> Path:
    return Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))


def _state_path() -> Path:
    return _home() / STATE_NAME


def load_state() -> dict:
    p = _state_path()
    try:
        return json.loads(p.read_text())
    except Exception:
        pass
    legacy = _home() / LEGACY_STATE_NAME
    try:
        st = json.loads(legacy.read_text())
        p.write_text(json.dumps(st))
        return st
    except Exception:
        return {}


def save_state(st: dict) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    os.replace(tmp, p)


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _chunks(text: str, prefix: str = ""):
    text = text or ""
    return [(prefix + text[i:i + CHUNK]) for i in range(0, len(text), CHUNK)]


# --- transcript parsing -----------------------------------------------------

_LINE_RE = re.compile(r"^\[[\d:]+\]\s*([^:]{1,60}):\s*(.*)$")


def parse_transcript(transcript: str):
    """``[m:ss] Speaker: text`` lines -> [(speaker_display, joined turn)]."""
    turns = []
    for line in (transcript or "").splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            if turns and line.strip():
                turns[-1][1].append(line.strip())
            continue
        speaker, text = m.group(1).strip(), m.group(2).strip()
        if turns and turns[-1][0] == speaker:
            turns[-1][1].append(text)
        else:
            turns.append([speaker, [text]])
    return [(s, " ".join(parts)) for s, parts in turns if any(parts)]


# --- sources ----------------------------------------------------------------

def _ingest_meetings(adapter, st: dict) -> int:
    db = _home() / "plugins-data" / "delivery-kit" / "meetings.db"
    if not db.exists():
        return 0
    done = set(st.get("meeting_ids", []))
    con = _ro(db)
    rows = con.execute(
        "select id, title, held_at, provider_summary, analysis, transcript "
        "from meetings order by id").fetchall()
    con.close()
    n = 0
    user = getattr(adapter, "user_peer", "user")
    for mid, title, held_at, summary, analysis, transcript in rows:
        if mid in done:
            continue
        session = adapter.ensure_session(f"{MEETING_SESSION_PREFIX}{mid}")
        head = f"Meeting: {title or 'untitled'} (held {held_at})"
        msgs = []
        if summary:
            msgs.append((user, f"{head}\n\nSummary:\n{summary}"))
        for c in _chunks(analysis or ""):
            msgs.append((user, f"{head}\n\nAnalysis:\n{c}"))
        turns = parse_transcript(transcript) if adapter.supports_peers else []
        if turns:
            for speaker, text in turns:
                peer = adapter.peer_for_actor(speaker)
                adapter.ensure_peer(peer)
                for c in _chunks(text):
                    msgs.append((peer, c))
        else:
            for c in _chunks(transcript or ""):
                msgs.append((user, f"{head}\n\nTranscript excerpt:\n{c}"))
        adapter.ensure_peer(user)
        adapter.post_messages(session, msgs or [(user, head)])
        done.add(mid)
        st["meeting_ids"] = sorted(done)
        if not analysis:
            st.setdefault("meetings_awaiting_analysis", []).append(mid)
        save_state(st)
        n += 1
    # analyses generated after the meeting was ingested
    waiting = [m for m in st.get("meetings_awaiting_analysis", [])
               if m in done]
    if waiting:
        con = _ro(db)
        rows = con.execute(
            "select id, title, held_at, analysis from meetings "
            f"where id in ({','.join('?' * len(waiting))})",
            waiting).fetchall()
        con.close()
        for mid, title, held_at, analysis in rows:
            if not analysis:
                continue
            head = f"Meeting: {title or 'untitled'} (held {held_at})"
            adapter.post_messages(
                f"{MEETING_SESSION_PREFIX}{mid}",
                [(user, f"{head}\n\nAnalysis:\n{c}")
                 for c in _chunks(analysis)])
            st["meetings_awaiting_analysis"].remove(mid)
            save_state(st)
            n += 1
    return n


def _ingest_doc(adapter, st: dict, key: str, path: Path, session: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text(errors="replace")
    h = hashlib.sha256(text.encode()).hexdigest()
    if not text.strip() or st.get("doc_hashes", {}).get(key) == h:
        return 0
    user = getattr(adapter, "user_peer", "user")
    adapter.ensure_peer(user)
    session = adapter.ensure_session(session)
    stamp = time.strftime("%Y-%m-%d")
    adapter.post_messages(
        session,
        [(user, c) for c in _chunks(text, f"[{key} as of {stamp}]\n")])
    st.setdefault("doc_hashes", {})[key] = h
    save_state(st)
    return 1


def _ingest_briefs(adapter, st: dict) -> int:
    d = _home() / "plugins-data" / "daily-brief" / "briefs"
    if not d.is_dir():
        return 0
    done = set(st.get("brief_files", []))
    user = getattr(adapter, "user_peer", "user")
    n = 0
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md") or f in done:
            continue
        text = (d / f).read_text(errors="replace")
        session = adapter.ensure_session("brief-" + f[:10])
        adapter.ensure_peer(user)
        adapter.post_messages(
            session,
            [(user, c) for c in _chunks(text, f"[daily intel brief {f}]\n")])
        done.add(f)
        st["brief_files"] = sorted(done)
        save_state(st)
        n += 1
    return n


def _ingest_insights(adapter, st: dict, limit: int = 1000) -> int:
    db = _home() / "plugins-data" / "youtube-insights" / "data.db"
    if not db.exists():
        return 0
    wm_seen = st.get("insight_wm_seen", "")
    wm_id = st.get("insight_wm_id", "")
    con = _ro(db)
    try:
        rows = con.execute(
            "select i.id, i.text, i.detail, i.category, i.first_seen, "
            "  (select v.channel_handle from insight_sources s "
            "   join videos v on v.video_id = s.video_id "
            "   where s.insight_id = i.id limit 1) as channel "
            "from insights i "
            "where (i.first_seen > ?) or (i.first_seen = ? and i.id > ?) "
            "order by i.first_seen, i.id limit ?",
            (wm_seen, wm_seen, wm_id, limit)).fetchall()
    except sqlite3.Error:
        con.close()
        return 0
    con.close()
    if not rows:
        return 0
    user = getattr(adapter, "user_peer", "user")
    by_channel: dict[str, list] = {}
    for _iid, text, detail, category, _seen, channel in rows:
        body = f"[youtube insight | {category or 'general'}]\n{text or ''}"
        if detail:
            body += f"\n\n{detail}"
        peer = _mi.sanitize_id(channel or "", "unknown-channel") \
            if adapter.supports_peers else user
        by_channel.setdefault(peer, []).append(body)
    for peer, bodies in by_channel.items():
        adapter.ensure_peer(peer)
        session = adapter.ensure_session(
            f"yt-{peer}" if adapter.supports_peers else "youtube-insights")
        adapter.post_messages(session, [(peer, b) for b in bodies])
    st["insight_wm_seen"] = rows[-1][4]
    st["insight_wm_id"] = rows[-1][0]
    save_state(st)
    return len(rows)


def run_ingest(adapter) -> dict:
    """Run every source against ``adapter``; per-source errors are isolated."""
    st = load_state()
    out: dict = {}
    acvc = _home() / "plugins-data" / "ai-cyber-value-creator"
    od = _home() / "plugins-data" / "offer-doc"
    for name, fn in (
        ("meetings", lambda: _ingest_meetings(adapter, st)),
        ("company_context", lambda: _ingest_doc(
            adapter, st, "company-context",
            acvc / "company-context.md", "company-context")),
        ("offer_doc", lambda: _ingest_doc(
            adapter, st, "offer-doc", od / "offer-doc.md", "offer-doc")),
        ("briefs", lambda: _ingest_briefs(adapter, st)),
        ("insights", lambda: _ingest_insights(adapter, st)),
    ):
        try:
            out[name] = fn()
        except Exception as exc:
            out[name] = f"error: {str(exc)[:150]}"
    return out
