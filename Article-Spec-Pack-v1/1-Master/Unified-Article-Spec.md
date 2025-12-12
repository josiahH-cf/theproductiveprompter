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

## Structural Expectations (Narrative Arc)

Write a natural article that moves through a **narrative arc**, not a rigid template. The arc flows from:

**Concrete problem → Conceptual reframing → Practical application → Closure**

Include *most* of these elements, but **vary their order, proportion, and naming** based on content needs. Not every article requires all elements. Combine or omit sections when they would be filler.

**Elements (use as building blocks, not as a fixed sequence):**
- **Opening hook:** A concrete scene, example, or scenario grounded in real work (e.g., the spam filter arms race, Maya's failed prompt). Never open with an abstract claim.
- **Conceptual grounding:** 1–3 mental models or definitions, woven into narrative or presented as a comparison table. These can appear in the opening or be integrated throughout.
- **Practical workflows:** 2–5 workflow patterns with clear triggers, mechanisms, and verification. These can be structured blocks OR narrative case studies.
- **Guardrails:** What not to outsource (security, architecture, compliance). Can be a standalone section OR integrated into workflows.
- **Verification:** A checklist, summary, or next step. Can be tri-stage OR a simpler closing.
- **Further Reading:** 3–6 credible links (optional).

**Gold standard:** Day 03 ("From Logic to Prediction") demonstrates structure emerging from content rather than from a template.

**Forbidden headers:** Do NOT use these as verbatim H2s: "The Reality Check," "Mental Models," "The Workflow," "Caution," "Tri-Stage Checklist," "Closing Activation." Instead, write descriptive headers specific to the topic (e.g., "Why RAG Fails at Scale" instead of "The Reality Check").

Length guidance: 1,500–2,500 words; expand only when adding concrete utility.

## Rhetorical Patterns & Devices

- **Contrast:** Bad vs. good prompting or old vs. new workflow. **Demonstrate** contrasts via tables, before/after examples, or scenarios rather than claiming them with "it's not X, it's Y" sentences.
- **Pattern Blocks:** Each workflow must contain a trigger (when), mechanism (prompt/code), and verification (steps), but these can be woven into a narrative, presented as a case study, or shown in a comparison table. Do NOT use fixed labels like "When/Why:" or "The Pattern:" as visible structure.
- **Prompt Snippets:** Include narrowly scoped prompt patterns (role, objective, constraints, success criteria).
- **Minimal Anecdotes:** Use sparingly to set stakes, not to pad. Open with a concrete scene when possible.
- **Tables:** Markdown, reflowable; use to prove distinctions (e.g., Logic vs. Prediction table in Day 03) rather than claiming them in prose.

## Depth & Density Guidelines

- Paragraphs: 2–5 sentences; each carries a single idea forward.
- Lists: Prefer bullets for steps, checks, and pitfalls.
- Examples: Realistic, self-contained; name tools/frameworks when helpful.
- Evidence: Link to reputable sources; APA only if the brief requires it.

## Factual Specificity Gate (High Priority)

If you cannot cite a source, **do not publish precise specifics**.

- Remove or generalize: exact dates, percentages, counts, “as of” claims, version numbers, token counts, market stats.
- Prefer bounded language: “commonly,” “in practice,” “providers vary,” “the details change,” “check vendor docs.”
- If a specific number is essential, include a credible link next to it.
- Do not add new statistics or numeric claims during polishing.

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
- Structure: Follows a narrative arc (concrete problem → conceptual reframing → practical application → closure). Order and sectioning fit the topic; no filler sections.
- Headers: Topic-specific headers; does not reuse generic framework headers; avoids internal scaffolding terms.
- Utility: Each workflow includes trigger, mechanism, and verification, expressed naturally (no fixed labels like “When/Why:” or “The Pattern:”).
- Workflow Schema: For any detected workflow, confirm PromptSpec present (role/objective/constraints/success criteria), OutputMode stated in natural language, ValidationPlan present (tests/logs/metrics/script), ChangeIsolation and RollbackNotes present in plain prose, and Guardrails stated.
- Factual specificity gate: Remove unsourced numbers, dates, “as of” claims, and version references; do not publish confident specifics without a link.
- Rhetorical hygiene: No “not X, it’s Y” lazy-contrast sentences unless immediately demonstrated with an example/table.
- Evidence: Link credible sources when making factual claims; APA only if brief requests; keep stats minimal and current.
- Anti-leak: No internal scaffolding terms or placeholders in public text.
- Readability: Short paragraphs; scannable lists; reflowable tables only when they add value.

## Variation Knobs (Use to Avoid Template Feel)

Deliberately vary 2–3 of these per article:

- Opener type: micro-story, scenario, before/after failure, “here’s the moment it breaks,” or a concrete artifact (log, prompt, diff).
- Proof style: comparison table, worked example, counterexample, small case study.
- Workflow presentation: labeled block vs narrative case study vs checklist-driven procedure.
- Closing type: verification, warning, callback, question, next action (avoid repeating the same closing formula).

Reference feel (do not copy phrases):
- Day 02 uses scenario + before/after prompts to prove the point.
- Day 03 uses a concrete analogy + a comparison table to establish the mental model.

---

Version: 1.1
Date: 2025-11-13
Precedence: Use alongside Style Baseline; overrides prior device/gate-heavy directives for public articles.
