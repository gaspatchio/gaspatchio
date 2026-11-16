---
name: gaspatchio-skill-index
description: Use when starting any gaspatchio task and you do not yet know which gaspatchio skill applies, or before reading more than one gaspatchio skill. Names the one skill to read for each job, and says to read one SKILL.md per tool call so none is cut short.
---

# Which gaspatchio skill to read

**Read one SKILL.md per tool call.** Never `cat` several skills in one command: a tool
call's output is capped (Codex cuts at about 10,000 tokens, roughly 40 KB) and the middle
of a long output is dropped without a word. Any three gaspatchio skills together, and many
pairs, pass that line. Read the one skill for the job below, then open its `references/` files
one at a time as it tells you to. Read `gspio docs` answers the same way: where they
print, one look-up per call. Do not redirect `gspio docs` output to a file.

This index can be used standalone, and it is the only skill you need to read first.

## The job, and the skill

| Your job | Read |
|---|---|
| New to gaspatchio; set it up and run a first model | `gaspatchio-quickstart` |
| Scope a model before writing code: product, inputs, outputs | `gaspatchio-model-discovery` |
| Convert an Excel workbook into a model | `gaspatchio-workbook-conversion` |
| Write or change model code | `gaspatchio-model-building` |
| Match a model to Excel, lifelib or a vendor's numbers | `gaspatchio-model-reconciliation` |
| Review a model's quality and actuarial standards | `gaspatchio-model-review` |
| Scenarios, shocks and sensitivities | `gaspatchio-model-scenarios` |
| Chart or total a finished run from its audit file and results | `gaspatchio-results-analysis` |
| Add an accessor, or port a function from another library | `gaspatchio-extending` |

Most work runs in that order: discovery or conversion, then building, then reconciliation
and review, then scenarios. Each skill names the next one in its own Integration section.

## Red flags

| Thought | Instead |
|---|---|
| "I'll read all the skills at once to get oriented" | This table is the orientation. Read one skill. |
| "The middle of that file looked thin" | It was cut. Read it again on its own. |
| "Two skills seem to apply" | Read the earlier one in the order above; it routes you on. |

## Integration

- **Called by:** any gaspatchio task, before its first skill.
- **Routes to:** exactly one skill from the table.

## Completion gate

You have named one skill from the table and read its SKILL.md in a tool call of its own.
