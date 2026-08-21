"""write_brief — the mission's product.

The properties under test are the honesty ones, not the formatting. A
brief that looks finished while containing invented figures is the single
most damaging output this system could produce, because it is the one
artifact a human acts on directly.
"""
import json
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from app.tools.brief_writer import write_brief  # noqa: E402


def test_structured_findings_render_with_their_field_names():
    result = write_brief(json.dumps([
        {"year": 2023, "yoy_pct": 28.0, "severity": "ALERT"},
    ]))

    assert result["status"] == "SUCCESS"
    assert result["finding_count"] == 1
    # The field name travels with the number so a figure in the brief can
    # be traced back to what produced it.
    assert "yoy_pct: 28.0" in result["brief"]
    assert "ALERT" in result["brief"]


def test_plain_prose_is_a_valid_input_not_an_error():
    result = write_brief("Revenue rose.\nSupport tickets rose.")

    assert result["status"] == "SUCCESS"
    assert result["finding_count"] == 2


def test_empty_findings_refuse_rather_than_produce_an_empty_report():
    """A brief with nothing in it still LOOKS like a finished report."""
    for empty in ("", "   ", [], None):
        assert write_brief(empty)["status"] == "ERROR"


def test_missing_recommendations_are_stated_never_invented():
    """The failure mode that matters: a model asked for an executive
    brief will generate plausible advice whether or not anything
    supported it. This must say it has none instead.
    """
    result = write_brief(json.dumps(["churn improved to 4.1%"]))

    assert result["recommendation_count"] == 0
    assert "does not infer" in result["brief"]


def test_supplied_recommendations_are_numbered():
    result = write_brief(
        json.dumps(["ticket backlog in EU"]),
        recommendations=["Staff the EU queue", "Re-check in 7 days"],
    )

    assert result["recommendation_count"] == 2
    assert "1. Staff the EU queue" in result["brief"]
    assert "2. Re-check in 7 days" in result["brief"]


def test_no_number_appears_that_was_not_supplied():
    """The core guarantee. Every digit in the brief must come from the
    findings, the timestamp, or the counts -- never from inference.
    """
    result = write_brief(json.dumps(["revenue grew"]))
    brief = result["brief"]

    # Strip the generated timestamp and the provenance count line, then
    # assert nothing numeric is left to have been invented.
    body = brief.split("_Generated")[0] + brief.split("_\n", 1)[-1]
    body = body.replace(result["generated_at"], "")
    body = body.replace("1 finding(s)", "")

    assert not any(character.isdigit() for character in body), body


def test_large_finding_sets_are_truncated_but_the_real_count_is_kept():
    """Truncating silently would understate what the mission found."""
    result = write_brief(json.dumps([f"finding {n}" for n in range(50)]))

    assert result["finding_count"] == 50
    assert result["truncated"] is True
    assert "50 were supplied in total" in result["brief"]


def test_registry_reports_write_brief_as_implemented():
    """The planner reads this flag to decide whether the step is a gap."""
    import app.capabilities.bootstrap  # noqa: F401
    from app.capabilities.registry import registry

    assert registry.is_implemented("write_brief") is True
