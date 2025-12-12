# Day 15: Prompt Interfaces for Teams: Stop Rewriting the Same Prompts

The first time a team tries “AI for PR reviews,” it feels like free speed.

Then five people use five different prompts, and the results stop being comparable.

If five people ask the model for the same kind of output, you’ll get five different formats, five different levels of rigor, and five different definitions of “done.” The result looks like speed until you try to merge it into a real workflow.

The fix is to treat prompts like interfaces.

---

## The Shift: From Prompts to Contracts

In code, you don’t ship a feature by pasting random snippets into production. You define an interface, decide what inputs are allowed, and enforce outputs you can depend on.

Team prompting works the same way.

A good prompt interface makes three things explicit:

- **Inputs:** what the model needs (context, constraints, artifacts)
- **Outputs:** what you expect back (format, fields, quality bar)
- **Verification:** how you check it (tests, rubrics, or review steps)

---

## Proof Artifact: The Same Task, Two Outcomes

Here is a tiny example of why teams get inconsistent results.

**Loose request**

```text
Help me review this PR.
```

**Interface-style request**

```text
Role: You are a senior reviewer.
Input: I will paste a diff.
Task: Identify the highest-risk issues.
Constraints:
- Focus on correctness, security, and maintainability.
- Do not comment on formatting unless it changes meaning.
Output:
1) A short risk summary (3 bullets max)
2) A checklist of review items (7–10)
3) The top 3 questions to ask the author
Verification:
- If the diff is too large to review safely in one pass, say so and ask for a narrower scope.
```

Both “work.” Only one is reusable.

Here is the deeper point: the interface-style version produces an output you can review in minutes, and the loose version produces an output you have to interpret.

---

## Build a Prompt Component Library

Use this when your team repeats the same tasks: PR review, incident writeups, meeting notes, design critiques, sprint planning.

Create components you can plug together.

Here is a complete example you can paste into a team doc and reuse:

```text
Role: You are a senior reviewer.

Context:
- Repo: [name]
- Change type: [bugfix | refactor | feature]
- Constraints: [no new deps, performance sensitive, etc]

Task:
- Review the diff for correctness, security, and maintainability.

Output:
1) Risk summary (3 bullets)
2) Review checklist (7–10 items)
3) Top questions for the author (3)

Verification:
- If evidence is missing, list exactly what you need.
- If you are uncertain, say what would reduce uncertainty.
```

### Component: Context Block

```text
Context:
- Product: [what this is]
- Environment: [language, platform, constraints]
- Goal: [what success looks like]
- Non-goals: [what to avoid]
```

### Component: Output Contract

```text
Output:
- Format: [table | bullets | JSON | diff]
- Required sections: [A, B, C]
- Length constraints: [max bullets/words]
```

### Component: Verification Hook

```text
Verification:
- List 3 checks I can run to validate the output.
- If you are uncertain, state the uncertainty and what evidence would reduce it.
```

The point is consistency, without removing judgment.

---

## One Task, One Golden Example

Use this when people keep debating “what good looks like.”

Pick one example output that your team agrees is high quality.

Then ask the model to imitate it.

```text
Here is an example of a great output.

[PASTE GOLDEN EXAMPLE]

Now do the same task for this new input:

[PASTE NEW INPUT]

Constraints:
- Match the structure, tone, and level of rigor of the example.
- Do not invent details.
```

This is the fastest way to align taste without endless style arguments.

---

## Team Defaults (Safety and Scope)

Use this when AI starts touching real decisions.

Set defaults that reduce risk without slowing people down.

```text
Team defaults:
- If a prompt involves security, compliance, legal, or customer data, require explicit review steps.
- Require assumptions to be listed explicitly.
- Require citations when making factual claims.
- Require “stop and ask” if the input is incomplete.
```

These defaults should live next to your engineering standards.

---

## What You Still Own

Prompt interfaces will make the model more consistent.

Correctness still comes from review, tests, and ownership.

Keep human ownership of:

- risk decisions
- merging changes
- anything you would not approve without reading line by line

---

## A Short Checklist

- [ ] Do we have 3–5 reusable prompt components?
- [ ] Do we have one golden example for our most common task?
- [ ] Are outputs structured so they can be reviewed quickly?
- [ ] Do prompts include a verification hook?
- [ ] Do prompts avoid lazy contrast and template voice?

If you want team-level leverage, stop treating prompts like personal hacks. Treat them like interfaces.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
