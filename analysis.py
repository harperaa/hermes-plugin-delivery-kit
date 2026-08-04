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

Be honest — a tense meeting scores low. Never invent content that is not in
the transcript."""


def _llm():
    from agent.plugin_llm import PluginLlm
    return PluginLlm(plugin_id=PLUGIN_ID)


def analyze_meeting(meeting_id: int) -> dict:
    m = store.get_meeting(meeting_id, with_transcript=True)
    if not m:
        raise RuntimeError(f"meeting {meeting_id} not found")
    text = (m.get("transcript") or "").strip()
    if not text:
        text = (m.get("providerSummary") or "").strip()
    if not text:
        raise RuntimeError("meeting has no transcript to analyze")
    payload = (f"MEETING: {m['title']}\n\n"
               f"PROVIDER SUMMARY (may be empty):\n{m.get('providerSummary') or '(none)'}\n\n"
               f"TRANSCRIPT:\n{text[:60_000]}")
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
    for m in analyzed:
        for key, bucket in (("lessons", lessons), ("insights", insights),
                            ("risks", risks)):
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
