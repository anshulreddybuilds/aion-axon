from app.capabilities.registry import registry
from app.tools.calculator import calculate

registry.register(
    name="calculator",
    description="Performs safe basic arithmetic calculations.",
    risk="LOW",
    function=calculate,
)

print("TOOLS REGISTERED:")

for tool in registry.list_tools():
    print(tool)
