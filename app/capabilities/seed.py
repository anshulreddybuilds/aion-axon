"""The 12 starter capabilities AION AXON ships with.

The demo's capability counter starts here. Counts are supporting evidence,
never the headline — the mission result is the headline.

Capabilities marked IMPLEMENTED have real code behind them. Capabilities
marked DECLARED are known-but-unbuilt: the agent knows the shape of the
job and can say so honestly, which is what lets it recognise a gap instead
of hallucinating a success. A DECLARED capability can never execute --
`registry.get()` raises, and nothing routes around the gate to reach it.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedCapability:
    name: str
    description: str
    risk: str
    implemented: bool


SEED_CAPABILITIES: tuple[SeedCapability, ...] = (
    SeedCapability(
        "calculator",
        "Performs safe basic arithmetic calculations.",
        "LOW",
        True,
    ),
    SeedCapability(
        "web_research",
        "Researches a question on the public web using Google Search "
        "grounding and returns findings with source receipts.",
        "LOW",
        True,
    ),
    SeedCapability(
        "read_dataset",
        "Reads rows from a public BigQuery dataset with a read-only, "
        "allowlisted, byte-capped SELECT.",
        "LOW",
        True,
    ),
    SeedCapability(
        "summarize_text",
        "Summarizes a long document into key points.",
        "LOW",
        False,
    ),
    SeedCapability(
        "detect_anomalies",
        "Finds outliers and unexpected changes in a numeric series.",
        "LOW",
        False,
    ),
    SeedCapability(
        "compare_periods",
        "Compares two time periods and reports the deltas.",
        "LOW",
        False,
    ),
    SeedCapability(
        "extract_entities",
        "Pulls named entities such as vendors and products from text.",
        "LOW",
        False,
    ),
    SeedCapability(
        "rank_priorities",
        "Ranks findings by business impact.",
        "LOW",
        False,
    ),
    SeedCapability(
        "write_brief",
        "Writes an executive Business Action Brief from findings.",
        "LOW",
        True,
    ),
    SeedCapability(
        "format_table",
        "Formats structured rows into a readable table.",
        "LOW",
        False,
    ),
    SeedCapability(
        "validate_numbers",
        "Re-checks arithmetic and flags inconsistencies.",
        "LOW",
        False,
    ),
    SeedCapability(
        "schedule_followup",
        "Schedules a follow-up check on a mission.",
        "MEDIUM",
        False,
    ),
)

SEED_COUNT = len(SEED_CAPABILITIES)
