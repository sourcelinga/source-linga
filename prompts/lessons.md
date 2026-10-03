You read a condensed log of a past working session between a user and an AI agent. USER lines are the user, AI lines are the agent, TOOL lines are tool calls, and TOOL ERROR lines are failures.

Extract reusable lessons, the kind that would make the next similar task go better:
- task: one line saying what the session was trying to do
- worked: approaches or tool sequences that succeeded
- failed: approaches that failed or wasted time, and why
- user_corrections: anything the user corrected, rejected or insisted on (these matter most)
- better_next_time: concrete advice for doing this kind of task better or faster

Be specific (name tools, files and rules). Use at most 5 items per list. Leave a list empty if there is nothing real to put in it. Do not invent anything.
