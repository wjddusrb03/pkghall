# pkghall

**AI가 생성한 코드에서 존재하지 않는 패키지를 찾아냅니다.**

[![CI](https://github.com/wjddusrb03/pkghall/actions/workflows/ci.yml/badge.svg)](https://github.com/wjddusrb03/pkghall/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 문제: AI는 존재하지 않는 패키지를 당당하게 추천한다

ChatGPT, Claude, Copilot 같은 LLM은 코드를 생성할 때 **실제로 PyPI에 없는 패키지 이름을 만들어내는** 경우가 있습니다. 이를 **패키지 환각(package hallucination)** 이라고 부릅니다.

연구에 따르면 LLM이 추천하는 패키지의 **약 20%가 PyPI에 존재하지 않습니다** ([출처](https://www.aikido.dev/blog/slopsquatting-ai-package-hallucination-attacks)).

이것이 단순한 오류로 끝나지 않는 이유가 있습니다 — **슬롭스쿼팅(slopsquatting)** 공격입니다.

```
LLM이 "langchain-utils-extra" 라고 추천
    ↓
실제로는 PyPI에 없는 이름
    ↓
공격자가 미리 해당 이름으로 악성 패키지를 등록해둠
    ↓
개발자가 pip install langchain-utils-extra 실행
    ↓
악성 코드 실행, 자격 증명 탈취
```

`pkghall`은 `pip install`을 실행하기 **전에** 패키지 이름을 검증해서 이 공격을 차단합니다.

---

## 동작 방식

1. Python 소스 파일(`.py`) 또는 `requirements.txt`에서 패키지 이름을 추출합니다.
2. 표준 라이브러리 모듈(`os`, `sys`, `json` 등)과 잘 알려진 import 별칭(`cv2` → `opencv-python`, `PIL` → `Pillow` 등)을 자동으로 제외합니다.
3. 각 패키지를 **PyPI JSON API**에 비동기로 병렬 조회합니다 (기본 동시 요청 10개).
4. 존재하지 않는 패키지, 신규 등록 패키지, 다운로드 수가 낮은 패키지를 분류하여 보고합니다.

---

## 설치

Python 3.11 이상이 필요합니다.

```bash
git clone https://github.com/wjddusrb03/pkghall.git
cd pkghall
pip install -e .
```

파일 감시(watch) 모드까지 사용하려면:

```bash
pip install -e ".[watch]"
```

개발 환경 (테스트 포함):

```bash
pip install -e ".[dev]"
```

---

## 명령어

### `pkghall check` — requirements 파일 검사

`requirements.txt` 형식의 파일을 받아 각 패키지가 PyPI에 실제로 존재하는지 확인합니다.

```bash
pkghall check requirements.txt
```

**출력 예시:**

```
Parsed as requirements — found 6 package name(s)
Checking 6 package(s) on PyPI…

 Status        Package                          Age    Note
 ─────────────────────────────────────────────────────────────────────────────────
 ✓             httpx                            2041d  A next generation HTTP client
 ✓             fastapi                          2193d  FastAPI framework, high performance
 ✓             pydantic                         2987d  Data validation using Python type hints
 ✓             requests                         5240d  Python HTTP for Humans.
 ✗ NOT FOUND   fastapi-auth-utils                  —   hallucination or typo
 ✗ NOT FOUND   langchain-tools-extra               —   hallucination or typo

 4 ok  2 NOT FOUND

Hallucinated packages:
  ✗ fastapi-auth-utils
  ✗ langchain-tools-extra
```

**지원하는 파일 형식:**

- `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt`
- `requirements-*.txt` 형태의 모든 파일
- `extras` 지정 무시: `fastapi[all]==0.100.0` → `fastapi` 로만 검사
- 환경 마커 무시: `numpy; python_version >= "3.9"` → `numpy` 로만 검사
- `git+https://...`, `--index-url`, `#` 주석 줄 자동 제외

```bash
# 표준 입력(stdin)으로도 사용 가능
cat requirements.txt | pkghall check -
```

---

### `pkghall scan` — Python 소스 파일 검사

`.py` 파일에서 `import` 문을 파싱하여 실제로 존재하는 패키지인지 확인합니다.

```bash
pkghall scan ai_generated_code.py
```

**출력 예시:**

```
Scanned ai_generated_code.py as python — found 8 import(s)
Checking 8 package(s) on PyPI…

 Status        Package                          Age    Note
 ─────────────────────────────────────────────────────────────────────────────────
 ✓             httpx                            2041d  A next generation HTTP client
 ✓             numpy                            5890d  Fundamental package for array computing
 ✓             pandas                           5621d  Powerful data structures for data analysis
 ✗ NOT FOUND   openai-utils-pro                    —   hallucination or typo
 ⚠ suspicious  ai-helper-framework               12d   new or unpopular — verify before installing

 3 ok  1 NOT FOUND  1 suspicious
```

**파싱 방식:**

- `import requests` → `requests`
- `from PIL import Image` → `Pillow` (import 별칭 자동 변환)
- `from sklearn.ensemble import ...` → `scikit-learn` (자동 변환)
- `import os, sys, json` → 표준 라이브러리이므로 제외
- 상대 import (`from .utils import ...`) 제외
- `TYPE_CHECKING` 블록, `try/except ImportError` 블록 내 import도 포함
- 문법 오류가 있는 파일은 정규식 폴백으로 처리

```bash
# stdin 지원
cat ai_code.py | pkghall scan -
```

---

### `pkghall watch` — 파일 감시 모드

디렉토리를 감시하다가 `.py` 파일이나 `requirements*.txt`가 저장될 때마다 자동으로 검사합니다. AI 코드를 에디터에서 붙여넣는 즉시 결과를 볼 수 있습니다.

```bash
# 현재 디렉토리 감시
pkghall watch

# 특정 디렉토리 감시
pkghall watch ./my-project
```

**출력 예시 (파일 저장 시):**

```
pkghall watch monitoring /home/user/my-project
Watching .py and requirements files. Press Ctrl+C to stop.

──────────── requirements.txt ────────────
  ✓ All 5 package(s) OK

──────────── ai_code.py ────────────
  ✗ NOT FOUND  openai-plugin-extra
  ⚠ suspicious  llm-agent-tools  (age 8d)
```

> `watchdog` 패키지가 필요합니다: `pip install -e ".[watch]"`

---

### `pkghall setup-hook` — git hook 자동 설치

커밋 전에 자동으로 pkghall이 실행되도록 설정합니다.

**pre-commit 프레임워크 사용 (권장):**

```bash
pkghall setup-hook --type pre-commit
```

`.pre-commit-config.yaml`에 자동으로 아래 내용을 추가합니다:

```yaml
repos:
  - repo: https://github.com/wjddusrb03/pkghall
    rev: v0.1.0
    hooks:
      - id: pkghall-check   # requirements*.txt 파일 검사
      - id: pkghall-scan    # Python 소스 파일 검사
```

이후 한 번만 실행:

```bash
pre-commit install
```

**raw git hook 사용 (pre-commit 없이):**

```bash
pkghall setup-hook --type git-hook
```

`.git/hooks/pre-commit` 스크립트를 직접 작성합니다. `pre-commit` 프레임워크 없이도 동작합니다.

---

## 공통 옵션

| 옵션 | 설명 |
|------|------|
| `--json` | JSON 형식으로 출력 (CI 파이프라인 연동용) |
| `--quiet` / `-q` | 진행 메시지 숨김 (스크립트 사용 시) |

---

## JSON 출력

`--json` 플래그를 붙이면 구조화된 JSON을 반환합니다. CI에서 결과를 파싱하거나 다른 도구와 연동할 때 사용합니다.

```bash
pkghall check requirements.txt --json
```

```json
[
  {
    "name": "httpx",
    "exists": true,
    "age_days": 2041,
    "latest_version": "0.27.0",
    "is_suspicious": false,
    "summary": "A next generation HTTP client"
  },
  {
    "name": "fastapi-auth-utils",
    "exists": false,
    "age_days": null,
    "latest_version": null,
    "is_suspicious": false,
    "summary": null
  }
]
```

**필드 설명:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | 패키지 이름 |
| `exists` | bool \| null | `true`=존재, `false`=없음, `null`=네트워크 오류 |
| `age_days` | int \| null | 최초 릴리스 후 경과 일수 |
| `latest_version` | string \| null | 최신 버전 |
| `is_suspicious` | bool | 의심 패키지 여부 |
| `summary` | string \| null | PyPI 패키지 요약 |

---

## 의심 패키지 탐지 기준

단순히 "존재 여부"를 넘어서, 다음 조건을 만족하면 **⚠ suspicious** 로 표시합니다.

| 조건 | 기준 | 이유 |
|------|------|------|
| 신규 등록 | 최초 릴리스 후 30일 미만 | 슬롭스쿼팅 공격은 LLM이 자주 생성하는 이름을 미리 등록해두는 방식 |
| 낮은 트래픽 | 월 다운로드 100 미만 + 출시 180일 미만 | 실제로 쓰이지 않는 패키지가 이름만 선점한 경우 |

의심 패키지는 자동으로 차단하지 않습니다. 직접 PyPI 페이지를 확인하고 판단하세요.

---

## import 별칭 자동 변환

Python에서 import 이름과 PyPI 패키지 이름이 다른 경우가 많습니다. pkghall은 180개 이상의 별칭을 자동으로 변환합니다.

| import 이름 | PyPI 패키지 이름 |
|------------|----------------|
| `PIL` | `Pillow` |
| `cv2` | `opencv-python` |
| `sklearn` | `scikit-learn` |
| `bs4` | `beautifulsoup4` |
| `yaml` | `PyYAML` |
| `dotenv` | `python-dotenv` |
| `serial` | `pyserial` |
| `Crypto` | `pycryptodome` |
| `google.cloud` | `google-cloud` |
| ... | (총 180개+) |

---

## CI/CD 연동 (GitHub Actions)

```yaml
# .github/workflows/security.yml
name: pkghall security check

on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install pkghall
        run: |
          git clone https://github.com/wjddusrb03/pkghall.git
          pip install -e ./pkghall
      - name: Check requirements
        run: pkghall check requirements.txt
      - name: Scan source files
        run: pkghall scan src/
```

`pkghall`은 문제가 있을 때 **exit code 1**을 반환하므로 CI가 자동으로 실패 처리합니다.

---

## 종료 코드

| 코드 | 의미 |
|------|------|
| `0` | 모든 패키지가 존재하고 의심스럽지 않음 |
| `1` | 하나 이상의 패키지가 존재하지 않거나 의심스러움 |

---

## 요구 사항

- Python 3.11 이상
- 인터넷 연결 (PyPI API 조회)
- watchdog 4.0+ (watch 모드 사용 시만)

---

## 한계

- **비공개 패키지**: 사내 패키지 인덱스나 PyPI에 없는 사설 패키지는 "NOT FOUND"로 표시될 수 있습니다.
- **네트워크 오류**: PyPI 조회에 실패하면 `⚠ timeout`으로 표시되며 종료 코드 0을 반환합니다 (오탐 방지).
- **Conda 패키지**: PyPI를 기준으로만 검사합니다. Conda 전용 패키지는 지원하지 않습니다.
- **동적 import**: `importlib.import_module("pkg")` 형태의 동적 import는 감지하지 못합니다.

---

## 라이선스

MIT
