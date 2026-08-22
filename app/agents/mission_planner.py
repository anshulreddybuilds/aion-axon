"""The structured planner: messy request in, executable plan out.

Separate from `planner_agent`, which produces the human-readable plan
shown in the demo. This one is constrained by `MissionPlan` so the
mission engine has steps it can actually route through the gate.

Both are ADK agents driven by an ADK Runner. Neither executes anything:
they return a plan, and the gate decides what happens to it.
"""
import asyncio
import json
import os
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.plan_schema import MissionPlan
from app.capabilities.declarations import capability_catalog

APP_NAME = "aion_axon_mission_planner"
MODEL = os.getenv("AXON_PLANNER_MODEL", "gemini-3.6-flash")

INSTRUCTION = """
You are the mission planner of AION AXON.

You turn a messy human request into an ordered, executable plan.
You do NOT answer the request yourself and you NEVER execute anything.

Rules you must follow:

1. Use ONLY capability names from the catalog you are given.
2. If a step needs a capability that is marked NOT IMPLEMENTED, or that
   is not in the catalog at all, set "tool" to null for that step.
   Setting tool to null is CORRECT and expected when the capability does
   not exist. Never substitute a different capability to avoid a null,
   and never pretend a step can be done when it cannot.
3. Mark every step READ_ANALYZE or EXTERNAL_EFFECT. Anything that changes
   the outside world, spends money, sends a message, or writes to a
   system outside AION is EXTERNAL_EFFECT.
4. Risk: LOW for reading and analysis. MEDIUM for anything with an
   external effect or business consequence. HIGH for anything touching
   credentials, secrets, destructive operations, or security controls.
5. "args" are positional string arguments for the capability. For the
   calculator, pass a single arithmetic expression such as "1250 * 1.18".
   For web_research, pass a single search question.
6. CHAINING — to pass an earlier step's OUTPUT into a later step, write
   "$STEP_1" (or $STEP_2, and so on) as that argument. It is replaced at
   run time with what that step actually returned.
   Use this whenever a step consumes a previous step's result. A step
   that analyses data produced by step 1 takes args ["$STEP_1"], NOT a
   sentence describing the data. A description is not data: passing one
   produces a confident answer about nothing.

   Reach INSIDE a result with a dot: "$STEP_1.rows". Capabilities return
   an envelope like {"status": ..., "rows": [...], "row_count": N}, and a
   capability that wants the records themselves will reject the whole
   envelope. read_dataset -> analysis is almost always "$STEP_1.rows".

7. BIGQUERY COST — read_dataset refuses any query that would scan more
   than ~200 MB, and the query fails outright rather than running. Keep
   it narrow:
   - Select only the columns you need. Never SELECT *.
   - Always filter with WHERE; aggregate with GROUP BY where you can.
   - Known-good example, ~89 MB:
     SELECT year, SUM(number) AS total
     FROM `bigquery-public-data.usa_names.usa_1910_2013`
     WHERE year >= 2005 GROUP BY year ORDER BY year

8. Keep steps minimal and concrete. Prefer fewer real steps to many
   vague ones.

Return ONLY the structured plan.
"""


def _agent() -> Agent:
    # Built per call so the catalog reflects capabilities acquired since
    # process start -- a self-evolving agent whose planner caches the
    # capability list would go blind to its own new skills.
    return Agent(
        name="axon_mission_planner",
        model=MODEL,
        description="Turns messy requests into executable AION AXON plans.",
        instruction=(
            f"{INSTRUCTION}\n\nCAPABILITY CATALOG:\n{capability_catalog()}"
        ),
        output_schema=MissionPlan,
    )


def planner_available() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


async def _run(request: str, user_id: str) -> str:
    session_service = InMemorySessionService()

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    runner = Runner(
        app_name=APP_NAME,
        agent=_agent(),
        session_service=session_service,
    )

    chunks: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=request)],
        ),
    ):
        if not event.content or not event.content.parts:
            continue

        for part in event.content.parts:
            if getattr(part, "text", None):
                chunks.append(part.text)

    return "".join(chunks).strip()


def plan_mission(
    request: str,
    user_id: str = "anshul",
) -> tuple[Optional[MissionPlan], Optional[str]]:
    """Return (plan, error). Never raises.

    A planning failure must degrade the mission to an honest error, not
    take the service down or invent a plan.
    """
    if not planner_available():
        return None, "No Gemini API key configured; planning skipped."

    try:
        raw = asyncio.run(_run(request, user_id))
    except Exception as error:  # noqa: BLE001 - planning is fallible
        return None, f"{type(error).__name__}: {error}"

    if not raw:
        return None, "Planner returned an empty response."

    try:
        return MissionPlan.model_validate(json.loads(raw)), None
    except Exception as error:  # noqa: BLE001 - malformed plan is an error
        return None, f"Planner returned an unusable plan: {error}"
