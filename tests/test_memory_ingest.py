"""Memory-ingest adapter layer + content collectors."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory_ingest as mi
import content_ingest as ci


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


class FakeAdapter:
    """Records every call; honcho-shaped capabilities."""

    available = True
    supports_peers = True
    supports_sessions = True
    user_peer = "allen"

    def __init__(self):
        self.peers, self.sessions, self.posts = set(), set(), []

    def peer_for_actor(self, name):
        low = (name or "").strip().lower()
        if "allen" in low:
            return "allen"
        return mi.sanitize_id(name, "unknown-speaker")

    def ensure_peer(self, p):
        self.peers.add(p)

    def ensure_session(self, s):
        self.sessions.add(s)
        return s

    def post_messages(self, session, msgs, **kw):
        self.posts.append((session, list(msgs)))


# --- resolution -------------------------------------------------------------

def test_no_provider_resolves_null(home):
    a = mi.resolve_adapter()
    assert not a.available
    assert "no memory provider" in a.reason


def test_unknown_provider_resolves_null_with_name(home):
    (home / "config.yaml").write_text("memory:\n  provider: mem0\n")
    a = mi.resolve_adapter()
    assert not a.available
    assert "mem0" in a.reason


def test_honcho_without_config_resolves_null(home):
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    a = mi.resolve_adapter()
    assert not a.available
    assert "honcho" in a.reason


def test_honcho_selfhosted_resolves_adapter(home):
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    (home / "honcho.json").write_text(json.dumps({
        "baseUrl": "http://honcho-api.railway.internal:8000",
        "hosts": {"hermes": {"apiKey": "jwt", "workspace": "hermes",
                             "peerName": "allen",
                             "userPeerAliases": {"dr harper": "allen"}}},
    }))
    a = mi.resolve_adapter()
    assert a.available and a.supports_peers
    assert a.workspace == "hermes" and a.user_peer == "allen"
    assert a.peer_for_actor("Dr Harper") == "allen"
    assert a.peer_for_actor("Allen Harper") == "allen"      # first-name match
    assert a.peer_for_actor("Steve Brodson") == "steve-brodson"


def test_honcho_cloud_defaults_base_url(home):
    (home / "config.yaml").write_text("memory:\n  provider: honcho\n")
    (home / "honcho.json").write_text(json.dumps(
        {"hosts": {"hermes": {"apiKey": "cloud-key"}}}))
    a = mi.resolve_adapter()
    assert a.available and a.base_url == "https://api.honcho.dev"
    assert a.workspace == "hermes"


def test_resolution_never_raises(home):
    (home / "config.yaml").write_text(":\tnot yaml [")
    a = mi.resolve_adapter()
    assert not a.available


# --- transcript parsing -----------------------------------------------------

def test_parse_transcript_groups_consecutive_turns():
    t = ("[0:14] Allen Harper: How's it going?\n"
         "[0:16] Steve Brodson: Good.\n"
         "[0:17] Steve Brodson: Projects going well.\n"
         "continuation line\n")
    turns = ci.parse_transcript(t)
    assert turns == [
        ("Allen Harper", "How's it going?"),
        ("Steve Brodson", "Good. Projects going well. continuation line"),
    ]


def test_parse_transcript_empty():
    assert ci.parse_transcript("") == []
    assert ci.parse_transcript(None) == []


# --- meetings ---------------------------------------------------------------

def _make_meetings_db(home, rows):
    d = home / "plugins-data" / "delivery-kit"
    d.mkdir(parents=True)
    con = sqlite3.connect(d / "meetings.db")
    con.execute("create table meetings (id integer primary key, provider text,"
                " external_id text, title text, held_at text, duration_min int,"
                " transcript text, provider_summary text, analysis text,"
                " created_at text)")
    for r in rows:
        con.execute("insert into meetings (id, title, held_at, transcript,"
                    " provider_summary, analysis) values (?,?,?,?,?,?)", r)
    con.commit()
    con.close()


def test_meetings_speaker_attribution_and_late_analysis(home):
    _make_meetings_db(home, [
        (1, "Check-in", "2026-08-01",
         "[0:01] Allen Harper: Hi.\n[0:02] Gav M: My retainer is 6k.",
         "sum", None),
    ])
    a = FakeAdapter()
    st = {}
    assert ci._ingest_meetings(a, st) == 1
    assert "meet-1" in a.sessions
    assert {"allen", "gav-m"} <= a.peers
    flat = [m for _, msgs in a.posts for m in msgs]
    assert ("gav-m", "My retainer is 6k.") in flat
    assert st["meetings_awaiting_analysis"] == [1]
    # analysis arrives later -> follow-up ships once
    con = sqlite3.connect(home / "plugins-data/delivery-kit/meetings.db")
    con.execute("update meetings set analysis='great progress' where id=1")
    con.commit()
    con.close()
    a2 = FakeAdapter()
    assert ci._ingest_meetings(a2, st) == 1
    assert st["meetings_awaiting_analysis"] == []
    flat2 = [m for _, msgs in a2.posts for m in msgs]
    assert any("great progress" in c for _, c in flat2)
    # nothing further to do
    assert ci._ingest_meetings(FakeAdapter(), st) == 0


def test_meetings_flatten_without_peer_support(home):
    _make_meetings_db(home, [
        (1, "Check-in", "2026-08-01",
         "[0:01] Gav M: My retainer is 6k.", None, "an"),
    ])
    a = FakeAdapter()
    a.supports_peers = False
    st = {}
    ci._ingest_meetings(a, st)
    flat = [m for _, msgs in a.posts for m in msgs]
    assert all(p == "allen" for p, _ in flat)
    assert any("Transcript excerpt" in c for _, c in flat)


# --- docs / briefs / insights ----------------------------------------------

def test_doc_hash_tracking(home):
    p = home / "plugins-data" / "ai-cyber-value-creator"
    p.mkdir(parents=True)
    (p / "company-context.md").write_text("ICP: builders")
    a = FakeAdapter()
    st = {}
    assert ci._ingest_doc(a, st, "company-context",
                          p / "company-context.md", "company-context") == 1
    assert ci._ingest_doc(a, st, "company-context",
                          p / "company-context.md", "company-context") == 0
    (p / "company-context.md").write_text("ICP: builders v2")
    assert ci._ingest_doc(a, st, "company-context",
                          p / "company-context.md", "company-context") == 1


def test_insights_per_channel_with_watermark(home):
    d = home / "plugins-data" / "youtube-insights"
    d.mkdir(parents=True)
    con = sqlite3.connect(d / "data.db")
    con.execute("create table insights (id text primary key, text text,"
                " detail text, category text, source_count int,"
                " first_seen text, last_seen text)")
    con.execute("create table insight_sources (insight_id text,"
                " video_id text, context text, timestamp_ref text,"
                " source_url text, added_at text)")
    con.execute("create table videos (video_id text primary key,"
                " channel_handle text)")
    con.execute("insert into videos values ('v1', 'ColeMedin')")
    con.execute("insert into insights (id, text, category, first_seen)"
                " values ('a', 'MCP is big', 'trend', '2026-01-01')")
    con.execute("insert into insight_sources (insight_id, video_id)"
                " values ('a', 'v1')")
    con.commit()
    con.close()
    a = FakeAdapter()
    st = {}
    assert ci._ingest_insights(a, st) == 1
    assert "yt-colemedin" in a.sessions and "colemedin" in a.peers
    assert st["insight_wm_id"] == "a"
    assert ci._ingest_insights(FakeAdapter(), st) == 0


# --- state / run_ingest -----------------------------------------------------

def test_state_migrates_from_legacy(home):
    (home / ci.LEGACY_STATE_NAME).write_text(json.dumps({"meeting_ids": [7]}))
    st = ci.load_state()
    assert st["meeting_ids"] == [7]
    assert (home / ci.STATE_NAME).exists()


def test_run_ingest_isolates_source_errors(home, monkeypatch):
    a = FakeAdapter()
    monkeypatch.setattr(ci, "_ingest_meetings",
                        lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    out = ci.run_ingest(a)
    assert str(out["meetings"]).startswith("error: boom"[:12])
    assert out["briefs"] == 0 and out["insights"] == 0
