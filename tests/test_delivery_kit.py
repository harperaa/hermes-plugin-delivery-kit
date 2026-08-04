"""delivery-kit tests — store, providers, analysis, rollup, key storage."""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PKG = "delivery_kit_test_pkg"
ROOT = Path(__file__).resolve().parent.parent

if PKG not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PKG, str(ROOT / "__init__.py"),
        submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)

store = importlib.import_module(f"{PKG}.store")
providers = importlib.import_module(f"{PKG}.providers")
analysis = importlib.import_module(f"{PKG}.analysis")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("FIREFLIES_API_KEY", raising=False)
    return tmp_path


def test_upsert_dedupes_by_external_id(home):
    a, new_a = store.upsert_meeting("fireflies", "x1", "Kickoff", 100.0, 30.0, "t")
    b, new_b = store.upsert_meeting("fireflies", "x1", "Kickoff", 100.0, 30.0, "t")
    assert new_a is True and new_b is False and a == b
    c, new_c = store.upsert_meeting("import", None, "Pasted", None, None, "t2")
    d, new_d = store.upsert_meeting("import", None, "Pasted", None, None, "t2")
    assert new_c and new_d and c != d          # manual imports never dedupe
    assert len(store.list_meetings()) == 3


def test_provider_key_storage_and_status(home):
    st = {p["id"]: p for p in providers.provider_status()}
    assert st["fireflies"]["default"] is True
    assert st["fireflies"]["connected"] is False
    assert st["otter"]["env"] is None            # import-only provider

    providers.store_key("FIREFLIES_API_KEY", "ff-test-123")
    st = {p["id"]: p for p in providers.provider_status()}
    assert st["fireflies"]["connected"] is True
    env = (home / ".env").read_text()
    assert "FIREFLIES_API_KEY=ff-test-123" in env
    # replace-not-duplicate
    providers.store_key("FIREFLIES_API_KEY", "ff-test-456")
    env = (home / ".env").read_text()
    assert env.count("FIREFLIES_API_KEY=") == 1 and "ff-test-456" in env

    with pytest.raises(ValueError):
        providers.store_key("NOT_A_PROVIDER_KEY", "x")
    with pytest.raises(ValueError):
        providers.store_key("FIREFLIES_API_KEY", "two\nlines")


def test_fireflies_fetch_normalizes(home, monkeypatch):
    providers.store_key("FIREFLIES_API_KEY", "ff-key")
    payload = {"data": {"transcripts": [{
        "id": "abc", "title": "Weekly sync", "date": 1_754_000_000_000,
        "duration": 42.5,
        "summary": {"overview": "Went well", "action_items": ["ship it"]},
        "sentences": [{"text": "Hello", "speaker_name": "Al"},
                      {"text": "Hi there", "speaker_name": "Client"}],
    }]}}

    class FakeResp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured = {}

    def fake_open(req, timeout=0):
        captured["auth"] = req.get_header("Authorization")
        return FakeResp()

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_open)
    out = providers.fireflies_fetch()
    assert captured["auth"] == "Bearer ff-key"
    m = out[0]
    assert m["title"] == "Weekly sync"
    assert m["heldAt"] == 1_754_000_000.0
    assert "Al: Hello" in m["transcript"] and "Client: Hi there" in m["transcript"]
    assert "Went well" in m["providerSummary"]


def test_fathom_fetch_normalizes(home, monkeypatch):
    providers.store_key("FATHOM_API_KEY", "fa-key")
    payload = {"items": [{
        "id": 77, "title": "Fathom call",
        "recording_start_time": "2026-08-01T15:00:00Z",
        "recording_end_time": "2026-08-01T15:30:00Z",
        "transcript": [{"speaker": {"display_name": "Al"}, "text": "hello"}],
        "summary": "quick sync",
    }]}
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout=0):
        captured["key"] = req.get_header("X-api-key")
        captured["url"] = req.full_url
        return FakeResp()

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_open)
    out = providers.fathom_fetch()
    assert captured["key"] == "fa-key"
    assert "include_transcript=true" in captured["url"]
    m = out[0]
    assert m["title"] == "Fathom call" and m["durationMin"] == 30.0
    assert "Al: hello" in m["transcript"]


