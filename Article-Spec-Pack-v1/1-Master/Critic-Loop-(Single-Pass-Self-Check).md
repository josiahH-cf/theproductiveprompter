# Critic Loop (Single-Pass Self-Check)

**Purpose**  
Guarantee that every drafted article meets the book's style, evidence, and argument requirements **before** it reaches the human author. The Critic Loop enforces compliance through a **single self-review and revision cycle** embedded in the article production process.

---

## How the Critic Loop Fits in Article Production

### Load Order Before Drafting

1. Style Baseline (Directive)
2. Unified/Consolidated Article Spec
3. Brand Pack (Author Compass)
4. Article Brief
5. Critic Loop (this document)

### Generation Cycle

1. Model **drafts the complete article**
2. Immediately performs the Critic Loop (three checks below)
3. Revises once—**silently**—to fix issues
4. Returns **only the revised text**, never intermediate or uncorrected draft

This guarantees compliance without adding filler or meta-commentary to the final manuscript.

---

## The Three Checks

Each check is **mandatory** and must be applied in order.  
If any criterion fails, the model **must revise** before producing final output.

---

### 1. Voice Check

Ensure the draft fully aligns with the **Style Baseline (Directive)**:

#### Voice
- Default to **second-person developer voice** (direct “you”; occasional “we” for team context)
- No first-person singular unless quoting; keep tone confident, plain-spoken, instructive

#### Tone & Cadence
- Confident, plain-spoken, instructive tone
- Subtle clever humor as appropriate (never forced or silly)
- Sentence rhythm and paragraphing consistent with Style Baseline:
  - Varied, intentional sentence structure
  - Natural flow (not robotic or formulaic)
  - No fixed paragraph word count requirement

#### Style Anchor Binding
- Verify 100–150 word Style Anchor Card is present
- Confirm cadence and lexicon match the Style Anchor
- If Style Anchor is missing, halt and request it

**Action if Voice Check fails:**  
Revise sentences/paragraphs to align with Style Baseline requirements.

---

### 2. Focus Check

Validate that the text fulfills the **Brand Pack's mission** and the **specific objectives** of the Article Brief:

#### Written with Intent
- Every sentence must:
  - Advance the idea, OR
  - Provide evidence, OR
  - Strengthen arguments, OR
  - Set up a transition
- No filler, repetition, or tangential digressions
- If sentence serves no purpose, remove it

#### Article Objective & Thesis Alignment
- Confirm article addresses all objectives stated in Article Brief
- Verify central thesis is developed and supported
- Ensure supporting claims are present and evidenced
- Check that scope boundaries (inclusions/exclusions) are respected

#### Implicit Structure
- Verify the implicit structure is present end-to-end:
  opening reality check → mental models/definition → 3–5 workflows (When/Why/Pattern/Steps) → caution → tri-stage checklist → closing activation → optional further reading

#### Final-Line Rule
- Ensure last sentence is a **verification or next action**
- Never a maxim, aphorism, or philosophical statement
- If final line violates rule, rewrite it

#### Anti-Leak
- Ensure no internal scaffolding terms (Device, Gate, Shape, Style Anchor, Critic Loop, Research Pass) or activation headers appear in public text

#### Anti-Redundancy
- Scan for sentences duplicating earlier content (>5 identical words)
- Remove redundant sentences
- Ensure each paragraph contributes unique information

**Action if Focus Check fails:**  
Rewrite sections to fulfill objectives, remove filler/redundancy, enforce hard shape, fix final line, or remove unapproved devices.

---

### 3. Evidence & Attribution Check

Verify that all claims meet the book's evidence and citation standards:

#### Citation Policy
- Use credible, linkable citations by default. Apply APA only if the Article Brief requires it.
- Confirm references/links can be compiled at article end if needed.

#### Freshness Verification
- Identify all time-sensitive claims (market data, statistics, regulations, technical capabilities)
- Verify each has current source per Article Brief freshness horizons
- If source is stale or missing, either generalize the claim or **trigger Research Pass**. Do not leak bracketed placeholders into public text.

#### Opinion vs. Fact Labeling
- Ensure opinions are clearly signaled (e.g., "Evidence suggests…" "This analysis indicates…")
- Distinguish between established facts and interpretations
- If claim is presented as fact but lacks citation, either:
  - Add citation, OR
  - Reframe as interpretation, OR
  - Remove claim

