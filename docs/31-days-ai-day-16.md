# Day 16: Decision Briefs: Using AI for Strategy Without Handing It the Wheel

A model can produce a strategy memo in seconds.

The dangerous part is that it can sound like a strategy memo even when it is guessing.

If you use AI for planning work, the goal is to get a structured draft you can interrogate.

---

## The Artifact That Scales: A Decision Brief

A decision brief is a small document that makes tradeoffs visible.

It forces clarity on:

- what decision is being made
- what constraints exist
- what options are on the table
- what evidence matters
- what could go wrong

When you ask a model for a “plan,” you often get confident prose.

When you ask it for a brief, you get an artifact you can review.

---

## Proof Artifact: A Brief Skeleton You Can Reuse

```text
Decision: [one sentence]
Owner: [role/team]
Date: [optional]

Context:
- Why now:
- Constraints:
- Non-goals:

Options (3 max):
1)
2)
3)

Risks:
- Technical:
- Operational:
- Security/compliance:

Open questions:
- 

Recommendation:
- 

Verification:
- What evidence would change the recommendation?
- What would you need to measure in production to know you were wrong?
```

This is deliberately boring. Boring scales.

---

## Convert a Messy Thread Into a Brief

Use this when you have a Slack thread, meeting notes, or a doc full of opinions.

```text
Role: You are a staff engineer.
Input: I will paste a thread.
Task: Convert it into a decision brief using the skeleton below.
Rules:
- Separate facts from interpretations.
- List assumptions explicitly.
- If the input is missing key context, ask 3 targeted questions.
Output:
- Return the brief.
```

Verification step:

- Read only the “Open questions” section. If it does not surface real uncertainties, the model smoothed over complexity.
- Then read only “Assumptions.” If it is empty, ask for a second pass that is harsher and more explicit.

---

## Option Comparison With Real Constraints

Use this when you already have 2–3 plausible approaches.

```text
Here are the options and constraints.

Options:
1) [A]
2) [B]
3) [C]

Constraints:
- [latency]
- [cost]
- [team skill]
- [compliance]

Task:
- Produce a comparison table.
- For each option, list: upside, downside, failure modes, operational burden.
- End with 5 questions I should ask in a review.
Rules:
- Do not invent metrics.
- If you need data, say what data.
```

This works because it keeps the model inside the box: structure, tradeoffs, and questions.

If you want a stronger output, require a comparison table format explicitly:

```text
Format: Markdown table with columns: Option, Upside, Downside, Failure Modes, Operational Burden, Unknowns.
Rules:
- Do not invent metrics.
- Put unknowns in the Unknowns column.
```

---

## Pre-mortem (How This Fails)

Use this when a plan looks too clean.

```text
Role: You are a skeptical reviewer.
Task: Run a pre-mortem on this decision brief.
- Assume the decision failed in 6 months.
- List 10 reasons it failed.
- For each reason, propose one mitigation.
Rules:
- Keep reasons concrete (systems, people, process).
- Flag anything that needs a human decision.
```

---

## What You Still Own

A model can help you organize thinking.

You still own:

- picking the option
- validating the evidence
- the accountability when it ships

---

## A Short Checklist

- [ ] Did we define the decision in one sentence?
- [ ] Did we list constraints and non-goals?
- [ ] Did we limit options to three?
- [ ] Did we run a pre-mortem?
- [ ] Did we identify what evidence would change our minds?

If you use AI for strategy, use it to draft briefs you can argue with, then do the arguing yourself.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
