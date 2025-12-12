# Day 18: The Restraint Playbook: When AI Becomes the Wrong Fit

One of the fastest ways to get value from AI is to avoid using it where it creates hidden risk.

Most teams don’t do this because the failure mode looks like success.

The model gives you an answer, the work moves forward, and the debt accumulates quietly.

Restraint is professional judgment.

---

## A Simple Frame: Authority, Not Capability

The model can generate a lot of useful drafts.

The question is what authority you assign to the output.

| If the output influences… | Treat AI as… | Because… |
|---------------------------|--------------|----------|
| low-stakes drafts | a drafting tool | you can revise quickly |
| internal decisions | a thought partner | you can interrogate assumptions |
| external commitments | a risky assistant | mistakes become promises |
| safety/compliance | a support tool at most | accountability cannot be outsourced |

Your goal is to use AI where revisions are cheap, and avoid it where mistakes are expensive.

---

## The “Should We Use AI?” Gate

Use this before you bring AI into a workflow.

```text
Task: Decide whether AI should be used for this work.

Inputs:
- Work type: [drafting | analysis | decision | execution]
- Stakes: [low | medium | high]
- Reversibility: [easy | hard]
- Verification: [easy | hard]
- Data sensitivity: [low | high]

Output:
1) Recommendation: Use AI / Use AI with constraints / Do not use AI
2) Rationale (5 bullets)
3) Required guardrails if AI is allowed
```

Verification step:

- If the recommendation is “use AI” for high stakes and hard-to-verify work, the gate is broken. Tighten it.

---

## Shadow Mode (AI as a Second Opinion)

Use this when you want the upside without letting the output drive the decision.

```text
Role: You are a second-opinion reviewer.
Input: Here is the decision brief / plan / draft.

Task:
- Identify weak assumptions.
- List edge cases.
- Suggest questions to ask in review.

Rules:
- Do not propose a final decision.
- Keep feedback concrete and testable.
```

Shadow mode is the best default for complex work: AI supports your thinking without owning outcomes.

---

## Human-First, AI-Assist (The Safe Split)

Use this when the team needs speed but the work has real stakes.

Split the work by ownership:

- Humans own the decision, constraints, and acceptance criteria.
- AI helps with drafts, options, and checklists.

```text
Role: You are a drafting assistant.
Input:
- Decision: [one sentence]
- Constraints: [list]
- Acceptance criteria: [list]

Task:
- Draft options and a review checklist.

Rules:
- Do not invent facts.
- If a claim needs evidence, ask for sources.

Output:
1) Options (3 max)
2) Checklist (10 items)
3) Open questions
```

---

## Where Restraint Pays Off

Avoid using AI as the primary driver for:

- security architecture
- compliance interpretations
- irreversible migrations
- anything you cannot verify quickly

Use AI aggressively for:

- summarizing and structuring messy input
- generating alternative drafts
- creating checklists and test plans

---

## What You Still Own

- you own what ships
- you own what you promise
- you own the review

That doesn’t change because a model wrote the words.

---

## A Short Checklist

- [ ] Are the stakes high?
- [ ] Is verification hard?
- [ ] Is the work irreversible?
- [ ] Is the data sensitive?
- [ ] If yes to any of the above, am I using shadow mode or human-first split?

Restraint is what keeps AI useful over time.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
