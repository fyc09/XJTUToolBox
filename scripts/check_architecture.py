"""Enforce the dependency rules for migrated application code."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYERS = {"api", "services", "gui", "cli", "contracts", "infrastructure", "runtime"}
QT = {"PyQt5", "PyQt6", "PySide2", "PySide6", "qfluentwidgets", "qframelesswindow"}
TRANSPORT = {"requests", "httpx", "peewee", "sqlite3", "auth", "jwxt", "gmis", "lms"}
TERMINAL = {"rich", "click", "typer"}
FORBIDDEN = {
    "api": {"services", "gui", "cli", "runtime"} | QT | TERMINAL,
    "services": {"gui", "cli", "runtime", "infrastructure"}
    | QT
    | TRANSPORT
    | TERMINAL
    | {"concurrent", "multiprocessing", "asyncio", "threading"},
    "gui": {
        "api",
        "cli",
        "infrastructure",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "qfluentwidgets",
        "qframelesswindow",
    }
    | TRANSPORT,
    "cli": {"api", "gui", "infrastructure"} | QT | TRANSPORT,
    "contracts": LAYERS - {"contracts"} | QT | TRANSPORT | TERMINAL,
    "infrastructure": {"services", "gui", "cli", "runtime"} | QT | TERMINAL,
    "runtime": {"services", "gui", "cli", "api", "infrastructure"}
    | QT
    | TRANSPORT
    | TERMINAL,
}


def violations(source: str, layer: str, *, entrypoint: bool = False) -> list[str]:
    errors = []
    tree = ast.parse(source)
    import_aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    import_aliases[alias.asname or alias.name] = "importlib"
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "importlib",
            "builtins",
        }:
            for alias in node.names:
                import_aliases[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}"
                )
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 1 and not node.module:
                modules = [alias.name for alias in node.names]
            if node.level and node.module:
                modules = [node.module]
            elif node.module:
                modules = [node.module]
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            parts = name.split(".")
            parts[0] = import_aliases.get(parts[0], parts[0])
            name = ".".join(parts)
            if name in {
                "__import__",
                "builtins.__import__",
                "importlib.import_module",
                "import_module",
            }:
                if (
                    not node.args
                    or not isinstance(node.args[0], ast.Constant)
                    or not isinstance(node.args[0].value, str)
                ):
                    errors.append(
                        f"line {node.lineno}: dynamic imports must have a literal target"
                    )
                else:
                    modules = [node.args[0].value]
        for module in modules:
            parts = module.split(".")
            target = (
                parts[1] if parts[0] == "xjtutoolbox" and len(parts) > 1 else parts[0]
            )
            if target in FORBIDDEN[layer] or target == "app":
                errors.append(
                    f"line {node.lineno}: forbidden {layer} dependency {module}"
                )
            if module == "xjtutoolbox.bootstrap" and not entrypoint:
                errors.append(
                    f"line {node.lineno}: composition root is entrypoint-only"
                )
            if layer == "api" and module.startswith("xjtutoolbox.contracts.tasks"):
                errors.append(f"line {node.lineno}: task contracts cannot enter APIs")
            if layer == "gui" and module.startswith("PySide6.QtWidgets"):
                errors.append(f"line {node.lineno}: new GUI cannot use Widgets")
        if (
            layer == "api"
            and isinstance(node, ast.Name)
            and node.id in {"Progress", "TaskContext", "RunContext"}
        ):
            errors.append(f"line {node.lineno}: API cannot use task/progress contracts")
    return errors


def check(root: Path = ROOT) -> list[str]:
    errors = []
    package = root / "xjtutoolbox"
    for layer in sorted(LAYERS):
        for path in sorted((package / layer).rglob("*.py")):
            entrypoint = layer in {"cli", "gui"} and path.name == "main.py"
            errors.extend(
                f"{path.relative_to(root)}: {error}"
                for error in violations(
                    path.read_text(encoding="utf-8"), layer, entrypoint=entrypoint
                )
            )
    for path in (package / "gui").rglob("*.qml"):
        source = path.read_text(encoding="utf-8")
        if any(
            token in source
            for token in (
                "XMLHttpRequest",
                "Qt.createQmlObject",
                "import QtQuick.Controls.Material",
                "import QtQuick.Controls.Fusion",
            )
        ):
            errors.append(f"{path.relative_to(root)}: forbidden QML transport or style")
    manifest = root / "docs/development/legacy-dependencies.json"
    if manifest.exists():
        allowed = {
            entry["path"]: set(entry["framework_imports"])
            for entry in json.loads(manifest.read_text(encoding="utf-8"))["exceptions"]
        }
        for directory, children, names in os.walk(root):
            children[:] = [
                child
                for child in children
                if not child.startswith(".")
                and child
                not in {
                    "test",
                    "scripts",
                    "xjtutoolbox",
                    "node_modules",
                    "build",
                    "dist",
                }
            ]
            for name in names:
                if not name.endswith(".py"):
                    continue
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                for node in ast.walk(tree):
                    modules = (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module]
                        if isinstance(node, ast.ImportFrom) and node.module
                        else []
                    )
                    for module in modules:
                        if module.split(".")[0] in QT and module not in allowed.get(
                            relative, set()
                        ):
                            errors.append(
                                f"{relative}: unregistered legacy framework dependency {module}"
                            )
    return errors


if __name__ == "__main__":
    errors = check()
    print("\n".join(errors) if errors else "Architecture checks passed")
    raise SystemExit(bool(errors))
