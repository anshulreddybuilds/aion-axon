"""The registry, expressed as Gemini function declarations.

One source of truth: capabilities are declared once in the registry and
projected into Gemini's schema here. A capability the registry does not
know about cannot be offered to the model, and a capability the model
invents cannot be executed -- `registry.get()` is still the only way to
reach code.

Declared-but-unimplemented capabilities are included on purpose. The
planner needs to see the shape of the job to recognise it, which is what
produces an honest capability gap instead of a hallucinated success.
"""
import inspect
from typing import Any

from google.genai import types

from app.capabilities.registry import registry


def function_declarations() -> list[types.FunctionDeclaration]:
    declarations = []

    for tool in registry.list_tools():
        suffix = (
            "" if tool["implemented"]
            else " [NOT YET IMPLEMENTED - AION cannot perform this today]"
        )

        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=f"{tool['description']}{suffix}",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "args": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                            description="Positional string arguments.",
                        ),
                    },
                ),
            )
        )

    return declarations


def as_gemini_tool() -> types.Tool:
    return types.Tool(function_declarations=function_declarations())


def capability_catalog() -> str:
    """A plain-text catalog for the planner's prompt.

    The planner is given the catalog as text rather than as callable
    tools because it must PLAN, not execute. Execution belongs to the
    gate.
    """
    lines = []

    for tool in registry.list_tools():
        state = "AVAILABLE" if tool["implemented"] else "NOT IMPLEMENTED"
        signature = _signature_of(tool["name"])

        lines.append(
            f"- {tool['name']}{signature} ({state}, risk {tool['risk']}): "
            f"{tool['description']}"
        )

    return "\n".join(lines)


def _signature_of(name: str) -> str:
    """The capability's real parameter names, for the planner's prompt.

    The catalog used to give the planner a name and a sentence and nothing
    else, so it had to guess each capability's arguments — and positional
    arguments punish a wrong guess silently. Found live 22 Aug: the
    planner called write_brief(rows, cagr_result), but the second
    parameter is `title`, so the mission's headline finding was rendered
    as the document's TITLE and the brief opened with a raw JSON blob.
    Every step reported EXECUTED. The artifact was simply wrong.

    Acquired capabilities are sandbox proxies whose signature is
    `(*args)`, which tells the planner nothing. Those are returned bare
    rather than with a misleading `(*args)`: an honest silence beats a
    confident non-answer, which is the rule the rest of this system runs
    on.
    """
    described = registry.describe(name)

    if described is None or described.function is None:
        return ""

    try:
        parameters = inspect.signature(described.function).parameters
    except (TypeError, ValueError):  # builtins and C callables
        return ""

    if any(
        p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters.values()
    ):
        return ""

    rendered = ", ".join(
        param if p.default is inspect.Parameter.empty
        else f"{param}=<optional>"
        for param, p in parameters.items()
    )

    return f"({rendered})"


def catalog_summary() -> dict[str, Any]:
    return {**registry.counts(), "capabilities": registry.list_tools()}
