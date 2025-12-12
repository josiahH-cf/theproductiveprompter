# Article Brief — Pilot Validation (Workflow-First Spec)

## 1. Article Metadata
**Title:** Small-Step Refactors with AI: When, Why, and How
**Intended Audience:** Backend developers using TypeScript/Node.js with PostgreSQL; intermediate+ experience
**Publication Context:** Companion site pilot to validate unified spec
**Estimated Scope:** 1,700–2,200 words; focused on refactoring/migrations with AI assistance

## 2. Objective & Scope
**Objective:** Enable readers to plan and execute refactors as a series of safe, reviewable steps using AI, without global rewrites.
**Scope:**
- Includes: mental models; 3–4 workflows (plan steps, codemod sketch, search/replace patterns, validation); caution; tri-stage checklist.
- Excludes: front-end frameworks; vendor-specific features; deep ORM migrations.
**Constraints:** Length 1.7–2.2k; second-person dev voice; linkable citations by default; no internal scaffolding terms in public text.
**Required Blocks:**
- 2–3 mental models
- 3–5 workflow blocks (When/Why/Pattern/Steps + prompt snippet)
- Caution section (what not to outsource)
- Tri-stage checklist (Before/During/After)

## 3. Core Argument
**Central Thesis:** Refactors succeed when decomposed into small, verifiable steps; AI accelerates planning and mechanics but must not own architecture or correctness.
**Supporting Claims:**
- Small steps reduce review risk and enable rollback.
- Prompted plans are faster than ad hoc edits when grounded in constraints.
- Local diffs and codemods beat global rewrites for reliability.

## 4. Planning Aids (Internal Behaviors)
- Scenario/vignette: Legacy validation spread across controllers; move to centralized schema module.
- Comparison table: Small-step vs. global rewrite (risk, review effort, rollback).
- Workflow blocks: plan sequence; generate codemod; search/replace; validate with tests.

## 5. Freshness Expectations
**Default:** Current industry guidance where cited; avoid stale stats.
**Time-Sensitive Topics:** none
**Stable Topics:** refactoring patterns; Zod/validation examples
**Companion-Site Policy:** Only if needed for evolving sources.

## 6. Success Criteria
- [ ] Includes at least 3 workflows with prompt snippets
- [ ] Provides a small, reflowable comparison table
- [ ] Contains a tri-stage checklist and caution section
- [ ] Ends with a concrete next action

## 7. Risks & Assumptions
**Risks:** Over-reliance on AI for global edits; tool-specific guidance drift.
**Assumptions:** Reader has Node.js+TS stack and tests running locally.

## 8. Integration Notes
**Cross-References:** None required
**Tone Adjustments:** Keep direct and technical; minimize metaphor
**Special Instructions:** Use neutral tool references; avoid vendor lock-in language

---
Template: Article-Brief-Template v1.0
Date: 2025-11-13
