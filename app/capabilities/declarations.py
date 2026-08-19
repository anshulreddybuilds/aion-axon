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
        lines.append(
            f"- {tool['name']} ({state}, risk {tool['risk']}): "
            f"{tool['description']}"
        )

    return "\n".join(lines)


def catalog_summary() -> dict[str, Any]:
    return {**registry.counts(), "capabilities": registry.list_tools()}
