# Reusable Blocks — Workflow and Mental Model

Purpose: Provide slot-based templates for the two core block types used in developer-grade articles. Treat these as internal scaffolding only. Do not print the labels “Workflow Block” or “Mental Model Block” in public text.

---

## Mental Model Block (Internal Template)

- Name: [short, memorable label]
- Utility: [how it improves usage and clarifies guardrails]
- Boundaries: [where it fails; common misuses to avoid]

Public rendering guidance:
- 2–4 sentences or 2–3 bullets
- Focus on how the model changes behavior; avoid lengthy metaphor

---

## Workflow Block (Internal Template)

- When: [situations where this applies]
- Why: [tie to a mental model; leverage and limits]
- Pattern (Prompt):
  - Role: [the system is reviewing/building X in Y context]
  - Objective: [what outcome is sought]
  - Constraints: [rules, dependencies, boundaries]
  - Success criteria: [what the answer must include/avoid]
- Steps: [3–6 concrete, verifiable steps for the reader]

Schema fields (internal; render naturally in prose, not as labels):
- OutputMode: diff | plan | snippet | checklist (select one)
- Artifacts: [unifiedDiff | reviewChecklist | codemodPrototype | grepPattern]
- ValidationPlan:
  - tests: [cases to add/adjust]
  - logs: [structured fields to compare]
  - metrics: [key rates/counters]
  - compareScript: [one-liner]
- ChangeIsolation: { includeGlobs: [...], excludeGlobs: [...] }
- RollbackNotes: [how to revert per step/PR]
- Risk & Guardrails: [vendor-neutral; no new deps; avoid authN/authZ/compliance]

Public rendering guidance:
- Use the headings or bold keywords “When”, “Why”, “Pattern”, and “Steps” naturally in the section
- Keep the prompt tight and copyable; avoid long code blocks unless essential

---

## Canonical Examples (Internal)

Use these to seed new workflows; adapt names and stack.

1) Refactor — Localized Diff Extraction
- OutputMode: diff
- Artifacts: unifiedDiff, reviewChecklist
- ValidationPlan: tests (happy/edge/invalid), logs (validation outcomes), compareScript
- ChangeIsolation: include controllers/, exclude migrations/
- RollbackNotes: revert single commit/PR

2) Debugging — Hypothesis Generation
- OutputMode: plan → snippet (minimal patch)
- Artifacts: rankedHypotheses, microExperiments, minimalPatch
- ValidationPlan: targeted logs; failing test first
- Guardrails: no global edits; no new deps

3) Feature Design — Spec-First
- OutputMode: plan
- Artifacts: alternativesMatrix, decisionRationale, scaffoldSkeleton
- ValidationPlan: unit test outline
- Guardrails: team conventions; performance constraints

4) Docs — Design Doc Section
- OutputMode: snippet
- Artifacts: context/problem/decision/tradeoffs block
- ValidationPlan: links to PRs/issues; terminology preservation

---

Version: 1.1
Date: 2025-11-13
