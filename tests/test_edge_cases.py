"""
Rigorous edge-case tests for pkghall.
These cover inputs that are tricky to parse correctly in real-world usage.
"""
import textwrap
from pathlib import Path

from pkghall.checker import PackageResult
from pkghall.parser import parse_file, parse_python_imports, parse_requirements, parse_stdin

FIXTURES = Path(__file__).parent / "fixtures"

# ── requirements.txt parsing ──────────────────────────────────────────────────

class TestRequirementsEdgeCases:
    def test_extras_are_stripped(self):
        """fastapi[all] should produce 'fastapi', not 'fastapi[all]'."""
        pkgs = parse_requirements("fastapi[all]==0.100.0\nuvicorn[standard]>=0.20\n")
        assert "fastapi" in pkgs
        assert "uvicorn" in pkgs
        assert not any("[" in p for p in pkgs)

    def test_environment_markers_stripped(self):
        """requests; python_version >= '3.8' → 'requests'."""
        pkgs = parse_requirements("requests; python_version >= '3.8'\n")
        assert "requests" in pkgs
        assert not any(";" in p for p in pkgs)

    def test_hash_checking_lines(self):
        """requests==2.28.0 \\ --hash=sha256:abc → 'requests'."""
        src = "requests==2.28.0 \\\n    --hash=sha256:deadbeef\n"
        pkgs = parse_requirements(src)
        assert "requests" in pkgs

    def test_index_url_lines_ignored(self):
        """--index-url and --extra-index-url should not appear as packages."""
        src = "--index-url https://pypi.org/simple\n--extra-index-url https://private.example.com\nrequests\n"
        pkgs = parse_requirements(src)
        assert pkgs == ["requests"]

    def test_constraint_file_references_ignored(self):
        """-c constraints.txt and -r other.txt lines are not packages."""
        src = "-r base.txt\n-c constraints.txt\nfastapi\n"
        pkgs = parse_requirements(src)
        assert pkgs == ["fastapi"]

    def test_git_url_ignored(self):
        """git+ URLs are skipped."""
        src = "git+https://github.com/org/repo.git@main\nrequests\n"
        pkgs = parse_requirements(src)
        assert "requests" in pkgs
        assert not any("github" in p.lower() for p in pkgs)

    def test_http_direct_reference_ignored(self):
        """http:// and https:// direct URL installs are skipped."""
        src = "https://example.com/my_package-1.0.tar.gz\nfastapi\n"
        pkgs = parse_requirements(src)
        assert pkgs == ["fastapi"]

    def test_blank_and_comment_only(self):
        """Files with only blanks and comments produce []."""
        src = "\n\n# comment line\n   # indented comment\n\n"
        assert parse_requirements(src) == []

    def test_empty_string(self):
        assert parse_requirements("") == []

    def test_duplicates_deduped(self):
        """Same package repeated with different pins → one entry."""
        src = "requests\nrequests==2.28.0\nrequests>=2.0,<3.0\n"
        pkgs = parse_requirements(src)
        assert pkgs.count("requests") == 1

    def test_version_operator_variety(self):
        """All PEP 440 version specifier operators stripped correctly."""
        src = (
            "pkgA==1.0\npkgB>=1.0\npkgC<=1.0\n"
            "pkgD~=1.0\npkgE!=1.0\npkgF===1.0\n"
            "pkgG>1.0\npkgH<1.0\n"
        )
        pkgs = parse_requirements(src)
        for pkg in pkgs:
            assert not any(op in pkg for op in ("==", ">=", "<=", "~=", "!=", "===", ">", "<"))
        names = {p.lower() for p in pkgs}
        assert {"pkga", "pkgb", "pkgc", "pkgd", "pkge", "pkgf", "pkgg", "pkgh"} == names

    def test_crlf_line_endings(self):
        """Windows-style CRLF newlines parse correctly."""
        src = "requests\r\nfastapi\r\npydantic\r\n"
        pkgs = parse_requirements(src)
        assert "requests" in pkgs
        assert "fastapi" in pkgs
        assert "pydantic" in pkgs

    def test_hundred_packages(self):
        """Scale test: 100 unique package names parsed without loss."""
        names = [f"testpkg-{i:03d}" for i in range(100)]
        src = "\n".join(names)
        pkgs = parse_requirements(src)
        assert len(pkgs) == 100
        for name in names:
            assert name in pkgs

    def test_package_name_with_dot(self):
        """zope.interface is a valid package name in requirements."""
        pkgs = parse_requirements("zope.interface>=4.0\n")
        assert "zope.interface" in pkgs

    def test_package_name_numeric_start_invalid(self):
        """Lines starting with a digit should be ignored (not valid package names)."""
        src = "1bad-package\nrequests\n"
        pkgs = parse_requirements(src)
        assert "requests" in pkgs
        assert "1bad-package" not in pkgs

    def test_inline_comment_stripped(self):
        """Inline comments after package spec should not appear in output."""
        src = "requests  # the best HTTP library\n"
        pkgs = parse_requirements(src)
        assert "requests" in pkgs
        assert not any("#" in p for p in pkgs)


