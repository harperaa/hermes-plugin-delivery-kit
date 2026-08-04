"""delivery-kit storage — meetings + analyses in sqlite under plugins-data."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


def data_dir() -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    root = Path(home) if home else Path.home() / ".hermes"
    d = root / "plugins-data" / "delivery-kit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "meetings.db")
    conn.execute("""
        create table if not exists meetings (
            id integer primary key autoincrement,
            provider text not null,
            external_id text,
            title text not null,
            held_at real,
            duration_min real,
            transcript text default '',
            provider_summary text default '',
            analysis text default '',
            created_at real not null
        )""")
    conn.execute("""
        create unique index if not exists idx_provider_ext
        on meetings(provider, external_id)""")
    return conn


def upsert_meeting(provider: str, external_id: Optional[str], title: str,
                   held_at: Optional[float], duration_min: Optional[float],
                   transcript: str, provider_summary: str = "") -> tuple[int, bool]:
    """Insert a meeting; skip when (provider, external_id) already exists.
    Returns (id, created)."""
    conn = connect()
    try:
        if external_id:
            row = conn.execute(
                "select id from meetings where provider=? and external_id=?",
                (provider, external_id)).fetchone()
            if row:
                return row[0], False
        with conn:
            cur = conn.execute(
                "insert into meetings (provider, external_id, title, held_at, "
                "duration_min, transcript, provider_summary, created_at) "
                "values (?,?,?,?,?,?,?,?)",
                (provider, external_id, title.strip()[:300], held_at,
                 duration_min, transcript[:400_000], provider_summary[:20_000],
                 time.time()))
            return cur.lastrowid, True
    finally:
        conn.close()


def save_analysis(meeting_id: int, analysis: dict) -> None:
    conn = connect()
    with conn:
        conn.execute("update meetings set analysis=? where id=?",
                     (json.dumps(analysis), meeting_id))
    conn.close()


def _row_to_dict(r, with_transcript: bool = False) -> dict:
    d = {
        "id": r[0], "provider": r[1], "externalId": r[2], "title": r[3],
        "heldAt": r[4], "durationMin": r[5],
        "providerSummary": r[7], "createdAt": r[9],
        "analysis": json.loads(r[8]) if r[8] else None,
    }
    if with_transcript:
        d["transcript"] = r[6]
    return d


_COLS = ("id, provider, external_id, title, held_at, duration_min, "
         "transcript, provider_summary, analysis, created_at")


def list_meetings(limit: int = 200) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        f"select {_COLS} from meetings "
        "order by coalesce(held_at, created_at) desc limit ?", (limit,)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_meeting(meeting_id: int, with_transcript: bool = True) -> Optional[dict]:
    conn = connect()
    r = conn.execute(f"select {_COLS} from meetings where id=?",
                     (meeting_id,)).fetchone()
    conn.close()
    return _row_to_dict(r, with_transcript) if r else None


def search_meetings(query: str = "", limit: int = 10) -> list[dict]:
    """Substring search over titles, transcripts, and analyses (chat tool)."""
    conn = connect()
    like = f"%{(query or '').strip()}%"
    rows = conn.execute(
        f"select {_COLS} from meetings where title like ? or transcript like ? "
        "or analysis like ? order by coalesce(held_at, created_at) desc limit ?",
        (like, like, like, max(1, min(int(limit), 50)))).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]
