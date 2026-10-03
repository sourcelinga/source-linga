---
name: systematic-debugging
description: Use for any bug, error message, crash, failing test, broken script or "it stopped working" problem, before proposing a fix.
triggers: bug, error, crash, traceback, exception, failing, broken, not working, stopped working, fix this, keyerror, typeerror
source: obra/superpowers (skills/systematic-debugging), MIT — condensed and adapted for Source Linga
---
# Systematic debugging

Rule: find the root cause before you propose a fix. A fix for a symptom is a failure.

1. Read the error completely: message, file, line number, error code. It often names the cause.
2. Reproduce: state the exact steps or input that trigger it. If you cannot reproduce it, say what extra information would let you, and do not guess.
3. Check what changed: recent edits, new data, config, versions.
4. Trace the bad value backwards: where does it first become wrong? Fix it there, not where it crashes.
5. Compare with something similar that works and list every difference.
6. Form ONE hypothesis: "X is the cause because Y". Test it with the smallest possible change. If it is wrong, form a new one; do not stack fixes.
7. Fix: write a failing test or a one-line reproduction first, then make a single change, then show how to confirm it now passes.
8. If three fixes have failed, stop and question the design instead of trying a fourth.

Answer format:
- Cause: one or two sentences, with the evidence.
- Fix: the corrected code in full (not a description of it).
- Check: the exact command or input that proves it works.

Red flags that mean "go back to step 1": "just try changing X", several changes at once, "it's probably…", fixing without having read the whole error.
