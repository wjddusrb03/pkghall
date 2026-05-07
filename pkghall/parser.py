import ast
import re
import sys
from pathlib import Path

from .aliases import IMPORT_TO_PACKAGE, STDLIB_MODULES


def _normalize(name: str) -> str:
    """import name → canonical PyPI lookup name."""
    root = name.split(".")[0]
    return IMPORT_TO_PACKAGE.get(root, root)


def _is_stdlib(name: str) -> bool:
    root = name.split(".")[0]
    return root in STDLIB_MODULES or root in sys.stdlib_module_names


def parse_python_imports(source: str) -> list[str]:
    """Extract unique package names from Python source code."""
    packages: set[str] = set()

    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    packages.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    packages.add(node.module)
    except SyntaxError:
        # Fallback: regex for broken/incomplete snippets
        for m in re.finditer(r"^(?:import|from)\s+([\w.]+)", source, re.MULTILINE):
            packages.add(m.group(1))

    result: list[str] = []
    for pkg in sorted(packages):
        if not _is_stdlib(pkg):
            result.append(_normalize(pkg))

    return sorted(set(result))


def parse_requirements(source: str) -> list[str]:
    """Parse requirements.txt content into package names."""
    packages: list[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-", "git+", "http", "--")):
            continue
        # PEP 508: package names must start with a letter (not a digit)
        m = re.match(r"^([A-Za-z]([A-Za-z0-9._-])*)", line)
        if m:
            packages.append(m.group(0))
    return sorted(set(packages))


def parse_file(path: Path) -> tuple[list[str], str]:
    """
    Auto-detect file type and return (packages, file_kind).
    file_kind is one of: 'python', 'requirements', 'unknown'
    """
    suffix = path.suffix.lower()
    name = path.name.lower()

    if suffix == ".py":
        return parse_python_imports(path.read_text(encoding="utf-8", errors="replace")), "python"

    if name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt") or (
        suffix == ".txt" and "require" in name
    ):
        return parse_requirements(path.read_text(encoding="utf-8", errors="replace")), "requirements"

    if suffix == ".txt":
        # Try as requirements first, fall back to python
        content = path.read_text(encoding="utf-8", errors="replace")
        pkgs = parse_requirements(content)
        if pkgs:
            return pkgs, "requirements"
        return parse_python_imports(content), "python"

    return [], "unknown"


def parse_stdin(content: str) -> tuple[list[str], str]:
    """Parse piped stdin — detect Python source vs requirements format."""
    # If there are any import statements, treat as Python source
    if re.search(r"^(?:import|from)\s+\w", content, re.MULTILINE):
        return parse_python_imports(content), "python"
    pkgs = parse_requirements(content)
    if pkgs:
        return pkgs, "requirements"
    return parse_python_imports(content), "python"
