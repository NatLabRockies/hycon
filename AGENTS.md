# Agents Instructions

This file contains additional guidance for AI agents and other AI editors including AI PR reviewers.

## Project Context

- Hycon is an open-source library of controllers for hybrid power plants
- Hycon is often paired with Hercules (hybrid power plant simulator) and ENPAX (cost modeling).

## Rules for agents

- Prefer simple, concise implementations over clever abstractions.
- Keep changes scoped to the requested task. Avoid broad refactors unless requested.
- Reduce the verbosity of your comments, more text and detail is not always better.
- If `.venv/` exists, use `.venv/bin/python` for running examples, tests, etc. (e.g. `.venv/bin/python -m pytest`).
- Append "(AI)" to inline comments written by an agent (not docstrings).

## Python Style

- Use Google-style docstrings for public functions, classes, and methods
- Docstring `Args` entries should state units where relevant
  (e.g. `energy_capacity (float): Deliverable energy capacity in kWh.`).
- Format with Ruff.
- Run `pre-commit run --all-files` before finishing.
- Favor readability first: straightforward control flow, minimal nesting, clear
  names. Avoid heavy abstractions.

## Testing and formatting

- Test: `.venv/bin/python -m pytest tests/` when `.venv/` exists; otherwise `pytest .` (or a single file, e.g. `pytest tests/battery_controllers_test.py`).
- Pre-commit: `pre-commit run --all-files`
- Write self-contained test functions, comprehensible to a human reviewer, with a short comment stating the purpose.
- Focus on core behavior and catching regressions rather than exhaustive edge cases;
  prefer fewer, targeted tests.

## Git rules

- Agents can use information gathering commands like diff
- Agents may never push, pull or fetch
- Agents should avoid committing. Agents must ask for explicit permission before making any commit.

## Communication

- Avoid flattery, avoid filler phrases, prefer technical clarity over marketing tone.
