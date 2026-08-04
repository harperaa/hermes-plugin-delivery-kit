# Delivery Kit — Hermes Plugin

> Aligned with the mentoring of **Dr. Allen Harper, AI Cyber Value Creator** — join the community at [AI Cyber Value Creators on Skool](https://www.skool.com/ai-cyber-value-creators).

The Deliver-phase workbench for [Hermes Agent](https://github.com/NousResearch/hermes-agent): pull in client meeting transcripts, analyze each one with the host LLM, and roll insights, sentiment, client satisfaction, and lessons learned into one delivery dashboard.

## What you get

- **Connect bar** — provider buttons at the top of the page. Each opens a modal with step-by-step key-retrieval instructions and an inline field that stores the key straight into your env (no trip to the Keys page). **Live sync (verified APIs):** Fireflies.ai (default, GraphQL), Fathom (`api.fathom.ai/external/v1`, transcripts inline), Grain (public API v2), and tl;dv (`pasta.tldv.io/v1alpha1`). **Key stored now, sync coming:** Plaud (their new developer platform, docs.plaud.ai) and Avoma. **Import path (no usable pull API):** Otter (Enterprise-only API), Read.ai (webhook-based), Granola (local-first), and Zoom (.vtt exports) — paste any of them via Import; analysis is identical.
- **Hourly auto-sync** — a zero-LLM-cost `no_agent` cron job pulls every connected provider hourly, 08:00–19:00 in *your* timezone (the page sends the browser's offset, so DST self-corrects). Toggle it from the sync bar.
- **Meeting Analysis tab** — ⟳ Sync pulls the latest transcripts (deduped); ＋ Import pastes one from any tool. Each meeting gets a ✨ Analyze pass: meeting type (client / sales / internal / other), overview, insights, client sentiment (−1…+1, shown as a color-shaded smiley badge), satisfaction (client-facing meetings only), strengths, weaknesses, lessons learned, action items, and risks. ✨ Analyze all works the backlog server-side — refresh-safe, skips already-analyzed meetings, and ⏹ Stop halts it; ↻ Redo re-analyzes one meeting with your optional feedback in the prompt.
- **Evidence click-through** — every insight, lesson, strength, weakness, risk, action item, and the sentiment badge itself is backed by verbatim transcript quotes. Click any of them for a modal showing the full transcript with the supporting lines highlighted and scrolled into view.
- **Filters & search** — search covers titles, transcripts, and analyses (server-side); pill filters slice by meeting type or flip to aggregated Strengths / Weaknesses / Risks views across all meetings.
- **Delivery Dashboard tab** — the rollup: averages and latest scores, a satisfaction-bars + sentiment-line trend chart, and aggregated Risks / Lessons / Insights with per-meeting attribution (also click-through to evidence), plus its own filter box.
- **Chat access** — the `meeting_search` tool lets any chat session answer "what did the client say about scope last month" from your meeting history.

## Layout

```
plugin.yaml        manifest: FIREFLIES_API_KEY prestage, meeting_search tool
store.py           meetings + analyses (sqlite, provider-deduped)
providers.py       provider catalog, env key storage, live sync fetchers
analysis.py        per-meeting LLM analysis + dashboard rollup
schedule.py        hourly auto-sync cron job (no-agent, user-local window)
dashboard/         the /delivery page (React via the hermes plugin SDK)
tests/             pytest suite
```

MIT licensed.
