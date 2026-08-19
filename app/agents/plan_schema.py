"""The structured plan the planner must return.

Free text is unexecutable. The mission engine needs steps it can route
through the gate, so the planner is constrained to this schema.

`tool = None` is meaningful, not an error: it is how the planner says
"this step needs a capability I do not have". Phase 4 turns that into a
capability gap and an Evolution Event.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

StepKind = Literal["READ_ANALYZE", "EXTERNAL_EFFECT"]
RiskName = Literal["LOW", "MEDIUM", "HIGH"]


class MissionStep(BaseModel):
    step: int = Field(..., description="1-based order.")
    description: str = Field(..., description="What this step does.")
    kind: StepKind = Field(
        ...,
        description=(
            "READ_ANALYZE reads or reasons and changes nothing outside. "
            "EXTERNAL_EFFECT changes something in the outside world."
        ),
    )
    tool: Optional[str] = Field(
        None,
        description=(
            "Name of a registered capability, or null if no registered "
            "capability can do this step."
        ),
    )
    args: list[str] = Field(
        default_factory=list,
        description="Positional string arguments for the tool.",
    )
    risk: RiskName = Field(..., description="Risk of performing this step.")
    action: str = Field(..., description="Short label for the audit trail.")


class MissionPlan(BaseModel):
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[MissionStep] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    expected_output: str = ""

    def capability_gaps(self) -> list[MissionStep]:
        """Steps the planner could not map to a registered capability."""
        return [step for step in self.steps if step.tool is None]
