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
schedule = importlib.import_module(f"{PKG}.schedule")


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
        m1: {"meetingType": "client",
             "overview": "Happy client.", "insights": ["They want more scope"],
             "sentimentScore": 0.8, "sentimentLabel": "positive",
             "satisfactionScore": 9, "satisfactionRationale": "said 'great work'",
             "lessons": [], "actionItems": ["send invoice"], "risks": []},
        m2: {"meetingType": "client",
             "overview": "Tense call.", "insights": ["Delays hurt trust"],
             "sentimentScore": -0.5, "sentimentLabel": "negative",
             "satisfactionScore": 3, "satisfactionRationale": "said 'frustrated'",
             "lessons": ["Communicate slips early"], "actionItems": [],
             "risks": ["churn risk if next sprint slips"],
             "strengths": ["report quality praised"],
             "weaknesses": ["two deadline slips in a row"]},
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
    assert roll["strengths"][0]["text"] == "report quality praised"
    assert roll["weaknesses"][0]["meeting"] == "Rough call"

    # chat tool surfaces analyzed meetings
    found = json.loads(analysis.tool_meeting_search({"query": "frustrated"}))
    assert found["count"] == 1
    assert found["meetings"][0]["analysis"]["sentimentLabel"] == "negative"


def test_meeting_type_gates_satisfaction(home, monkeypatch):
    mid, _ = store.upsert_meeting("import", None, "Team sync", 100.0, None,
                                  "Al: standup stuff")

    class FakeRes:
        parsed = {"meetingType": "Internal", "overview": "standup",
                  "insights": [], "sentimentScore": 0.7,
                  "sentimentLabel": "positive",
                  "satisfactionScore": 8,          # model forgot the sentinel
                  "satisfactionRationale": "friendly"}

    class FakeLlm:
        def complete_structured(self, **kw):
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    out = analysis.analyze_meeting(mid)
    assert out["meetingType"] == "internal"        # normalized lowercase
    assert out["satisfactionScore"] == -1          # forced sentinel for internal

    roll = analysis.dashboard_rollup()
    assert roll["avgSatisfaction"] is None         # no client meetings
    assert roll["satisfactionMeetings"] == 0
    assert roll["trend"][0]["satisfaction"] is None
    assert roll["trend"][0]["type"] == "internal"


def test_rollup_mixed_types_averages_clients_only(home):
    c, _ = store.upsert_meeting("import", None, "Client call", 100.0, None, "t")
    i, _ = store.upsert_meeting("import", None, "Standup", 200.0, None, "t")
    store.save_analysis(c, {"meetingType": "client", "overview": "x",
                            "insights": [], "sentimentScore": 0.5,
                            "sentimentLabel": "positive",
                            "satisfactionScore": 6,
                            "satisfactionRationale": "r"})
    store.save_analysis(i, {"meetingType": "internal", "overview": "y",
                            "insights": [], "sentimentScore": 0.9,
                            "sentimentLabel": "positive",
                            "satisfactionScore": -1,
                            "satisfactionRationale": "not a client meeting"})
    roll = analysis.dashboard_rollup()
    assert roll["analyzed"] == 2
    assert roll["avgSatisfaction"] == 6.0          # internal excluded
    assert roll["satisfactionMeetings"] == 1
    assert abs(roll["avgSentiment"] - 0.7) < 1e-9  # sentiment includes both


def test_batch_skips_analyzed_and_persists(home, monkeypatch):
    m1, _ = store.upsert_meeting("import", None, "Done already", 100.0, None, "t1")
    m2, _ = store.upsert_meeting("import", None, "Needs work", 200.0, None, "t2")
    store.save_analysis(m1, {"overview": "x", "insights": [],
                             "sentimentScore": 0, "sentimentLabel": "neutral",
                             "satisfactionScore": 5, "satisfactionRationale": "r"})
    analyzed_ids = []

    def fake_analyze(mid, feedback=""):
        analyzed_ids.append(mid)
        store.save_analysis(mid, {"overview": "y", "insights": [],
                                  "sentimentScore": 0.1, "sentimentLabel": "neutral",
                                  "satisfactionScore": 6,
                                  "satisfactionRationale": "r"})
        return {}

    monkeypatch.setattr(analysis, "analyze_meeting", fake_analyze)
    out = analysis.start_batch()
    assert out["total"] == 1                      # only the unanalyzed one
    import time
    for _ in range(50):
        if not analysis.batch_status().get("running"):
            break
        time.sleep(0.05)
    st = analysis.batch_status()
    assert st["running"] is False and st["done"] == 1 and st["failed"] == 0
    assert analyzed_ids == [m2]
    # nothing left -> a second start refuses
    with pytest.raises(RuntimeError):
        analysis.start_batch()


def test_batch_stop_cancels_between_meetings(home, monkeypatch):
    import time
    ids = []
    for i in range(3):
        mid, _ = store.upsert_meeting("import", None, f"M{i}", 100.0 + i,
                                      None, "transcript text")
        ids.append(mid)
    started = []

    def slow_analyze(mid, feedback=""):
        started.append(mid)
        if len(started) == 1:
            analysis.stop_batch()          # cancel right after the first starts
        store.save_analysis(mid, {"overview": "x", "insights": [],
                                  "sentimentScore": 0, "sentimentLabel": "neutral",
                                  "satisfactionScore": 5,
                                  "satisfactionRationale": "r"})
        return {}

    monkeypatch.setattr(analysis, "analyze_meeting", slow_analyze)
    analysis.start_batch()
    for _ in range(50):
        if not analysis.batch_status().get("running"):
            break
        time.sleep(0.05)
    st = analysis.batch_status()
    assert st.get("cancelled") is True
    assert len(started) == 1               # stopped before meeting 2
    with pytest.raises(RuntimeError):      # nothing running anymore
        analysis.stop_batch()