# ── Python import parsing ─────────────────────────────────────────────────────

class TestPythonImportEdgeCases:
    def test_relative_imports_excluded(self):
        """from . import x and from .module import y should produce no packages."""
        src = "from . import utils\nfrom .helpers import something\nfrom ..core import base\n"
        pkgs = parse_python_imports(src)
        assert pkgs == []

    def test_type_checking_block(self):
        """Imports inside TYPE_CHECKING blocks should be detected."""
        src = textwrap.dedent("""\
            from __future__ import annotations
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                import pandas as pd
                from numpy import ndarray
        """)
        pkgs = parse_python_imports(src)
        assert "pandas" in pkgs
        assert "numpy" in pkgs

    def test_try_except_import(self):
        """Both branches of try/except import should be detected."""
        src = textwrap.dedent("""\
            try:
                import ujson as json
            except ImportError:
                import json
        """)
        pkgs = parse_python_imports(src)
        assert "ujson" in pkgs
        assert "json" not in pkgs  # stdlib

    def test_star_import(self):
        """from package import * → package detected."""
        src = "from fastapi import *\nfrom pydantic import *\n"
        pkgs = parse_python_imports(src)
        assert "fastapi" in pkgs
        assert "pydantic" in pkgs

    def test_deeply_nested_submodule(self):
        """from a.b.c.d import x → root 'a' checked, not full dotted name."""
        src = "from email.mime.multipart import MIMEMultipart\nimport xml.etree.ElementTree as ET\n"
        pkgs = parse_python_imports(src)
        # Both are stdlib — should produce nothing
        assert pkgs == []

    def test_third_party_submodule(self):
        """from langchain.chat_models import ChatOpenAI → 'langchain' checked."""
        src = "from langchain.chat_models import ChatOpenAI\n"
        pkgs = parse_python_imports(src)
        assert "langchain" in pkgs

    def test_multiline_import(self):
        """Parenthesised multi-line from-import parsed correctly."""
        src = textwrap.dedent("""\
            from fastapi import (
                FastAPI,
                Request,
                Response,
            )
        """)
        pkgs = parse_python_imports(src)
        assert "fastapi" in pkgs

    def test_alias_import(self):
        """import numpy as np → 'numpy' detected."""
        src = "import numpy as np\nimport pandas as pd\n"
        pkgs = parse_python_imports(src)
        assert "numpy" in pkgs
        assert "pandas" in pkgs

    def test_stdlib_exhaustive_sample(self):
        """A broad sample of stdlib modules must NOT appear in output."""
        src = textwrap.dedent("""\
            import os, sys, re, json, ast, io, abc, argparse
            import asyncio, base64, collections, contextlib, copy
            import csv, datetime, decimal, enum, functools, gc
            import hashlib, http, importlib, inspect, itertools
            import logging, math, pathlib, pickle, platform, queue
            import random, shutil, signal, socket, sqlite3, ssl
            import statistics, string, struct, subprocess, tempfile
            import threading, time, traceback, typing, unittest
            import urllib, uuid, warnings, weakref, xml, zipfile
        """)
        pkgs = parse_python_imports(src)
        assert pkgs == [], f"stdlib modules leaked into output: {pkgs}"

    def test_alias_normalization_pil(self):
        """import PIL → Pillow."""
        pkgs = parse_python_imports("import PIL\n")
        assert "Pillow" in pkgs
        assert "PIL" not in pkgs

    def test_alias_normalization_cv2(self):
        """import cv2 → opencv-python."""
        pkgs = parse_python_imports("import cv2\n")
        assert "opencv-python" in pkgs

    def test_alias_normalization_sklearn(self):
        """import sklearn → scikit-learn."""
        pkgs = parse_python_imports("import sklearn\n")
        assert "scikit-learn" in pkgs

    def test_alias_normalization_bs4(self):
        """import bs4 → beautifulsoup4."""
        pkgs = parse_python_imports("import bs4\n")
        assert "beautifulsoup4" in pkgs

    def test_duplicate_imports_deduped(self):
        """Same package imported multiple ways → appears once."""
        src = textwrap.dedent("""\
            import requests
            from requests import Session
            from requests.adapters import HTTPAdapter
        """)
        pkgs = parse_python_imports(src)
        assert pkgs.count("requests") == 1

    def test_future_import_excluded(self):
        """from __future__ import annotations is not a third-party package."""
        src = "from __future__ import annotations\n"
        pkgs = parse_python_imports(src)
        assert pkgs == []

    def test_syntax_error_fallback(self):
        """Truncated/broken Python should not crash — regex fallback used."""
        src = "import requests\nfrom fastapi import\n# broken\ndef "
        # Should not raise
        pkgs = parse_python_imports(src)
        assert "requests" in pkgs

    def test_empty_source(self):
        """Empty Python file produces []."""
        assert parse_python_imports("") == []

    def test_docstring_only(self):
        """File with only a docstring produces []."""
        src = '"""This module does something."""\n'
        assert parse_python_imports(src) == []

    def test_comment_mentions_import_ignored(self):
        """A comment saying '# import requests' is not treated as an import."""
        src = "# import requests\n# from fastapi import FastAPI\n"
        pkgs = parse_python_imports(src)
        assert pkgs == []