def test_tldv_fetch_normalizes(home, monkeypatch):
    providers.store_key("TLDV_API_KEY", "tl-key")
    responses = {
        "meetings": {"results": [{"id": "m9", "name": "tldv call",
                                  "happenedAt": "2026-08-02T10:00:00Z",
                                  "duration": 25}]},
        "transcript": {"data": [{"speaker": "Client", "text": "sounds good"}]},
    }

    class FakeResp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return json.dumps(self.body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout=0):
        body = (responses["transcript"] if req.full_url.endswith("/transcript")
                else responses["meetings"])
        return FakeResp(body)

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_open)
    out = providers.tldv_fetch()
    assert out[0]["title"] == "tldv call"
    assert "Client: sounds good" in out[0]["transcript"]


def test_sync_dispatcher(home):
    with pytest.raises(RuntimeError):
        providers.sync_provider("plaud")       # no direct sync yet
    with pytest.raises(RuntimeError):
        providers.sync_provider("nonsense")
    assert set(providers.SYNCERS) == {"fireflies", "fathom", "grain", "tldv"}
    # catalog and syncers agree on canSync
    for p in providers.PROVIDERS:
        assert bool(p.get("canSync")) == (p["id"] in providers.SYNCERS)


def test_fireflies_requires_key(home):
    with pytest.raises(RuntimeError):
        providers.fireflies_fetch()


def test_analysis_and_rollup(home, monkeypatch):
    m1, _ = store.upsert_meeting("import", None, "Good call", 100.0, None,
                                 "Client: this is great work")
    m2, _ = store.upsert_meeting("import", None, "Rough call", 200.0, None,
                                 "Client: I'm frustrated with the delays")

    fake = {
        m1: {"overview": "Happy client.", "insights": ["They want more scope"],
             "sentimentScore": 0.8, "sentimentLabel": "positive",
             "satisfactionScore": 9, "satisfactionRationale": "said 'great work'",
             "lessons": [], "actionItems": ["send invoice"], "risks": []},
        m2: {"overview": "Tense call.", "insights": ["Delays hurt trust"],
             "sentimentScore": -0.5, "sentimentLabel": "negative",
             "satisfactionScore": 3, "satisfactionRationale": "said 'frustrated'",
             "lessons": ["Communicate slips early"], "actionItems": [],
             "risks": ["churn risk if next sprint slips"]},
    }

    class FakeRes:
        def __init__(self, parsed):
            self.parsed = parsed

    class FakeLlm:
        def __init__(self, mid):
            self.mid = mid

        def complete_structured(self, **kw):
            return FakeRes(fake[self.mid])

    def analyze_with_fake(mid):
        monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm(mid))
        return analysis.analyze_meeting(mid)

    out1 = analyze_with_fake(m1)
    assert out1["satisfactionScore"] == 9
    analyze_with_fake(m2)

    roll = analysis.dashboard_rollup()
    assert roll["analyzed"] == 2 and roll["total"] == 2
    assert roll["avgSatisfaction"] == 6.0
    assert abs(roll["avgSentiment"] - 0.15) < 1e-9
    # trend reads oldest -> newest
    assert roll["trend"][0]["title"] == "Good call"
    assert roll["risks"][0]["meeting"] == "Rough call"
    assert roll["lessons"][0]["text"] == "Communicate slips early"

    # chat tool surfaces analyzed meetings
    found = json.loads(analysis.tool_meeting_search({"query": "frustrated"}))
    assert found["count"] == 1
    assert found["meetings"][0]["analysis"]["sentimentLabel"] == "negative"


def test_analyze_requires_transcript(home):
    mid, _ = store.upsert_meeting("import", None, "Empty", None, None, "")
    with pytest.raises(RuntimeError):
        analysis.analyze_meeting(mid)
