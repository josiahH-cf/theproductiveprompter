# Day 29: AI for Incident Response: Make It a Calm Copilot, Not a Chaos Multiplier

Your service is paging.

You open the dashboard, skim the logs, and your brain starts doing the thing it always does under stress: pattern-matching.

AI can help here.

AI can also make it worse by producing a clean story too early.

In incident response, the goal is not a clever answer.

The goal is **a sequence of safe, reversible steps that reduce uncertainty**.

---

## The Constraint That Changes Everything: You Are Operating a Live System

During an incident, “helpful” suggestions have a cost.

- a wrong command can widen the blast radius
- a premature root-cause story can send the team down the wrong path
- a confident summary can create a false sense of control

So treat AI like a calm copilot.

It can:

- turn messy evidence into an inspectable timeline
- propose hypotheses and list what would confirm or refute them
- draft comms that you can quickly edit

It must not:

- run commands
- invent facts
- decide the mitigation

---

## Proof Artifact: A Good Incident Output Has Receipts

Two outputs can sound equally confident.

Only one is useful.

| Output type | Looks good | Actually helps |
|---|---|---|
| “Probable root cause” paragraph | yes | only if it cites evidence and uncertainty |
| Timeline table | boring | yes, because it is reviewable |
| Hypothesis list + tests | less fluent | yes, because it creates next steps |
| Comms draft with unknowns | safe | yes, because it avoids promises |

If the output is not inspectable, it is noise.

---

## The Evidence Pack (What You Paste, What You Do Not)

Use this when you are about to paste everything into a model.

Your goal is to share enough to reason, without leaking secrets or drowning the model.

```text
Task: Help me build an incident evidence pack.

Context:
- System: [name]
- Current impact: [who/what is affected]
- What changed recently: [deploy/config/traffic]

Evidence (paste only what you can safely share):
- Alerts: [top signals]
- Logs: [short excerpt]
- Metrics: [key graphs described in text]
- Recent deploys: [titles/IDs]

Rules:
- If any evidence contains secrets or customer data, tell me what to redact.
- Ask for the 5 missing pieces that would change the diagnosis.

Output:
- A cleaned evidence pack
- A list of missing info
```

Verification step:

- If the evidence pack contains credentials, tokens, or customer identifiers, stop and redact.

---

## Triage as a Table (Turn Stress Into Structure)

Use this when you need the fastest path to “what do we do next?”

```text
Role: You are an incident commander assistant.

Task:
1) Build a timeline table from the evidence.
2) Generate 3–5 hypotheses.
3) For each hypothesis, propose a fast test or check.
4) Recommend a safe next action sequence (reversible first).

Rules:
- Quote the exact evidence lines you used.
- If evidence conflicts, say so.
- Do not propose irreversible actions.

Output:
1) Timeline table: Time, Signal, Observation, Evidence quote
2) Hypotheses: Hypothesis, Evidence for, Evidence against, Fast test
3) Next actions: ordered list with rollback notes

Evidence:
[PASTE]
```

Verification step:

- If the next actions include “delete,” “drop,” “rotate,” “disable,” or “migrate” without an explicit rollback, treat it as unsafe.

---

## Runbook Translator (Turn a Wall of Docs Into Steps You Can Execute)

Use this when your runbook exists, but nobody can parse it under pressure.

```text
Role: You are an on-call engineer.

Task: Convert this runbook into a step-by-step procedure.

Rules:
- Each step must include: intent, exact command (if present), expected output, and what to do if it fails.
- If the runbook does not provide a command, ask for the missing details.
- Do not invent commands.

Output:
- A numbered procedure
- A "stop conditions" section (when to escalate)

Runbook:
[PASTE]
```

Verification step:

- If any step lacks an expected outcome, add it. “Run X” without “what success looks like” is not a runbook.

---

## Safer Incident Comms (Draft Fast Without Promising Things)

Use this when you need a status update that is accurate and defensible.

```text
Role: You are drafting incident communications.

Inputs:
- Impact: [what users see]
- Known facts: [bullets]
- Unknowns: [bullets]
- Next update time: [time window]

Task:
- Write a short update for internal stakeholders.

Rules:
- Separate facts from hypotheses.
- Do not claim a root cause unless it is confirmed.
- Avoid exact ETAs unless the team has high confidence.

Output:
- Status
- Impact
- What we know
- What we do not know
- What we are doing next
```

Verification step:

- If the draft contains causal language (“caused by”) without evidence, rewrite it to reflect uncertainty.

---

## What You Still Own

AI can help you move faster in an incident.

It cannot own:

- the decision to mitigate
- the blast-radius tradeoff
- the call to roll back or roll forward
- the responsibility for customer impact

Use it to make evidence and options clearer, then make the calls like an adult.

---

## A Short Checklist

- [ ] Did we build an evidence pack with redactions?
- [ ] Did we produce a timeline table with evidence quotes?
- [ ] Are hypotheses tied to fast tests?
- [ ] Are next actions reversible first, with rollback notes?
- [ ] Does comms separate facts, unknowns, and hypotheses?

The best incident response tool is the one that keeps you calm and honest.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
