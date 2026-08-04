"""delivery-kit meeting analysis — host LLM extraction + dashboard rollup.

Per meeting: insights, sentiment, client satisfaction, lessons learned,
action items — one structured PluginLlm call. The dashboard aggregates
every analyzed meeting into the delivery view.
"""
from __future__ import annotations

import json
import re
from typing import Optional

try:
    from . import store
except ImportError:  # loaded outside package context (tests, tooling)
    import store  # type: ignore

PLUGIN_ID = "delivery-kit"

_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string",
                     "description": "2-3 sentence meeting overview"},
        "insights": {"type": "array", "items": {"type": "string"},
                     "description": "3-8 concrete insights from the meeting"},
        "sentimentScore": {"type": "number",
                           "description": "Client sentiment -1.0 (hostile) to 1.0 (delighted)"},
        "sentimentLabel": {"type": "string",
                           "description": "one word: negative | mixed | neutral | positive"},
        "satisfactionScore": {"type": "number",
                              "description": "Client satisfaction 0-10 as evidenced in THIS meeting"},
        "satisfactionRationale": {"type": "string",
                                  "description": "One sentence citing the evidence for the score"},
        "lessons": {"type": "array", "items": {"type": "string"},
                    "description": "Lessons learned for delivering better (0-5)"},
        "actionItems": {"type": "array", "items": {"type": "string"},
                        "description": "Open action items with owners when stated"},
        "risks": {"type": "array", "items": {"type": "string"},
                  "description": "Churn/scope/relationship risks heard (0-3)"},
        "strengths": {"type": "array", "items": {"type": "string"},
                      "description": "What went well in the delivery — things the client praised or that clearly landed (0-5)"},
        "weaknesses": {"type": "array", "items": {"type": "string"},
                       "description": "What fell short — friction, complaints, or delivery gaps heard in the meeting (0-5)"},
    },
    "required": ["overview", "insights", "sentimentScore", "sentimentLabel",
                 "satisfactionScore", "satisfactionRationale"],
}

_INSTRUCTIONS = """You are the Delivery Analyst for a client-services business.
You are given one client meeting transcript. Extract, with evidence, not
vibes:
- overview (2-3 sentences)
- insights: concrete, decision-useful takeaways (3-8)
- sentimentScore/-Label: the CLIENT's sentiment, not the vendor's
- satisfactionScore (0-10) with a one-sentence rationale citing what was said
- lessons: what to do differently next delivery (skip if none earned)
- actionItems: open commitments, with owner names when stated
- risks: churn, scope, or relationship risks actually heard
- strengths: what went well — client praise, wins, things that landed
- weaknesses: what fell short — friction, complaints, delivery gaps

Be honest — a tense meeting scores low. Never invent content that is not in
the transcript."""


def _llm():
    from agent.plugin_llm import PluginLlm
    return PluginLlm(plugin_id=PLUGIN_ID)


def analyze_meeting(meeting_id: int, feedback: str = "") -> dict:
    m = store.get_meeting(meeting_id, with_transcript=True)
    if not m:
        raise RuntimeError(f"meeting {meeting_id} not found")
    text = (m.get("transcript") or "").strip()
    if not text:
        text = (m.get("providerSummary") or "").strip()
    if not text:
        raise RuntimeError("meeting has no transcript to analyze")
    redo_note = ""
    if (feedback or "").strip():
        prior = m.get("analysis")
        redo_note = ("\n\nREANALYSIS REQUEST — the user reviewed the prior "
                     "analysis and says:\n" + feedback.strip()[:2000] +
                     ("\n\nPRIOR ANALYSIS (revise in light of the feedback):\n"
                      + json.dumps(prior)[:4000] if prior else ""))
    payload = (f"MEETING: {m['title']}\n\n"
               f"PROVIDER SUMMARY (may be empty):\n{m.get('providerSummary') or '(none)'}\n\n"
               f"TRANSCRIPT:\n{text[:60_000]}" + redo_note)
    res = _llm().complete_structured(
        instructions=_INSTRUCTIONS,
        input=[{"type": "text", "text": payload}],
        json_schema=_SCHEMA,
        schema_name="delivery_analysis",
        temperature=0.2,
        max_tokens=1600,
        timeout=180,
        purpose="delivery-meeting-analysis",
    )
    parsed = getattr(res, "parsed", None)
    if parsed is None:
        raw = getattr(res, "text", "") or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        raise RuntimeError("analyst returned no usable response — try again")
    parsed.setdefault("lessons", [])
    parsed.setdefault("actionItems", [])
    parsed.setdefault("risks", [])
    parsed.setdefault("strengths", [])
    parsed.setdefault("weaknesses", [])
    store.save_analysis(meeting_id, parsed)
    return parsed


