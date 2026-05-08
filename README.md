# pkghall

**Detect hallucinated (non-existent) packages in AI-generated code.**

When AI generates code, it sometimes invents package names that don't exist on PyPI. These phantom packages are either pure hallucinations or targets for [slopsquatting](https://www.aikido.dev/blog/slopsquatting-ai-package-hallucination-attacks) attacks — where attackers pre-register packages that LLMs commonly invent.

`pkghall` catches them before you run `pip install`.

## Quick demo

```
$ pkghall check requirements.txt

 Status        Package                          Age    Note
 ─────────────────────────────────────────────────────────────────────────
 ✓             httpx                            2041d  A next generation HTTP client
 ✓             fastapi                          2193d  FastAPI framework
 ✓             pydantic                         2987d  Data validation using Python type hints
 ✗ NOT FOUND   fastapi-auth-utils                  —   hallucination or typo
 ✗ NOT FOUND   langchain-tools-extra               —   hallucination or typo
 ✓             requests                         5240d  Python HTTP for Humans.

 3 ok  2 NOT FOUND

Hallucinated packages:
  ✗ fastapi-auth-utils
  ✗ langchain-tools-extra
```

## Install

```bash
pip install pkghall
```

## Usage

```bash
# Check a requirements.txt
pkghall check requirements.txt

# Scan a Python file for hallucinated imports
pkghall scan ai_generated_code.py

# Pipe support
cat output.py | pkghall scan -

# JSON output (for CI integration)
pkghall check requirements.txt --json

# Pre-commit hook (add to .pre-commit-config.yaml)
# See docs below
```

## Why this exists

Studies show ~20% of package names recommended by LLMs don't exist on PyPI ([source](https://www.aikido.dev/blog/slopsquatting-ai-package-hallucination-attacks)).
Attackers register these names to intercept installs from AI-assisted developers.

`pkghall` is a one-liner check you can run before `pip install` on any AI-generated code.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All packages found, none suspicious |
| `1` | One or more packages NOT FOUND or suspicious |

## Use as a pre-commit hook

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/wjddusrb03/pkghall
    rev: v0.1.0
    hooks:
      - id: pkghall-check   # checks requirements*.txt files
      - id: pkghall-scan    # scans Python source files
```

Then run:

```bash
pre-commit install
```

Or install automatically with the built-in command:

```bash
pkghall setup-hook
```

## Suspicious package detection

Beyond "does it exist", `pkghall` also flags:

- **Brand-new packages** (registered in the last 30 days) with very low downloads — a common attack vector
- **Hallucination-pattern names** (`langchain-*-extra`, `fastapi-*-utils`, `ai-*-framework`) that LLMs frequently invent

## License

MIT
