# Unified Article Spec — Developer-Grade, Workflow-First

Purpose: Provide a single, authoritative specification that consistently produces practical, developer-facing articles matching the reference style: direct, anti-hype, mental-models → workflows → caution → checklist, with concrete prompt patterns and minimal scaffolding.

This spec replaces scattered instructions and removes any tendency to leak internal mechanics (devices, gates, shapes) into public text.

---

## Purpose & Audience

- Audience: Professional developers and technically fluent AI users.
- Goal: Deliver articles that change behavior this week via clear mental models, reusable workflows, and guardrails.
- Outcome: Readers can apply at least one workflow immediately and understand limits and risks.

## Target Tone & Voice

- Voice: Direct, peer-to-peer, confident, pragmatic. Default to second person (“you”).
- Diction: Specific, concrete, anti-hype. No marketing speak; no academic stiffness.
- Anthropomorphism: Avoid it. Refer to models as predictive systems.
- Rhythm: Short to medium sentences; natural cadence; vary openings.

## Structural Expectations

Write a natural article (do not expose labels) that implicitly follows:
1) Opening Reality Check (scene/tension grounded in real work)
2) Definition and/or 2–3 Mental Models (brief, utility-first)
3) 3–5 Workflow Blocks (each uses the template below)
4) Caution: What Not to Outsource to AI (security, architecture, compliance, unreviewed code)
5) Before/During/After Checklist (tri-stage, practical)
6) Closing Activation (one concrete next step)
7) Further Reading (3–6 credible links; optional)

Length guidance: 1,500–2,500 words; expand only when adding concrete utility.

## Rhetorical Patterns & Devices

- Contrast: Bad vs. good prompting or old vs. new workflow.
- Pattern Blocks: Use “When / Why / Pattern / Steps” for each workflow.
- Prompt Snippets: Include narrowly scoped prompt patterns (role, objective, constraints, success criteria).
- Minimal Anecdotes: Use sparingly to set stakes, not to pad.
- Tables: Markdown, reflowable; use only when they improve scannability.

## Depth & Density Guidelines

- Paragraphs: 2–5 sentences; each carries a single idea forward.
- Lists: Prefer bullets for steps, checks, and pitfalls.
- Examples: Realistic, self-contained; name tools/frameworks when helpful.
- Evidence: Link to reputable sources; APA only if the brief requires it.

## Content Construction Instructions

### Workflow Block (repeat 3–5 times)
- When: Situations where this applies.
- Why: Tie to a mental model; explain leverage and limits.
- Pattern: A short, copyable prompt structure (role, objective, constraints, success criteria).
- Steps: Concrete, verifiable steps the reader can follow.

Required internal fields (silent; render naturally in prose):
- PromptSpec: role, objective, constraints[], successCriteria[]
- OutputMode: diff | plan | snippet | checklist (pick one; render as clear instructions, not a label)
- Artifacts: expected artifacts like unifiedDiff, reviewChecklist, codemodPrototype, grepPattern (expressed in plain language)
- ValidationPlan: tests to add/adjust; logs/metrics to compare; a one-line compare script (render as guidance under Steps or Pattern)
- ChangeIsolation: scope of change (files/folders/globs) and exclusions
- RollbackNotes: how to revert per step or PR
- Risk & Guardrails: vendor-neutrality; no new deps unless brief allows; no authZ/authN or compliance logic

Notes:
- These fields guide drafting and QA. Public text should express them naturally (e.g., “Return a unified diff for X and a 7–10 item review checklist”) rather than exposing internal labels.

### Mental Model Block (2–3 total)
- Name: Short, memorable label.
- Utility: How it shapes better usage and guardrails.
- Boundaries: Where it fails; how to avoid misuse.

### Caution Section
- Enumerate tasks to keep human-owned (security, architecture, compliance, high-risk code, anything you won’t review line-by-line).
- Provide quick tests for safe usage.

### Tri-Stage Checklist
- Before: Task clarity, constraints, success criteria.
- During: Ask for designs/hypotheses/transformations; ensure adequate context; iterate.
- After: Review as you would a junior’s output; test/run/verify; correct invented claims.

## Things That Must Never Appear in Public Articles

- Internal terms: Device, Gate, Shape, Style Anchor, Critic Loop, Research Pass, Activation Header, Gate Validation, Article Metrics, Archival Information.
- File paths from this workspace.
- Bracketed placeholders like [Writer to research…], [RESEARCH GAP…], or execution logs.

Also avoid exposing schema labels like PromptSpec, OutputMode, Artifacts, ValidationPlan, ChangeIsolation, RollbackNotes.

## Quality & Self-Review Checklist (Silent)

- Voice: Second-person developer voice; direct, anti-hype; no anthropomorphism.
- Structure: Opening reality check → mental models → 3–5 workflows → caution → tri-stage checklist → closing activation → optional further reading.
- Utility: Each workflow has When/Why/Pattern/Steps and a tight prompt snippet.
- Workflow Schema: For any detected workflow, confirm PromptSpec present (role/objective/constraints/success criteria), OutputMode stated in natural language, ValidationPlan present (tests/logs/metrics/script), ChangeIsolation and RollbackNotes present in plain prose, and Guardrails stated.
- Evidence: Link credible sources; APA only if brief requests; keep stats minimal (≤2) and current.
- Anti-leak: No internal scaffolding terms or placeholders in public text.
- Readability: Short paragraphs; scannable lists; reflowable tables only when they add value.

---

Version: 1.1
Date: 2025-11-13
Precedence: Use alongside Style Baseline; overrides prior device/gate-heavy directives for public articles.
