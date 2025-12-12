# Day 30: Documentation That Stays True: Using AI Without Shipping Lies

Your docs are correct.

For about a week.

Then a flag changes, an endpoint gets renamed, a default flips, and the docs become a confident artifact that points people at the wrong thing.

AI can help you write docs.

It can also help you scale the most expensive kind of bug: **misleading documentation**.

The goal is not prettier docs.

The goal is docs that behave like a product: versioned, reviewable, and tested against reality.

---

## The Real Problem: Drift, Not Writing

Most teams do not fail at documentation because they cannot write.

They fail because documentation drifts away from the system.

Drift happens when:

- docs are written once and never revisited
- the person who made the change does not own the docs
- reviews focus on code and skip the user-facing story
- examples are not executable, so nobody notices when they rot

AI can reduce writing friction.

It cannot detect drift unless you design for it.

---

## Proof Artifact: “Docs as a Patch,” Not “Docs as a Blog Post”

If you want docs to stay correct, treat them like code changes.

A useful doc update looks like a patch:

- what changed
- what users should do differently
- what examples must be updated
- what is still unknown

Here is the simplest pattern that scales:

```text
Change summary:
- What changed:
- Who it affects:
- What to do now:

Docs affected:
- Pages to update:
- Examples to update:
- Screenshots to update (if any):

Verification:
- How we verified the docs match reality:
```

AI is excellent at drafting this structure.

Your team must own the verification.

---

## The Doc Diff Review (Use AI Like a Reviewer, Not an Author)

Use this when a PR changes behavior.

```text
Role: You are a careful doc reviewer.

Inputs:
- Here is a code diff.
- Here is the current documentation (relevant section only).

Task:
1) Explain what behavior changed in user terms.
2) Identify what parts of the docs are now wrong or ambiguous.
3) Propose a documentation patch (Markdown diff) that fixes it.
4) List what you could not verify from the diff and what you would ask the author.

Rules:
- Do not invent behavior not shown in the diff.
- If the change implies new edge cases, list them as questions.

Output:
- A Markdown patch + questions
```

Verification step:

- If the patch adds claims that are not visible in the diff, delete them and ask for evidence.

---

## Example-First Docs (Turn Examples Into Tests)

Use this when your docs include commands, config, or code snippets.

The fastest way to prevent doc drift is to make examples executable.

AI can help you rewrite examples into a consistent, testable shape.

```text
Task: Turn these documentation examples into executable checks.

Inputs:
- Here are code snippets / commands from docs.
- Here is the environment context (language, toolchain).

Requirements:
- Produce a minimal test plan that validates the examples.
- For each example, define what success looks like.
- If a snippet cannot be tested, explain why and propose a safer alternative.

Rules:
- Do not guess versions.
- Do not invent outputs.

Output:
- Test plan + per-example checks
```

Verification step:

- Run the checks in CI (or a nightly job) so broken docs show up as failures, not customer tickets.

---

## Make “Unknown” a First-Class Doc State

A lot of doc harm comes from pretending we know.

If a behavior is unclear, unstable, or vendor-dependent, write that.

AI is helpful here as a consistency enforcer:

- spot definitive language (“always,” “guaranteed,” “never”) and soften it
- label assumptions
- add “how to verify in your environment” steps

```text
Task: Make this documentation section safer.

Input:
[PASTE]

Rules:
- Flag any definitive claims that should be bounded.
- Add an "Assumptions" section if needed.
- Add a "How to verify" section with simple steps.

Output:
- Revised doc section
```

Verification step:

- If the “how to verify” steps require access users do not have, rewrite them to something they can actually do.

---

## The Small Process Change That Works: Docs Ownership at Review Time

If you only do one thing, do this:

- When a change affects users, require a doc update in the same PR.
- If docs are not updated, require an explicit reason.

AI can draft the patch.

The engineer still owns the truth.

---

## A Short Checklist

- [ ] Does every user-visible change include a doc patch?
- [ ] Are examples executable or at least verifiable?
- [ ] Do docs distinguish facts from assumptions?
- [ ] Do docs include “how to verify” steps?
- [ ] Do we have a way to detect doc drift (CI checks, reviews, scheduled audits)?

Docs stay correct when they are treated as part of the system, not as a side project.

---

## Further Reading (Optional)

- Writing and formatting Markdown in GitHub: https://docs.github.com/en/get-started/writing-on-github
- Docs-as-code (treat docs like product changes): https://www.writethedocs.org/guide/docs-as-code/
- RAG survey (how retrieval is often used for “docs answers”): https://arxiv.org/abs/2312.10997

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
