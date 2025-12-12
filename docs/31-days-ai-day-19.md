# Day 19: Agentic AI: When the Model Stops Answering and Starts Doing

You ask for a plan.

You get a plan, plus a set of shell commands, a suggested folder structure, and a confident claim that it all “just works.”

Then you run it and it breaks in three different ways.

That is the difference between an assistant and an agent.

An assistant returns text.

An agent takes actions, or at least proposes actions in a way that looks actionable.

If you treat agents as smarter chatbots, you will hand them authority they haven’t earned.

---

## The Core Idea: Loops, Tools, and Memory

A useful mental model for an agent is a loop that repeats:

1. Observe (read context)
2. Decide (pick a next action)
3. Act (call a tool, write a file, run a query)
4. Verify (check results)

Three ingredients determine whether that loop is safe and useful:

- **Tools:** what it can touch (filesystem, browser, database, deploy pipeline)
- **Memory:** what it can remember (short context vs stored state)
- **Guardrails:** what it is not allowed to do (scope, permissions, approvals)

When an agent fails, it usually fails by taking the wrong action with too much confidence.

---

## Where Agentic Work Breaks Down

Agents are good at stitching steps together.

They are weak at knowing when to stop, what they do not know, and what requires human accountability.

Common failure modes:

- **Scope creep:** it “helpfully” edits adjacent files you didn’t ask to change.
- **Phantom verification:** it claims tests passed without actually running them.
- **Tool misuse:** it uses a command that looks right but is wrong for your environment.
- **Silent assumptions:** it assumes paths, versions, permissions, or policies.

The fix is to make the loop observable and bounded.

---

## The Safe Agent Contract (Scope + Outputs)

Use this when you want agent-like behavior, but you need strict boundaries.

```text
Role: You are a careful engineering agent.
Goal: Complete the task below with minimal changes.
Task: [describe]

Scope:
- Allowed paths: [list folders]
- Forbidden paths: [list folders]
- Allowed operations: [read-only | edits | create files]
- Forbidden operations: [deps, migrations, auth changes, infra]

Outputs required:
1) A short plan (3–7 steps).
2) A list of files it will touch.
3) A patch/diff only.
4) A verification plan (commands to run).

Rules:
- If a requirement is ambiguous, ask 2–3 questions.
- Do not claim something was tested unless you show the exact command.
- If you cannot verify, say so.
```

This works because it turns agent behavior into a contract you can enforce.

---

## Tool Calls With Receipts (No Phantom Success)

Use this when the agent can run commands or call tools.

Require a receipt for every claim.

```text
Task: Perform the change.

Verification rules:
- For every tool call, output:
  - The exact command
  - The exit status
  - A short excerpt of the output that proves success

If any step fails:
- Stop
- Explain what failed
- Propose 2 options
```

The point is not bureaucracy. The point is making the loop inspectable.

---

## “Plan, Patch, Prove” (The Default Agent Pattern)

Use this for codebase work where the agent is writing changes.

```text
You will operate in three phases:

1) Plan:
- Identify the target files and risks.
- State assumptions.

2) Patch:
- Produce a minimal diff.

3) Prove:
- List the exact commands I should run to verify.
- Explain what success looks like.

Constraints:
- Keep the change isolated.
- Avoid refactors unless required.
- Do not introduce new dependencies.
```

If you only adopt one agent pattern, adopt this one.

---

## Guardrails That Matter More Than Cleverness

Agentic systems feel powerful because they chain steps.

In practice, safety comes from boring controls:

- **Least privilege:** the agent should not have access to production secrets.
- **Path scoping:** constrain where it can write.
- **Human approvals:** require sign-off before merges, deploys, or migrations.
- **Rollback:** every step should be reversible.

If you cannot describe how to undo the agent’s work, it is not safe to run unattended.

---

## Before You Let an Agent Touch Your Repo

- [ ] Did I define allowed paths and forbidden paths?
- [ ] Did I require a diff-only output?
- [ ] Did I require receipts for tool calls and tests?
- [ ] Did I block high-risk areas (auth, payments, infra, compliance logic)?
- [ ] Did I keep a rollback path?

Agents are valuable when you treat them like a junior engineer with fast hands, limited context, and a tendency to sound confident.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
