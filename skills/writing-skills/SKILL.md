---
name: writing-skills
description: Use when creating, improving, rewriting or reviewing an AI skill, SKILL.md, agent instruction, system prompt or workflow instruction.
triggers: skill, skill.md, agent instruction, system prompt, prompt for, instruction file, improve this instruction, instruction, agent prompt, prompt
trigger_boost: 0.2
source: obra/superpowers (skills/writing-skills), MIT — condensed and adapted for Source Linga
---
# Writing and improving skills

A skill is a reusable instruction an AI loads when a matching task appears. A good one changes behaviour reliably.

Front matter:
- name: short-kebab-case.
- description: starts with "Use when…" and lists the situations and words that should trigger it. It is how the skill gets found, so include the user's own words.

Body:
1. One-line core rule (what must always or never happen).
2. Steps or a checklist in the order they are done. Use exact actions, tools, names and limits rather than adjectives.
3. Output format: what the answer should look like.
4. Red flags: the excuses or shortcuts that mean the rule is being broken.
5. One short good-vs-bad example when misunderstanding is likely. Never invent facts for it.
6. A final "Check before finishing" step: what to verify or review before the work is handed over.

Test it like code: think of a task where an AI without the skill would fail; check that the skill makes it pass, and that it doesn't trigger on unrelated tasks.

Cut: history, motivation, repetition, anything that does not change what the AI does. Keep it under about 400 words; move long reference material elsewhere.

When improving an existing skill, keep what works, fix vague words, add the missing verification step, and output the complete new skill.
