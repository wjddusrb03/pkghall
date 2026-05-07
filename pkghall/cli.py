import io
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from .checker import PackageResult, run_checks
from .parser import parse_file, parse_stdin

# Force UTF-8 on Windows terminals so Unicode symbols render correctly
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(stderr=False, legacy_windows=False, highlight=False)
err_console = Console(stderr=True, legacy_windows=False, highlight=False)


def _result_row(r: PackageResult) -> tuple[Text, Text, Text, Text]:
    """Return (status, name, age, note) as Rich Text objects."""
    if r.exists is None:
        status = Text("⚠ timeout", style="yellow")
        name_text = Text(r.name)
        age_text = Text("?")
        note = Text("network error", style="dim")
    elif not r.exists:
        status = Text("✗ NOT FOUND", style="bold red")
        name_text = Text(r.name, style="bold red")
        age_text = Text("—")
        note = Text("hallucination or typo", style="red")
    elif r.is_suspicious:
        status = Text("⚠ suspicious", style="yellow")
        name_text = Text(r.name, style="yellow")
        age_text = Text(f"{r.age_days}d" if r.age_days is not None else "?")
        note = Text("new or unpopular — verify before installing", style="yellow")
    else:
        status = Text("✓", style="green")
        name_text = Text(r.name, style="dim")
        age_text = Text(f"{r.age_days}d" if r.age_days is not None else "?", style="dim")
        note = Text(r.summary[:60] if r.summary else "", style="dim")

    return status, name_text, age_text, note


def _print_table(results: list[PackageResult]) -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Status", min_width=12)
    table.add_column("Package", min_width=30)
    table.add_column("Age", min_width=6, justify="right")
    table.add_column("Note", min_width=30)

    for r in sorted(results, key=lambda x: (x.exists is not False, x.exists is None, x.name)):
        table.add_row(*_result_row(r))

    console.print(table)


def _print_summary(results: list[PackageResult]) -> int:
    """Print summary line. Returns exit code (0 = all OK, 1 = problems found)."""
    not_found = [r for r in results if r.exists is False]
    suspicious = [r for r in results if r.is_suspicious]
    timeout = [r for r in results if r.exists is None]
    ok = [r for r in results if r.exists is True and not r.is_suspicious]

    parts: list[str] = []
    if ok:
        parts.append(f"[green]{len(ok)} ok[/green]")
    if not_found:
        parts.append(f"[bold red]{len(not_found)} NOT FOUND[/bold red]")
    if suspicious:
        parts.append(f"[yellow]{len(suspicious)} suspicious[/yellow]")
    if timeout:
        parts.append(f"[yellow]{len(timeout)} timeout[/yellow]")

    console.print("  ".join(parts))

    if not_found:
        console.print()
        console.print("[bold red]Hallucinated packages:[/bold red]")
        for r in not_found:
            console.print(f"  [red]✗[/red] {r.name}")

    return 1 if (not_found or suspicious) else 0


def _output_json(results: list[PackageResult]) -> None:
    output = []
    for r in results:
        output.append({
            "name": r.name,
            "exists": r.exists,
            "age_days": r.age_days,
            "latest_version": r.latest_version,
            "is_suspicious": r.is_suspicious,
            "summary": r.summary,
        })
    click.echo(json.dumps(output, indent=2))


def _run(packages: list[str], as_json: bool, quiet: bool) -> int:
    if not packages:
        err_console.print("[yellow]No packages found to check.[/yellow]")
        return 0

    if not quiet and not as_json:
        err_console.print(f"[dim]Checking {len(packages)} package(s) on PyPI…[/dim]")

    results = run_checks(packages)

    if as_json:
        _output_json(results)
        not_found = [r for r in results if r.exists is False]
        return 1 if not_found else 0

    _print_table(results)
    return _print_summary(results)


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(prog_name="pkghall")
def main() -> None:
    """pkghall — detect hallucinated packages in AI-generated code.

    \b
    Examples:
      pkghall check requirements.txt
      pkghall scan ai_output.py
      cat output.py | pkghall scan -
      pkghall check requirements.txt --json
    """