def dashboard_rollup(meetings: Optional[list[dict]] = None) -> dict:
    """Aggregate analyzed meetings into the delivery dashboard."""
    ms = meetings if meetings is not None else store.list_meetings()
    analyzed = [m for m in ms if m.get("analysis")]
    n = len(analyzed)
    if n == 0:
        return {"analyzed": 0, "total": len(ms)}
    sent = [float(m["analysis"].get("sentimentScore", 0)) for m in analyzed]
    sat = [float(m["analysis"].get("satisfactionScore", 0)) for m in analyzed]
    # newest-first lists arrive sorted by held_at desc; trends read old->new
    trend = [{"heldAt": m.get("heldAt") or m.get("createdAt"),
              "title": m["title"],
              "sentiment": float(m["analysis"].get("sentimentScore", 0)),
              "satisfaction": float(m["analysis"].get("satisfactionScore", 0))}
             for m in reversed(analyzed)]
    lessons, insights, risks = [], [], []
    strengths, weaknesses = [], []
    for m in analyzed:
        for key, bucket in (("lessons", lessons), ("insights", insights),
                            ("risks", risks), ("strengths", strengths),
                            ("weaknesses", weaknesses)):
            for item in m["analysis"].get(key) or []:
                bucket.append({"text": item, "meeting": m["title"],
                               "heldAt": m.get("heldAt") or m.get("createdAt")})
    return {
        "analyzed": n,
        "total": len(ms),
        "avgSentiment": sum(sent) / n,
        "avgSatisfaction": sum(sat) / n,
        "latestSentiment": sent[0],
        "latestSatisfaction": sat[0],
        "trend": trend,
        "lessons": lessons[:40],
        "insights": insights[:60],
        "risks": risks[:20],
        "strengths": strengths[:40],
        "weaknesses": weaknesses[:40],
    }


# ---------------------------------------------------------------------------
# Agent tool (chat access: "what did the client say about X last month?")
# ---------------------------------------------------------------------------

def tool_meeting_search(args: dict, **kwargs) -> str:
    results = store.search_meetings(query=args.get("query") or "",
                                    limit=int(args.get("limit") or 5))
    for r in results:
        if r.get("analysis"):
            r["analysis"] = {k: r["analysis"].get(k) for k in
                             ("overview", "insights", "sentimentLabel",
                              "satisfactionScore", "lessons", "actionItems")}
    return json.dumps({"count": len(results), "meetings": results})


# ---------------------------------------------------------------------------
# Server-side batch: "Analyze all" survives page refreshes. Progress lives
# in batch.json; a daemon thread walks the unanalyzed meetings; a second
# start while running is refused; already-analyzed meetings are skipped.
# ---------------------------------------------------------------------------

import threading
import time as _time

_BATCH_LOCK = threading.Lock()


def _batch_path():
    return store.data_dir() / "batch.json"


def batch_status() -> dict:
    try:
        st = json.loads(_batch_path().read_text())
    except Exception:
        return {"running": False}
    if st.get("running") and _time.time() - float(st.get("updatedAt", 0)) > 600:
        # thread died (restart mid-batch) — report honestly and clear
        st["running"] = False
        st["stale"] = True
        _write_batch(st)
    return st


def _write_batch(st: dict) -> None:
    st["updatedAt"] = _time.time()
    p = _batch_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    tmp.replace(p)


def _batch_worker(ids: list, titles: dict) -> None:
    done = 0
    failed = 0
    for mid in ids:
        if batch_status().get("cancelRequested"):
            _write_batch({"running": False, "total": len(ids), "done": done,
                          "failed": failed, "cancelled": True,
                          "finishedAt": _time.time()})
            return
        _write_batch({"running": True, "total": len(ids), "done": done,
                      "failed": failed, "current": titles.get(mid, "")})
        try:
            m = store.get_meeting(mid, with_transcript=False)
            if m and not m.get("analysis"):     # still unanalyzed?
                analyze_meeting(mid)
        except Exception:
            failed += 1
        done += 1
    _write_batch({"running": False, "total": len(ids), "done": done,
                  "failed": failed, "finishedAt": _time.time()})


def start_batch() -> dict:
    with _BATCH_LOCK:
        st = batch_status()
        if st.get("running"):
            raise RuntimeError("an Analyze-all run is already in progress")
        todo = [m for m in store.list_meetings() if not m.get("analysis")
                and ((m.get("transcript") is not None) or True)]
        # only meetings with content can be analyzed; filter via detail fetch
        ids = []
        titles = {}
        for m in todo:
            full = store.get_meeting(m["id"], with_transcript=True)
            if full and ((full.get("transcript") or "").strip()
                         or (full.get("providerSummary") or "").strip()):
                ids.append(m["id"])
                titles[m["id"]] = m["title"]
        if not ids:
            raise RuntimeError("nothing to analyze — every meeting with a "
                               "transcript is already done")
        _write_batch({"running": True, "total": len(ids), "done": 0,
                      "failed": 0, "current": titles[ids[0]],
                      "startedAt": _time.time()})
        t = threading.Thread(target=_batch_worker, args=(ids, titles),
                             daemon=True)
        t.start()
        return {"started": True, "total": len(ids)}


def stop_batch() -> dict:
    """Request cancellation; the worker stops before its next meeting (the
    in-flight analysis finishes — LLM calls are not interruptible)."""
    st = batch_status()
    if not st.get("running"):
        raise RuntimeError("no Analyze-all run is in progress")
    st["cancelRequested"] = True
    _write_batch(st)
    return {"stopping": True}
