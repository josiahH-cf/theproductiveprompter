# Day 28: When AI Can Call Tools: How to Keep “Helpful” From Becoming Dangerous

You give a model a tool.

At first it’s great:

- it can open a ticket
- it can query a database
- it can edit a file

Then one day it does the thing you did not mean.

It updates the wrong record.

It edits the wrong file.

It posts the wrong message.

Tool-using AI fails the same way junior engineers fail: fast hands, partial context, and a tendency to sound confident.

The fix is not better prompts.

The fix is designing the tool interface like an engineering system: scopes, receipts, idempotency, and human approvals.

---

## The Mental Model: Tools Turn Text Errors Into Real-World Changes

When a model is chat-only, its mistakes are mostly words.

When a model can call tools, its mistakes become:

- state changes
- external side effects
- security incidents
- irreversible actions

So you need a different bar for “works.”

The goal is not to make the model smarter.

The goal is to make the system safer when the model is wrong.

---

## Proof Artifact: The Same Intent, Two Different Tool Interfaces

The tool interface you design determines how the model behaves.

**Loose interface**

```text
Tool: create_ticket(title, description)
```

**Constrained interface**

```text
Tool: create_ticket(
  project: "support" | "infra" | "security",
  severity: "low" | "med" | "high",
  title: string,
  description: string,
  customer_id: string | null,
  requires_human_review: true
)
```

The constrained version reduces ambiguity and forces a review step.

That is what you want.

---

## The Safe Tool Contract (Scope + Output Receipts)

Use this when you are wiring tools into an agent.

```text
Role: You are a careful engineering agent.

Goal:
- Propose tool calls that achieve the task.

Scope:
- Allowed tools: [list]
- Forbidden tools: [list]
- Allowed resources: [paths, projects, tenants]
- Forbidden resources: [paths, projects, tenants]

Rules:
1) Produce a plan first.
2) For each tool call, output a JSON object with only the allowed fields.
3) Never guess identifiers (IDs, URLs, account numbers). Ask.
4) For any write operation, include a rollback plan.
5) Always return receipts: tool name, arguments, and why.

Output:
- Plan
- Proposed tool calls (JSON)
- Verification steps
- Rollback plan
```

Verification step:

- If the agent proposes a write operation without a rollback, block it.

---

## Make Writes Harder Than Reads

Most safe systems share one boring principle:

> Read is cheap. Write is gated.

Design your tool set that way:

- read-only tools (search, fetch, list) can run freely
- write tools (update, delete, deploy) require extra friction

Two practical patterns:

1) **Two-step commit**

- Step 1: propose a diff / patch / plan
- Step 2: a human approves
- Step 3: apply the change

2) **Scoped capability tokens**

- tool calls include a short-lived capability (scope + expiration)
- the model cannot mint its own capability

You do not need to call this “security.”

You just need to make it hard to do the wrong thing quickly.

---

## Idempotency and “Undo” Are Not Optional

If the model retries, you do not want duplicate side effects.

If the model is wrong, you want a reversible action.

Make these design choices explicit:

- tool calls accept a request id (idempotency key)
- writes return a change id you can revert
- destructive operations are disabled or require explicit human confirmation

This is systems engineering, not prompt engineering.

---

## A Practical Prompt Pattern: Plan, Then Call Tools

Use this when you see the model jumping straight into actions.

```text
Role: You are a careful operator.

Task:
- Complete the request using tools.

Rules:
1) First output a short plan.
2) Then propose tool calls (do not execute).
3) Wait for approval.
4) After approval, execute tool calls.
5) After execution, summarize what changed and how to verify.

Safety:
- If any required info is missing, ask targeted questions.
- If the action is irreversible, stop and request explicit confirmation.

Output:
- Plan
- Proposed calls
- Questions (if any)
```

Verification step:

- If the plan and tool calls do not match, reject and ask for a second pass.

---

## What You Still Own

Even with perfect tool wiring, the human responsibility does not go away.

You still own:

- what resources the model can touch
- what counts as approval
- what logging is required
- what happens when something goes wrong

Agents do not remove accountability. They move it into your system design.

---

## A Short Checklist

- [ ] Are write tools gated behind approval?
- [ ] Do tool calls have scope and least privilege?
- [ ] Do writes have idempotency keys and rollback paths?
- [ ] Do we require receipts for every action?
- [ ] Can the system say “missing info” instead of guessing?

Tool-using AI is safe when the interface makes dangerous behavior difficult.

---

## Further Reading (Optional)

- ReAct (reasoning + acting): https://arxiv.org/abs/2210.03629
- Toolformer (models learning to call tools): https://arxiv.org/abs/2302.04761
- Gorilla (LLMs + large API surfaces): https://arxiv.org/abs/2305.15334

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
