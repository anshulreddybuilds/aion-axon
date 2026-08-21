"""Registers the capabilities AION AXON starts life with.

Implemented capabilities get real functions. The rest are DECLARED: AION
knows the shape of the job but cannot do it yet. That distinction is what
lets the planner produce an honest capability gap instead of pretending.

Importing this module is idempotent, and declaring never overwrites a
real implementation.
"""
from app.capabilities.registry import registry
from app.capabilities.seed import SEED_CAPABILITIES
from app.tools.bigquery_public import query_public_dataset
from app.tools.brief_writer import write_brief
from app.tools.calculator import calculate
from app.tools.web_research import search_web

IMPLEMENTATIONS = {
    "calculator": calculate,
    "web_research": search_web,
    "read_dataset": query_public_dataset,
    "write_brief": write_brief,
}


def register_default_capabilities() -> None:
    for capability in SEED_CAPABILITIES:
        function = IMPLEMENTATIONS.get(capability.name)

        if capability.implemented and function is not None:
            registry.register(
                capability.name,
                capability.description,
                capability.risk,
                function,
            )
        else:
            registry.declare(
                capability.name,
                capability.description,
                capability.risk,
            )


register_default_capabilities()