def test_redo_feedback_reaches_the_prompt(home, monkeypatch):
    mid, _ = store.upsert_meeting("import", None, "Redo me", 100.0, None,
                                  "Client: fine I guess")
    store.save_analysis(mid, {"overview": "old", "insights": [],
                              "sentimentScore": 0.9, "sentimentLabel": "positive",
                              "satisfactionScore": 9, "satisfactionRationale": "r"})
    seen = {}

    class FakeRes:
        parsed = {"overview": "revised", "insights": [],
                  "sentimentScore": 0.1, "sentimentLabel": "mixed",
                  "satisfactionScore": 5, "satisfactionRationale": "revised"}

    class FakeLlm:
        def complete_structured(self, **kw):
            seen["payload"] = kw["input"][0]["text"]
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    out = analysis.analyze_meeting(mid, feedback="score felt too high")
    assert out["overview"] == "revised"
    assert "REANALYSIS REQUEST" in seen["payload"]
    assert "score felt too high" in seen["payload"]
    assert "PRIOR ANALYSIS" in seen["payload"]
    # a plain analyze has no redo scaffolding
    analysis.analyze_meeting(mid)
    assert "REANALYSIS REQUEST" not in seen["payload"]


def test_analyze_requires_transcript(home):
    mid, _ = store.upsert_meeting("import", None, "Empty", None, None, "")
    with pytest.raises(RuntimeError):
        analysis.analyze_meeting(mid)


def test_evidence_normalization_and_rollup_quotes(home, monkeypatch):
    mid, _ = store.upsert_meeting("import", None, "Evidence call", 100.0, None,
                                  "Client: honestly this has been fantastic")
    parsed = {"meetingType": "client", "overview": "x",
              "insights": [{"text": "wants phase 2", "quote": "plan phase 2 now"},
                           "legacy string insight"],
              "sentimentScore": 0.7, "sentimentLabel": "positive",
              "sentimentQuotes": ["  honestly this has been fantastic  ", "",
                                  "q2", "q3", "q4"],
              "satisfactionScore": 9, "satisfactionRationale": "r",
              "lessons": [], "actionItems": [], "risks": [],
              "strengths": [{"text": "", "quote": "dropped with empty text"}],
              "weaknesses": []}

    class FakeRes:
        def __init__(self, p):
            self.parsed = p

    class FakeLlm:
        def complete_structured(self, **kw):
            return FakeRes(parsed)

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    out = analysis.analyze_meeting(mid)

    # object items pass through; legacy strings coerce; empty text drops
    assert out["insights"][0] == {"text": "wants phase 2", "quote": "plan phase 2 now"}
    assert out["insights"][1] == {"text": "legacy string insight", "quote": ""}
    assert out["strengths"] == []
    # sentiment quotes: stripped, empties dropped, capped at 3
    assert out["sentimentQuotes"] == ["honestly this has been fantastic", "q2", "q3"]

    roll = analysis.dashboard_rollup()
    ins = roll["insights"][0]
    assert ins["quote"] == "plan phase 2 now"
    assert ins["meetingId"] == mid
    assert ins["meeting"] == "Evidence call"


def test_autosync_cron_expr_maps_local_window_to_utc():
    # EDT: getTimezoneOffset() = 240 -> 8:00-19:00 local = 12:00-23:00 UTC
    assert schedule._cron_expr(240) == \
        "0 " + ",".join(str(h) for h in range(12, 24)) + " * * *"
    # UTC user: window unchanged
    assert schedule._cron_expr(0) == \
        "0 " + ",".join(str(h) for h in range(8, 20)) + " * * *"
    # IST (+05:30): offset -330 -> minute 30, hours 2..13 UTC
    assert schedule._cron_expr(-330) == \
        "30 " + ",".join(str(h) for h in range(2, 14)) + " * * *"


def test_autosync_ensure_creates_and_updates_job(home, monkeypatch):
    import types
    created, updated = [], []
    jobs_by_ref = {}

    fake_jobs = types.ModuleType("cron.jobs")

    def resolve_job_ref(ref):
        return jobs_by_ref.get(ref)

    def create_job(prompt, schedule, name=None, deliver=None,
                   script=None, no_agent=False, **kw):
        job = {"id": "job-1", "name": name, "schedule": schedule,
               "script": script, "no_agent": no_agent, "enabled": True}
        jobs_by_ref[job["id"]] = job
        jobs_by_ref[name] = job
        created.append(job)
        return job

    def update_job(job_id, updates):
        jobs_by_ref[job_id].update(updates)
        updated.append(updates)
        return jobs_by_ref[job_id]

    fake_jobs.resolve_job_ref = resolve_job_ref
    fake_jobs.create_job = create_job
    fake_jobs.update_job = update_job
    fake_cron = types.ModuleType("cron")
    fake_cron.jobs = fake_jobs
    monkeypatch.setitem(sys.modules, "cron", fake_cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", fake_jobs)

    info = schedule.ensure_sync_job(tz_offset_minutes=240)
    assert len(created) == 1
    assert created[0]["no_agent"] is True
    assert created[0]["schedule"].startswith("0 12,")
    assert info["enabled"] is True and info["configured"] is True

    # generated script exists under ~/.hermes/scripts and compiles
    script = home / "scripts" / schedule.SCRIPT_NAME
    assert script.exists()
    compile(script.read_text(), str(script), "exec")

    # toggle off updates the existing job instead of creating another
    info2 = schedule.ensure_sync_job(enabled=False)
    assert len(created) == 1
    assert updated and updated[-1]["enabled"] is False
    assert info2["enabled"] is False
    # tz offset survives the toggle
    assert schedule.load_settings()["tzOffsetMinutes"] == 240