@main.command()
@click.argument("file", type=click.Path(allow_dash=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress messages")
def check(file: str, as_json: bool, quiet: bool) -> None:
    """Check a requirements.txt (or any text file) for hallucinated packages."""
    if file == "-":
        content = sys.stdin.read()
        from .parser import parse_stdin
        packages, kind = parse_stdin(content)
    else:
        path = Path(file)
        if not path.exists():
            err_console.print(f"[red]File not found:[/red] {file}")
            raise SystemExit(1)
        packages, kind = parse_file(path)

    if not as_json and not quiet:
        err_console.print(f"[dim]Parsed as [bold]{kind}[/bold] — found {len(packages)} package name(s)[/dim]")

    raise SystemExit(_run(packages, as_json, quiet))


@main.command()
@click.argument("file", type=click.Path(allow_dash=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress messages")
def scan(file: str, as_json: bool, quiet: bool) -> None:
    """Scan a Python source file for hallucinated imports."""
    if file == "-":
        content = sys.stdin.read()
        from .parser import parse_python_imports
        packages = parse_python_imports(content)
        kind = "python"
    else:
        path = Path(file)
        if not path.exists():
            err_console.print(f"[red]File not found:[/red] {file}")
            raise SystemExit(1)
        packages, kind = parse_file(path)

    if not as_json and not quiet:
        err_console.print(f"[dim]Scanned [bold]{file}[/bold] as {kind} — found {len(packages)} import(s)[/dim]")

    raise SystemExit(_run(packages, as_json, quiet))


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--quiet", "-q", is_flag=True, help="Suppress startup banner")
def watch(path: str, quiet: bool) -> None:
    """Watch a directory and auto-check files when they are saved.

    \b
    Watches for changes to .py files and requirements*.txt files.
    Runs pkghall automatically on every save.

    Requires:  pip install pkghall[watch]
    """
    from .watcher import run_watch
    run_watch(Path(path).resolve(), quiet)


@main.command("setup-hook")
@click.option(
    "--type",
    "hook_type",
    type=click.Choice(["pre-commit", "git-hook"], case_sensitive=False),
    default="pre-commit",
    show_default=True,
    help="Which kind of hook to install",
)
def setup_hook(hook_type: str) -> None:
    """Install pkghall as a git hook so it runs before every commit.

    \b
    pre-commit (recommended):
      Adds pkghall to .pre-commit-config.yaml.
      Requires 'pre-commit' to be installed.

    git-hook:
      Writes a raw .git/hooks/pre-commit shell script.
      Works without any extra tools.
    """
    import shutil

    if hook_type == "pre-commit":
        config_path = Path(".pre-commit-config.yaml")
        hook_snippet = (
            "\n# pkghall: detect hallucinated packages\n"
            "  - repo: https://github.com/wjddusrb03/pkghall\n"
            "    rev: v0.1.0\n"
            "    hooks:\n"
            "      - id: pkghall-check\n"
            "      - id: pkghall-scan\n"
        )

        if config_path.exists():
            existing = config_path.read_text(encoding="utf-8")
            if "pkghall" in existing:
                console.print("[yellow]pkghall hook already present in .pre-commit-config.yaml[/yellow]")
                return
            with config_path.open("a", encoding="utf-8") as f:
                f.write(hook_snippet)
            console.print(f"[green]✓ Appended pkghall hooks to[/green] {config_path}")
        else:
            config_path.write_text(
                "repos:\n" + hook_snippet.lstrip("\n"), encoding="utf-8"
            )
            console.print(f"[green]✓ Created[/green] {config_path}")

        if shutil.which("pre-commit"):
            console.print("[dim]Run [bold]pre-commit install[/bold] to activate.[/dim]")
        else:
            console.print(
                "[yellow]'pre-commit' not found. Install it:[/yellow]\n"
                "  pip install pre-commit && pre-commit install"
            )

    else:  # git-hook
        hooks_dir = Path(".git") / "hooks"
        if not hooks_dir.exists():
            console.print("[red]Not a git repository (no .git/hooks directory found).[/red]")
            raise SystemExit(1)

        hook_path = hooks_dir / "pre-commit"
        script = (
            "#!/bin/sh\n"
            "# pkghall: check for hallucinated packages before commit\n"
            "set -e\n\n"
            "# Find staged requirements files\n"
            "REQ=$(git diff --cached --name-only --diff-filter=ACM | grep -E 'requirements.*\\.txt$' || true)\n"
            "if [ -n \"$REQ\" ]; then\n"
            "  echo \"[pkghall] Checking staged requirements files...\"\n"
            "  echo \"$REQ\" | xargs pkghall check --quiet\n"
            "fi\n\n"
            "# Find staged Python files\n"
            "PY=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.py$' || true)\n"
            "if [ -n \"$PY\" ]; then\n"
            "  echo \"[pkghall] Scanning staged Python files...\"\n"
            "  echo \"$PY\" | xargs pkghall scan --quiet\n"
            "fi\n"
        )

        if hook_path.exists():
            console.print("[yellow]A pre-commit hook already exists.[/yellow]")
            if not click.confirm("Overwrite it?"):
                return

        hook_path.write_text(script, encoding="utf-8")
        # Make executable (no-op on Windows but harmless)
        try:
            import stat
            hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        console.print(f"[green]✓ Installed git hook at[/green] {hook_path}")
        console.print("[dim]pkghall will now run automatically before every commit.[/dim]")