#### Research Gaps Flagged
- When credible sources are unavailable or claim requires further research, explicitly mark:
  > "[Writer to research topic]"
- Never fabricate citations
- Never use unreliable sources to fill gaps

**Action if Evidence Check fails:**  
Add missing citations, update stale sources, flag research gaps, or trigger Research Pass.

---

## Output Requirement

After performing all three checks and making one internal revision, the model outputs:

- **Only the final, revised text**
- **No checklists, reasoning notes, or compliance reports**

The Critic Loop is **invisible to the reader** but ensures the article meets professional publishing standards.

---

## Integration with Article Workflow

### Placement in Process Flow

The Critic Loop executes **after complete article draft** and **before Research Pass** (if triggered).

**Process sequence:**
1. Plan (Article Brief)
2. Draft (complete article)
3. **Critic Loop** ← (Voice, Focus, Evidence checks)
4. Research Pass (if triggered by Evidence Check)
5. Re-run Critic Loop (after Research Pass updates)
6. Final QA
7. References

### Precedence Position

**Fourth in precedence chain:**
1. Style Baseline (Directive)
2. Unified/Consolidated Article Spec
3. Brand Pack (Author Compass)
4. **Critic Loop** ← This document
5. Article Brief
6. Evidence & IP Annex

### Re-Running After Research Pass

If a Research Pass is triggered and updates the article:
- **Must re-run Critic Loop** after research changes
- Verify research updates didn't introduce voice drift or focus issues
- Confirm new citations are formatted correctly
- Ensure **no-new-claims rule** was followed (research may update evidence but not introduce new arguments)

---

## Quality Gate Integration

The Critic Loop enforces **Gate B** in the article quality system:

### Gate B — Critic Loop
- [ ] Single silent pass completed (Voice, Focus, Evidence)
- [ ] Final-line rule satisfied
- [ ] Device activations validated (headers present if used)
- [ ] Anti-redundancy check passed

**Reference:** See [Article-Master-Spec.md](../1-Master/Article-Master-Spec.md) for full quality gate definitions.

---

## What This Document Solves

- **Voice integrity:** Enforces third-person, confident, concise style and Style Anchor binding
- **Argument fidelity:** Ensures article fulfills objectives without filler; enforces hard-shape and final-line rules
- **Citation quality:** Guarantees fresh, verifiable APA citations; triggers Research Pass or flags gaps; enforces device gating

---

## Execution Notes

### Silent Operation
- All checks happen internally
- Never output reasoning or compliance notes
- Only deliver final revised text

### Single-Pass Revision
- One revision cycle only
- Don't iterate multiple times
- Trust the systematic three-check process

### Scope
- Applies to entire article as a single unit
- No section-by-section application needed (articles are single-pass)
- Comprehensive review of whole text

---

## Quick Reference: Critic Loop Checklist

**Voice Check:**
- [ ] Second-person developer voice (direct “you”; occasional “we”)
- [ ] Confident, plain-spoken, instructive tone
- [ ] Style Anchor Card bound (cadence and lexicon match; internal only)
- [ ] Sentence variety and paragraph structure per Style Baseline

**Focus Check:**
- [ ] Every sentence advances, evidences, or transitions
- [ ] Article objectives and thesis fulfilled
- [ ] Implicit structure present (opening → mental models → workflows → caution → checklist → closing)
- [ ] Final line is verification or next action
- [ ] No internal scaffolding terms or activation headers in public text
- [ ] No redundant sentences (>5 identical words)

**Evidence Check:**
- [ ] Credible citations present (APA only if required by Brief)
- [ ] Freshness verified per Article Brief horizons
- [ ] If missing or stale, generalize the claim or trigger Research Pass (no bracket placeholders in public text)
- [ ] Opinions clearly labeled
- [ ] No fabricated or unreliable citations

**Output:**
- [ ] Only revised text returned (no notes or checklists)

---

**Version:** 1.0 (Article-oriented)  
**Date:** November 3, 2025  
**Status:** Normative — Updated to support single-pass article production.  
**Changes from original:** Removed chapter/sub-chapter and movement references; updated Focus Check to reference Article Brief instead of Chapter/Sub-chapter Briefs; clarified article-scale application; maintained three-check structure.
