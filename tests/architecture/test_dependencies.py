import ast
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "vetorthoplan"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_does_not_depend_on_outer_layers_or_frameworks() -> None:
    forbidden_prefixes = (
        "fastapi",
        "pydantic",
        "sqlalchemy",
        "vetorthoplan.api",
        "vetorthoplan.application",
        "vetorthoplan.infrastructure",
    )

    violations: list[str] = []
    for path in (SRC / "domain").rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(SRC)} imports {module}")

    assert violations == []

