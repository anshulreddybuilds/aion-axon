"""Registers the tools AION AXON starts life with.

Importing this module is idempotent: registering the same name twice
replaces the definition rather than duplicating it.
"""
from app.capabilities.registry import registry
from app.tools.calculator import calculate
from app.tools.web_research import search_web


def register_default_tools() -> None:
    registry.register(
        "calculator",
        "Performs safe basic arithmetic calculations.",
        "LOW",
        calculate,
    )

    registry.register(
        "web_research",
        "Read-only public web research. No external side effects.",
        "LOW",
        search_web,
    )


register_default_tools()
