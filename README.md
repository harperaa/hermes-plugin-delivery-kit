# Delivery Kit — Hermes Plugin

> Aligned with the mentoring of **Dr. Allen Harper, AI Cyber Value Creator** — join the community at [AI Cyber Value Creators on Skool](https://www.skool.com/ai-cyber-value-creators).

The Deliver-phase workbench for [Hermes Agent](https://github.com/NousResearch/hermes-agent): pull in client meeting transcripts, analyze each one with the host LLM, and roll insights, sentiment, client satisfaction, and lessons learned into one delivery dashboard.

## What you get

- **Connect bar** — provider buttons at the top of the page. Each opens a modal with step-by-step key-retrieval instructions and an inline field that stores the key straight into your env (no trip to the Keys page). **Fireflies.ai is the default** (`FIREFLIES_API_KEY`, prestaged); Fathom / Grain / tl;dv keys store now with sync landing in updates; Otter and Zoom connect via transcript import.
- **Meeting Analysis tab** — ⟳ Sync pulls your latest Fireflies transcripts (GraphQL, deduped); ＋ Import pastes a transcript from any tool. Each meeting gets a ✨ Analyze pass: overview, insights, client sentiment (−1…+1), satisfaction (0–10 with cited evidence), lessons learned, action items, and risks. Analyze all runs the backlog.
- **Delivery Dashboard tab** — the rollup: averages and latest scores, a satisfaction-bars + sentiment-line trend chart, and aggregated Risks / Lessons / Insights with per-meeting attribution.
- **Chat access** — the `meeting_search` tool lets any chat session answer "what did the client say about scope last month" from your meeting history.

## Layout

```
plugin.yaml        manifest: FIREFLIES_API_KEY prestage, meeting_search tool
store.py           meetings + analyses (sqlite, provider-deduped)
providers.py       provider catalog, env key storage, Fireflies GraphQL sync
analysis.py        per-meeting LLM analysis + dashboard rollup
dashboard/         the /delivery page (React via the hermes plugin SDK)
tests/             pytest suite
```

MIT licensed.
