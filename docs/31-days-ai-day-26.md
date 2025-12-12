# Day 26: Evals That Prevent Embarrassing Launches (Not “Benchmarks”)

You test your AI feature with three prompts.

It looks great.

Then a customer asks a slightly different question, and the model:

- answers confidently with the wrong policy
- misreads a number in a pasted table
- refuses a harmless request because it “sounds risky”

That should not surprise you.

You shipped without evals.

Evals are not a research thing. They are the cheapest form of engineering insurance you can buy.

---

## The Artifact That Matters: A Small, Fixed Test Set

Most teams don’t need a massive benchmark.

They need a **small set of real inputs** that represent:

- your highest-value workflows
- your highest-risk failures
- your weird edge cases

The goal is simple:

> When you change anything (prompt, retrieval, model, tool wiring), you can detect regressions before users do.

---

## Proof Artifact: A One-Page Eval Card

This is the minimum you need to stop shipping vibes.

```text
Feature: [name]
Purpose: [what it does]

Golden tasks (5–20):
- [task name] — [why it matters]

Red flag tasks (5–20):
- [task name] — [how it fails]

Rubric (per task):
- Correctness: [pass/fail criteria]
- Safety: [pass/fail criteria]
- Helpfulness: [pass/fail criteria]
- Evidence: [must cite sources? must quote input?]

What counts as a regression:
- [one sentence]

Release gates:
- What must pass to ship?
- What can degrade if we accept the risk?
```

Once you have this card, you can turn “it feels worse” into “these three tasks regressed.”

---

## Build Your First Eval Set From What You Already Have

Use this when you want an eval set that reflects reality.

Start with artifacts your team already produces:

- support tickets
- incident writeups
- docs people misinterpret
- common user questions
- the top queries in your search logs

Then choose tasks that represent **decisions** users actually make.

---

## Turn Messy Reality Into Test Cases (Without Leaking Secrets)

Use this when your source material is sensitive.

```text
Role: You are a careful QA engineer.

Task: Convert the examples below into eval test cases.

Rules:
- Remove or anonymize sensitive details (names, IDs, customer info).
- Preserve the structure of the problem (what makes it hard).
- Each test case must include:
  - Input
  - Expected properties (not a single “correct answer” unless it’s objective)
  - Failure modes to watch for

Output:
- A list of test cases in a consistent format.

Examples:
[PASTE]
```

Verification step:

- If any anonymized case no longer has a clear failure mode, replace it with a different example.

---

## Make the Rubric Specific Enough to Disagree Less

A rubric that says “be accurate” is not a rubric.

A usable rubric describes what “pass” looks like in observable terms.

Here’s a pattern that works in most product evals:

- **Must include:** required fields, required citations, required steps.
- **Must avoid:** forbidden claims, forbidden actions, forbidden leakage.
- **Must be consistent:** output shape stays stable across runs.

```text
Task: Tighten this rubric.

Context:
- Here are 5 sample outputs for the same task.

Goal:
- Rewrite the rubric so two humans can score outputs similarly.

Rules:
- Use pass/fail checks when possible.
- If a check is subjective, define examples of pass vs fail.

Rubric:
[PASTE]

Samples:
[PASTE]

Output:
- Revised rubric + 5 concrete scoring rules.
```

---

## “LLM as Judge” Is Useful, If You Treat It Like a Biased Rater

Using a model to score outputs can scale your evals.

It also introduces new failure modes: inconsistent scoring, preference bias, and sensitivity to phrasing.

If you do this, make the judge follow the same rules you want from humans:

```text
Role: You are a strict evaluator.

Task: Score the candidate output.

Rubric:
[PASTE]

Input:
[PASTE]

Candidate output:
[PASTE]

Rules:
1) Quote the exact text that triggered each score.
2) If you cannot find evidence for a criterion, score it as fail.
3) Return a short rationale per criterion.

Output:
- A table with: Criterion, Pass/Fail, Evidence Quote, Rationale
```

Verification step:

- Run the judge twice on the same example. If it changes its mind, your rubric is still too soft.

---

## What to Measure Beyond “Quality”

If your evals only score “the answer,” you’ll miss why users complain.

Track at least these dimensions:

- **Latency:** does the output arrive in time to be useful?
- **Variance:** do repeated runs produce stable decisions?
- **Refusal behavior:** does it refuse the right things, for the right reasons?
- **Evidence behavior:** does it quote sources or hallucinate them?

These are product behaviors, not model trivia.

---

## A Short Checklist

- [ ] Do we have a small fixed test set based on real work?
- [ ] Does each test have a clear failure mode?
- [ ] Is the rubric specific enough to score consistently?
- [ ] Do we measure variance, latency, and refusal behavior?
- [ ] Do we treat any scoring model like a biased rater and require evidence quotes?

Evals are how you keep your AI feature boring in production.

---

## Further Reading (Optional)

- HELM (multi-metric evaluation for language models): https://arxiv.org/abs/2211.09110
- LLM-as-a-judge (MT-Bench / Chatbot Arena): https://arxiv.org/abs/2306.05685

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
