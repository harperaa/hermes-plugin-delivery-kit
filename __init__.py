"""delivery-kit — hermes plugin entry point."""
from __future__ import annotations

import logging

try:
    from . import analysis
except ImportError:  # imported outside package context (tests, tooling)
    import analysis  # type: ignore

logger = logging.getLogger(__name__)

_MEETING_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string",
                  "description": "Substring to find across meeting titles, transcripts, and analyses"},
        "limit": {"type": "integer", "description": "Max results (default 5)"},
    },
    "description": ("Delivery Kit: search analyzed client meetings — use to "
                    "answer questions like 'what did the client say about "
                    "scope last month' from meeting history."),
}


def register(ctx) -> None:
    ctx.register_tool(
        name="meeting_search",
        toolset="delivery_kit",
        schema=_MEETING_SEARCH_SCHEMA,
        handler=analysis.tool_meeting_search,
    )
