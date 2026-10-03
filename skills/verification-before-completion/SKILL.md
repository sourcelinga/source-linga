---
name: verification-before-completion
description: Use before saying something is done, fixed, working, passing or correct; when reviewing whether a task, script, change or claim really succeeded.
triggers: is it done, verify, did it work, did the tests pass, confirm it works, check my work
source: obra/superpowers (skills/verification-before-completion), MIT — condensed and adapted for Source Linga
---
# Verification before completion

Rule: evidence before claims. Never say "done", "fixed" or "works" without proof you have actually seen.

Before any success claim:
1. Name the check that would prove it (a command, a test, a calculation, a file to open).
2. Run it, or, if you cannot run it, give the user the exact check to run and say the result is not yet verified.
3. Read the whole result: exit code, number of failures, the actual output.
4. Only then state the result, and quote the evidence ("12/12 tests pass", "calculate returned 7.42").

What does NOT count as proof:
- "It should work now", "looks correct", confidence.
- An earlier run, before the last change.
- A tool or agent saying it succeeded, without checking the result.
- One passing check when the claim covers several requirements: re-read the request and tick off each requirement.

Words that signal an unverified claim: should, probably, seems to, Great!, Done! — replace them with the evidence or with "not verified yet".
For numbers, use the calculate tool rather than mental arithmetic.
