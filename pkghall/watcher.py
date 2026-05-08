"""
Watch mode: monitor a directory and auto-check Python/requirements files on save.
Requires the optional 'watchdog' package.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

from rich.console import Console

console = Console(legacy_windows=False, highlight=False)


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

    from .checker import check_packages
    from .parser import parse_file, is_parseable

    # One persistent event loop in a background thread — avoids recreating
    # the loop (and httpx connection pool) on every file-save event.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    _loop = asyncio.new_event_loop()
    _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True, name="pkghall-async")
    _loop_thread.start()

    def _run_async(packages: list[str]):
        future = asyncio.run_coroutine_threadsafe(check_packages(packages), _loop)
        return future.result(timeout=30)

    class _Handler(FileSystemEventHandler):
        def _handle(self, event) -> None:
            if event.is_directory:
                return
            path = Path(event.src_path)
            if not is_parseable(path):
                return
            _check_file(path)

        def on_modified(self, event) -> None:  # type: ignore[override]
            self._handle(event)

        def on_created(self, event) -> None:  # type: ignore[override]
            self._handle(event)

    def _check_file(path: Path) -> None:
        packages, _kind = parse_file(path)
        if not packages:
            return

        rel = path.relative_to(root) if path.is_relative_to(root) else path
        console.rule(f"[dim]{rel}[/dim]", style="dim")

        results = _run_async(packages)
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
        _loop.call_soon_threadsafe(_loop.stop)
        _loop_thread.join()
        console.print("\n[dim]Stopped.[/dim]")

    observer.join()