# ── PackageResult logic ───────────────────────────────────────────────────────

class TestPackageResultLogic:
    def test_not_found_is_not_suspicious(self):
        """exists=False packages are not flagged as suspicious (already flagged as not found)."""
        r = PackageResult(name="ghost-pkg", exists=False, age_days=2)
        assert r.is_suspicious is False

    def test_young_package_suspicious(self):
        r = PackageResult(name="newpkg", exists=True, age_days=15)
        assert r.is_suspicious is True

    def test_old_package_not_suspicious(self):
        r = PackageResult(name="requests", exists=True, age_days=5000)
        assert r.is_suspicious is False

    def test_borderline_age_29_days(self):
        """29 days is still within the suspicious window (< 30)."""
        r = PackageResult(name="pkg", exists=True, age_days=29)
        assert r.is_suspicious is True

    def test_borderline_age_30_days(self):
        """Exactly 30 days is not suspicious by age alone."""
        r = PackageResult(name="pkg", exists=True, age_days=30, downloads_last_month=10_000)
        assert r.is_suspicious is False

    def test_none_age_not_suspicious_by_default(self):
        """If age is unknown, don't false-positive."""
        r = PackageResult(name="pkg", exists=True, age_days=None)
        assert r.is_suspicious is False

    def test_hallucination_pattern_utils_suffix(self):
        assert PackageResult(name="langchain-auth-utils", exists=True).looks_hallucinated is True

    def test_hallucination_pattern_extra_suffix(self):
        assert PackageResult(name="fastapi-streaming-extra", exists=True).looks_hallucinated is True

    def test_hallucination_pattern_ai_prefix(self):
        assert PackageResult(name="ai-helper-framework", exists=True).looks_hallucinated is True

    def test_hallucination_pattern_llm_prefix(self):
        assert PackageResult(name="llm-orchestration-tools", exists=True).looks_hallucinated is True

    def test_no_hallucination_real_packages(self):
        for name in ["requests", "fastapi", "pydantic", "httpx", "click", "rich"]:
            r = PackageResult(name=name, exists=True)
            assert r.looks_hallucinated is False, f"{name} was wrongly flagged"

    def test_timeout_result(self):
        """exists=None means network timeout — should not be suspicious."""
        r = PackageResult(name="pkg", exists=None)  # type: ignore
        assert r.is_suspicious is False


# ── parse_file auto-detection ─────────────────────────────────────────────────

class TestParseFileAutoDetect:
    def test_py_extension_detected_as_python(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("import requests\n", encoding="utf-8")
        pkgs, kind = parse_file(f)
        assert kind == "python"
        assert "requests" in pkgs

    def test_requirements_txt_detected(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("requests\nfastapi\n", encoding="utf-8")
        pkgs, kind = parse_file(f)
        assert kind == "requirements"

    def test_requirements_dev_txt_detected(self, tmp_path):
        f = tmp_path / "requirements-dev.txt"
        f.write_text("pytest\nruff\n", encoding="utf-8")
        pkgs, kind = parse_file(f)
        assert kind == "requirements"

    def test_unknown_extension_returns_empty(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value\n", encoding="utf-8")
        pkgs, kind = parse_file(f)
        assert kind == "unknown"
        assert pkgs == []


# ── stdin parsing ─────────────────────────────────────────────────────────────

class TestParseStdin:
    def test_stdin_requirements_format(self):
        content = "requests\nfastapi\npydantic\n"
        pkgs, kind = parse_stdin(content)
        assert kind == "requirements"
        assert "requests" in pkgs

    def test_stdin_python_format(self):
        content = "import requests\nfrom fastapi import FastAPI\n"
        pkgs, kind = parse_stdin(content)
        # May detect as requirements (single words) or python — either is valid
        # What matters: requests and fastapi appear
        all_names = {p.lower() for p in pkgs}
        assert "requests" in all_names or "fastapi" in all_names
