from pathlib import Path
import pytest
from pkghall.parser import parse_python_imports, parse_requirements, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_requirements_real():
    source = "requests==2.31.0\nfastapi>=0.100.0\npydantic\n"
    pkgs = parse_requirements(source)
    assert "requests" in pkgs
    assert "fastapi" in pkgs
    assert "pydantic" in pkgs


def test_parse_requirements_skips_comments_and_blanks():
    source = "# comment\n\nrequests\n-r other.txt\ngit+https://github.com/foo/bar"
    pkgs = parse_requirements(source)
    assert pkgs == ["requests"]


def test_parse_python_imports_skips_stdlib():
    source = "import os\nimport sys\nimport json\nimport requests\n"
    pkgs = parse_python_imports(source)
    assert "os" not in pkgs
    assert "sys" not in pkgs
    assert "json" not in pkgs
    assert "requests" in pkgs


def test_parse_python_imports_from_style():
    source = "from fastapi import FastAPI\nfrom pydantic import BaseModel\n"
    pkgs = parse_python_imports(source)
    assert "fastapi" in pkgs
    assert "pydantic" in pkgs


def test_parse_python_imports_alias_normalization():
    source = "import PIL\nimport cv2\nimport sklearn\n"
    pkgs = parse_python_imports(source)
    assert "Pillow" in pkgs
    assert "opencv-python" in pkgs
    assert "scikit-learn" in pkgs


def test_parse_file_requirements(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("requests\nfastapi\n")
    pkgs, kind = parse_file(req)
    assert kind == "requirements"
    assert "requests" in pkgs


def test_parse_file_python(tmp_path):
    py = tmp_path / "app.py"
    py.write_text("import requests\nfrom fastapi import FastAPI\n")
    pkgs, kind = parse_file(py)
    assert kind == "python"
    assert "requests" in pkgs
    assert "fastapi" in pkgs


def test_fixture_bad_requirements():
    pkgs = parse_requirements((FIXTURES / "bad_requirements.txt").read_text())
    assert "requests" in pkgs
    assert "fastapi-auth-utils" in pkgs
    assert "langchain-tools-extra" in pkgs


def test_fixture_sample_ai_code():
    source = (FIXTURES / "sample_ai_code.py").read_text()
    pkgs = parse_python_imports(source)
    assert "requests" in pkgs
    assert "fastapi" in pkgs
    # stdlib excluded
    assert "os" not in pkgs
    assert "sys" not in pkgs
