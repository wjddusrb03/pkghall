"""
Checks package names against the PyPI JSON API.
Uses asyncio + httpx for concurrent requests.
"""
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


PYPI_URL = "https://pypi.org/pypi/{package}/json"
PYPI_STATS_URL = "https://pypistats.org/api/packages/{package}/recent"

# Patterns that commonly appear in LLM hallucinations
_HALLUCINATION_PATTERNS = [
    re.compile(r"-(utils?|helpers?|extras?|tools?|plus|pro|lite|mini|v\d)$", re.I),
    re.compile(r"^(langchain|openai|anthropic|fastapi|django|flask)-\w+(-\w+)+$", re.I),
    re.compile(r"^ai[-_]", re.I),
    re.compile(r"^llm[-_]", re.I),
]


@dataclass
class PackageResult:
    name: str
    exists: bool
    downloads_last_month: int | None = None
    age_days: int | None = None
    latest_version: str | None = None
    summary: str | None = None

    @property
    def is_suspicious(self) -> bool:
        """Flag as suspicious when it exists but looks shady."""
        if not self.exists:
            return False
        too_new = self.age_days is not None and self.age_days < 30
        low_traffic = (
            self.downloads_last_month is not None
            and self.downloads_last_month < 100
            and self.age_days is not None
            and self.age_days < 180
        )
        return too_new or low_traffic

    @property
    def looks_hallucinated(self) -> bool:
        """Name pattern commonly seen in LLM hallucinations."""
        return any(p.search(self.name) for p in _HALLUCINATION_PATTERNS)


async def _check_one(client: httpx.AsyncClient, name: str) -> PackageResult:
    # PyPI normalizes underscores → hyphens (PEP 503)
    normalized = name.replace("_", "-")
    url = PYPI_URL.format(package=normalized)
    try:
        resp = await client.get(url, timeout=8.0, follow_redirects=True)
    except (httpx.TimeoutException, httpx.RequestError):
        return PackageResult(name=name, exists=None)  # type: ignore[arg-type]

    if resp.status_code == 404:
        return PackageResult(name=name, exists=False)

    if resp.status_code != 200:
        return PackageResult(name=name, exists=None)  # type: ignore[arg-type]

    try:
        data = resp.json()
        info = data.get("info", {})
        releases = data.get("releases", {})

        # Age from first published release — track running minimum to avoid building a list
        age_days: int | None = None
        oldest: datetime | None = None
        for release_files in releases.values():
            for f in release_files:
                upload_time = f.get("upload_time")
                if upload_time:
                    try:
                        dt = datetime.fromisoformat(upload_time).replace(tzinfo=timezone.utc)
                        if oldest is None or dt < oldest:
                            oldest = dt
                    except ValueError:
                        pass
        if oldest is not None:
            age_days = (datetime.now(timezone.utc) - oldest).days

        return PackageResult(
            name=name,
            exists=True,
            age_days=age_days,
            latest_version=info.get("version"),
            summary=info.get("summary") or "",
        )
    except Exception:
        return PackageResult(name=name, exists=True)


async def check_packages(names: list[str], concurrency: int = 10) -> list[PackageResult]:
    """Check a list of package names against PyPI, concurrently."""
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "pkghall/0.1 (github.com/wjddusrb03/pkghall)"}

    async with httpx.AsyncClient(headers=headers) as client:
        async def bounded(name: str) -> PackageResult:
            async with sem:
                return await _check_one(client, name)

        tasks = [bounded(n) for n in names]
        return await asyncio.gather(*tasks)


def run_checks(names: list[str]) -> list[PackageResult]:
    """Synchronous wrapper — handles Windows event-loop quirk."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(check_packages(names))
