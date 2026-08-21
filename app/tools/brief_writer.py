"""write_brief — the Business Action Brief the mission exists to produce.

This is the mission's PRODUCT. Everything else in AION Axon is machinery
for getting here: the planner decomposes, SYNAPSE acquires what is
missing, the gate governs, and then this turns whatever was actually
found into something an owner can act on.

Deliberately deterministic, pure-standard-library, and model-free. Three
reasons, and the third is the one that matters:

1. It costs no quota, so the deliverable can never be blocked by a rate
   limit at demo time.
2. It is reproducible -- the same findings always render the same brief,
   which is what makes it evidence rather than a performance.
3. **It cannot invent a number.** A model asked to "write an executive
   brief" will happily produce "revenue up 12%, efficiency improved 68%"
   whether or not anything measured that. This module can only arrange
   what it was handed. If a figure appears in the brief, something
   upstream actually produced it.

That last property is why the brief is worth trusting at all, and it is
the same rule the rest of the system runs on: measure, never estimate.
"""
import json
from datetime import datetime, timezone
from typing import Any, Optional

MAX_SECTION_ITEMS = 20


def _as_items(findings: Any) -> tuple[list[Any], Optional[str]]:
    """Normalise findings into a list. Returns (items, parse_note).

    `None` is emptiness, not a finding. Without this branch it fell
    through to the scalar case and produced a one-item brief whose single
    bullet was the word "None" -- a finished-looking report about
    nothing, which is exactly the failure this module is built to refuse.
    """
    if findings is None:
        return [], None

    if isinstance(findings, str):
        text = findings.strip()

        if not text:
            return [], None

        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            # Plain prose is a legitimate input, not an error. Each line
            # becomes a finding so a human-written note briefs the same
            # way a structured result does.
            lines = [line.strip() for line in text.splitlines()]
            return [line for line in lines if line], None

        return _as_items(parsed)[0], None

    if isinstance(findings, dict):
        return [findings], None

    if isinstance(findings, list):
        return findings, None

    return [findings], None


def _render_item(item: Any) -> str:
    """One finding as one line. Dicts keep their keys so a number in the
    brief can be traced back to the field that produced it."""
    if isinstance(item, dict):
        parts = [
            f"{key}: {value}"
            for key, value in item.items()
            if value is not None and value != ""
        ]
        return " | ".join(parts) if parts else str(item)

    return str(item)


def write_brief(
    findings: Any,
    title: str = "Business Action Brief",
    recommendations: Any = None,
) -> dict:
    """Render findings into an executive Business Action Brief.

    `findings` accepts a JSON string, a JSON array/object, plain prose, or
    a list -- whatever the upstream step actually produced, without the
    caller having to reshape it first.

    `recommendations` is optional and, when absent, the brief says so
    rather than generating advice. An invented recommendation is worse
    than a missing one: it reads exactly like a considered one.
    """
    items, _ = _as_items(findings)

    if not items:
        return {
            "status": "ERROR",
            "error": (
                "No findings supplied. A brief with nothing in it would "
                "look like a finished report about nothing."
            ),
        }

    truncated = len(items) > MAX_SECTION_ITEMS
    shown = items[:MAX_SECTION_ITEMS]

    actions, _ = _as_items(recommendations) if recommendations else ([], None)

    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        f"# {title}",
        "",
        f"_Generated {generated_at} by AION Axon._",
        "",
        "## Key findings",
        "",
    ]

    lines.extend(f"- {_render_item(item)}" for item in shown)

    if truncated:
        lines.append(
            f"- _...and {len(items) - MAX_SECTION_ITEMS} further findings "
            f"not shown; {len(items)} were supplied in total._"
        )

    lines.extend(["", "## Recommended actions", ""])

    if actions:
        lines.extend(
            f"{n}. {_render_item(action)}"
            for n, action in enumerate(actions[:MAX_SECTION_ITEMS], start=1)
        )
    else:
        lines.append(
            "- None supplied. This brief reports what was found; it does "
            "not infer what to do about it."
        )

    lines.extend([
        "",
        "## Provenance",
        "",
        f"- {len(items)} finding(s) received from the mission's own steps.",
        "- Figures are reproduced exactly as measured upstream. This brief "
        "performs no estimation and adds no numbers of its own.",
    ])

    return {
        "status": "SUCCESS",
        "title": title,
        "generated_at": generated_at,
        "finding_count": len(items),
        "recommendation_count": len(actions),
        "truncated": truncated,
        "brief": "\n".join(lines),
    }
