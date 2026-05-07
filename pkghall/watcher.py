"""
Watch mode: monitor a directory and auto-check Python/requirements files on save.
Requires the optional 'watchdog' package.
"""
from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console

console = Console(legacy_windows=False, highlight=False)

_WATCHED_EXTENSIONS = {".py", ".txt"}
_WATCHED_NAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "requirements-prod.txt",
}


def _should_watch(path: Path) -> bool:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in _WATCHED_NAMES:
        return True
    if suffix == ".py":
        return True
    if suffix == ".txt" and "require" in name:
        return True
    return False


def run_watch(root: Path, quiet: bool) -> None:
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        console.print(
            "[red]Watch mode requires the 'watchdog' package.[/red]\n"
            "Install it with:  [bold]pip install pkghall[watch][/bold]"
        )
        raise SystemExit(1)

    from .checker import run_checks
    from .parser import parse_file

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            path = Path(event.src_path)
            if not _should_watch(path):
                return
            _check_file(path)

        def on_created(self, event):  # type: ignore[override]
            self.on_modified(event)

    def _check_file(path: Path) -> None:
        packages, kind = parse_file(path)
        if not packages:
            return

        rel = path.relative_to(root) if path.is_relative_to(root) else path
        console.rule(f"[dim]{rel}[/dim]", style="dim")

        results = run_checks(packages)
        not_found = [r for r in results if r.exists is False]
        suspicious = [r for r in results if r.is_suspicious]

        if not not_found and not suspicious:
            console.print(f"[green]  ✓ All {len(results)} package(s) OK[/green]")
        else:
            for r in not_found:
                console.print(f"  [bold red]✗ NOT FOUND[/bold red]  {r.name}")
            for r in suspicious:
                console.print(f"  [yellow]⚠ suspicious[/yellow]  {r.name}  (age {r.age_days}d)")

    observer = Observer()
    observer.schedule(_Handler(), str(root), recursive=True)
    observer.start()

    console.print(f"[bold green]pkghall watch[/bold green] monitoring [cyan]{root}[/cyan]")
    console.print("[dim]Watching .py and requirements files. Press Ctrl+C to stop.[/dim]\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[dim]Stopped.[/dim]")

    observer.join()
