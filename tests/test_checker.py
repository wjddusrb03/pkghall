import pytest

from pkghall.checker import PackageResult, run_checks


@pytest.mark.integration
def test_real_package_exists():
    """requests is a real, popular package."""
    results = run_checks(["requests"])
    assert len(results) == 1
    r = results[0]
    assert r.exists is True
    assert r.is_suspicious is False


@pytest.mark.integration
def test_nonexistent_package():
    """A clearly made-up package name should return exists=False."""
    results = run_checks(["this-package-does-not-exist-xyzzy-42"])
    assert len(results) == 1
    assert results[0].exists is False


@pytest.mark.integration
def test_multiple_packages():
    """Mix of real and fake packages."""
    results = run_checks(["requests", "fastapi", "totally-fake-package-zz99"])
    result_map = {r.name: r for r in results}
    assert result_map["requests"].exists is True
    assert result_map["fastapi"].exists is True
    assert result_map["totally-fake-package-zz99"].exists is False


def test_package_result_suspicious():
    """A brand-new package with no history should flag as suspicious."""
    r = PackageResult(name="fresh-pkg", exists=True, age_days=5, downloads_last_month=0)
    assert r.is_suspicious is True


def test_package_result_not_suspicious():
    """An old, popular package should not be suspicious."""
    r = PackageResult(name="requests", exists=True, age_days=4000, downloads_last_month=50_000_000)
    assert r.is_suspicious is False


def test_package_result_hallucination_pattern():
    """Names matching common LLM hallucination patterns should flag."""
    r = PackageResult(name="langchain-auth-utils-extra", exists=True, age_days=None)
    assert r.looks_hallucinated is True

    r2 = PackageResult(name="requests", exists=True, age_days=None)
    assert r2.looks_hallucinated is False
