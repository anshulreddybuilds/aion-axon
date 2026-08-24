"""Static safety screen for generated code, before anything executes.

Runs BEFORE the sandbox, not instead of it. The sandbox answers "does this
work?"; this answers "should we even run it?". Both are needed: a
candidate that tries to read credentials should be rejected on sight
rather than merely observed failing.

This is an AST screen, so it cannot be fooled by a string that merely
mentions a dangerous call -- it inspects what the code actually does.
Its limitation is the mirror image: sufficiently indirect code
(getattr chains, dynamic imports by computed name) can evade it, which is
exactly why the sandbox holds no credentials. Neither layer is trusted
alone.
"""
import ast
from dataclasses import dataclass, field

# Modules a generated capability has no legitimate reason to import.
# `os` and `sys` are deliberately included: a data-transformation skill
# does not need the process environment, and the one that asks for it is
# the one worth refusing.
FORBIDDEN_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "ctypes",
    "importlib",
    "pickle",
    "marshal",
    "multiprocessing",
    "threading",
    "google",
    "google.cloud",
    "firebase_admin",
}

FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
}


@dataclass
class ScreenResult:
    safe: bool
    findings: list[str] = field(default_factory=list)
    syntax_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "findings": self.findings,
            "syntax_error": self.syntax_error,
        }


def screen(code: str) -> ScreenResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return ScreenResult(
            safe=False,
            findings=["Candidate does not parse."],
            syntax_error=str(error),
        )

    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    findings.append(f"Forbidden import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                findings.append(f"Forbidden import from: {node.module}")

        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in FORBIDDEN_CALLS:
                findings.append(f"Forbidden call: {name}()")

        elif isinstance(node, ast.Attribute):
            # Dunder access is how sandbox escapes usually start.
            if node.attr.startswith("__") and node.attr.endswith("__"):
                findings.append(f"Dunder attribute access: {node.attr}")

        elif isinstance(node, ast.Name):
            # `x = eval; x(...)` calls the ALIAS, not `eval` -- the Call
            # branch above only ever sees the literal name at the call
            # site, so it never sees `eval` there at all. This catches
            # every bare reference to a forbidden builtin (assigned,
            # passed as an argument, returned, aliased) regardless of
            # whether it is ever actually called by its real name. Found
            # live 24 Aug: `imp = __import__; imp('os').system(...)` is a
            # complete sandbox-escape path with zero forbidden imports,
            # zero forbidden call names, and zero dunder attribute
            # access -- this was the only layer that could have caught it.
            if node.id in FORBIDDEN_CALLS:
                findings.append(f"Reference to forbidden builtin: {node.id}")

    return ScreenResult(safe=not findings, findings=sorted(set(findings)))


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""
