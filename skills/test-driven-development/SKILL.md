---
name: test-driven-development
description: Use when writing a new function, script or feature, or changing code behaviour, so the code comes with a test that proves it works.
triggers: write a function, python function, write a script, def, unit test, tests for, implement, write a python, function that
source: obra/superpowers (skills/test-driven-development), MIT — condensed and adapted for Source Linga
---
# Test-driven development

Cycle: RED → GREEN → REFACTOR.
1. RED: write the smallest test that describes the behaviour you want. It must fail first, for the right reason (missing behaviour, not a typo).
2. GREEN: write the simplest code that makes that test pass. Nothing extra.
3. REFACTOR: tidy names and duplication while the tests stay green.
Repeat for the next behaviour.

Good tests:
- One behaviour per test, named after it: test_short_code_has_no_year.
- Real inputs and exact expected outputs, including edge cases (empty input, missing parts, very long values, wrong types).
- No testing of internals or mocks when a real call is cheap.

When answering a coding request:
- Give the tests (plain assert statements are fine) together with the code.
- Mentally run every assert against your code line by line before replying; if one would fail, fix the code first.
- If the request says "output only the code", put the asserts after the function only when that still satisfies the request; otherwise check them silently.

A bug fix starts with a test that reproduces the bug.
