from dataclasses import dataclass
from typing import Any, Callable, Optional


class CapabilityNotImplemented(KeyError):
    """Raised when a capability is known but has no implementation.

    Distinct from an unknown name: this is a capability GAP, the signal
    SYNAPSE acts on. It raises rather than returning None so that a
    declared-but-unbuilt capability can never be executed by accident.
    """


@dataclass
class ToolDefinition:
    name: str
    description: str
    risk: str
    function: Optional[Callable[..., Any]] = None

    @property
    def implemented(self) -> bool:
        return self.function is not None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        risk: str,
        function: Callable[..., Any],
    ) -> None:
        """Register a capability that has real code behind it."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            risk=risk,
            function=function,
        )

    def declare(
        self,
        name: str,
        description: str,
        risk: str,
    ) -> None:
        """Declare a capability AION knows about but cannot yet perform.

        Declaring never overwrites a real implementation -- otherwise a
        seed list could silently disable working code.
        """
        existing = self._tools.get(name)

        if existing is not None and existing.implemented:
            return

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            risk=risk,
            function=None,
        )

    def unregister(self, name: str) -> bool:
        """Remove a capability entirely. True if it was present.

        This is the ROLLBACK step of the Skill Passport. An acquisition
        process with no way back is a one-way door, and a capability that
        turns out to be wrong must be removable without a redeploy.
        """
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Unknown AXON capability: {name}")

        tool = self._tools[name]

        if not tool.implemented:
            raise CapabilityNotImplemented(
                f"Capability '{name}' is declared but not implemented."
            )

        return tool

    def describe(self, name: str) -> Optional[ToolDefinition]:
        """Look a capability up without demanding it be executable."""
        return self._tools.get(name)

    def is_implemented(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool is not None and tool.implemented

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk": tool.risk,
                "implemented": tool.implemented,
            }
            for tool in self._tools.values()
        ]

    def implemented_names(self) -> list[str]:
        return sorted(
            name for name, tool in self._tools.items() if tool.implemented
        )

    def counts(self) -> dict[str, int]:
        total = len(self._tools)
        implemented = len(self.implemented_names())

        return {
            "total": total,
            "implemented": implemented,
            "declared_only": total - implemented,
        }


registry = ToolRegistry()
