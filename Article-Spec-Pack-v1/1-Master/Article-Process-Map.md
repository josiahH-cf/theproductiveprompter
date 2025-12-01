# Article Process Map

**Purpose**  
Define the single-pass workflow for producing complete, publication-ready articles without multi-section stop-points or chapter architecture mechanics.

---

## Overview

Article production follows a **streamlined, single-pass flow** designed for standalone pieces. Unlike chapter-oriented workflows with stop-and-confirm behaviors, article production proceeds continuously from planning through final QA.

**Key principle:** Write the complete article in one continuous draft cycle, then apply quality controls silently before delivering final text.

---

## Process Flow

### 1. Plan (Article Brief)

**Input:** Article Brief created using [Article-Brief-Template.md](../2-Templates/Article-Brief-Template.md)

**Actions:**
- Define article objective and scope
- Identify target audience and constraints
- Set topic-specific freshness expectations
- Establish success criteria and evaluation checks

**Output:** Approved Article Brief serving as activation authority and operational directive

**Control documents loaded:**
- Unified Article Spec and/or Consolidated Article Spec
- Style Baseline (Directive)
- Brand Pack (Author Compass)
- Article Brief

---

### 2. Draft (Complete Article)

**Input:** Approved Article Brief + loaded control documents

**Actions:**
- Write complete article to natural completion (content-driven length)
- Follow the invisible structure: opening reality check → mental models → 3–5 workflows (When/Why/Pattern/Steps) → caution → tri-stage checklist → closing activation → optional further reading
- Use second-person developer voice; maintain purposeful sentences; apply anti-redundancy
- Cite facts with credible links by default; use APA only if the Brief requires it
- End with verification or next-action sentence (final-line rule)

**Output:** Complete first-pass article draft (internal, not yet delivered)

**No stop-points:** Article is drafted continuously without section breaks or confirmation pauses

---

### 3. Critic Loop (Silent Self-Check)

**Input:** Complete first-pass draft

**Actions (performed silently, never exposed to reader):**

#### Voice Check
- Verify second-person developer voice (direct “you”; occasional “we” for team context)
- Confirm confident, plain-spoken, instructive tone
- Validate natural sentence rhythm and paragraph structure
- Ensure natural voicing (feels human-written)

#### Focus Check
- Validate every sentence advances the idea, provides evidence, or strengthens arguments
- Confirm no filler, repetition, or tangential digressions
- Verify implicit structure (opening → mental models → workflows → caution → checklist → closing) is present
- Check final-line rule (last sentence is verification or next action, not a maxim)
 - For any detected workflows, verify schema elements are expressed naturally: PromptSpec (role/objective/constraints/success criteria), OutputMode, expected artifacts, ValidationPlan, ChangeIsolation, RollbackNotes, and Guardrails

#### Evidence Check
- Verify credible, linkable citations for non-common-knowledge facts (APA only if the Brief requires it)
- Validate freshness against Article Brief horizons
- Identify any time-sensitive claims lacking current sources and either generalize the claim or trigger Research Pass

**Actions:**
- Revise once internally to fix all identified issues
- **Never output** reasoning notes, checklists, or compliance reports

**Output:** Revised article draft (internal)

**Trigger for Research Pass:** If Evidence Check identifies freshness gaps or Article Brief requires verification

---

### 4. Research Pass (Conditional)

**Trigger conditions:**
- Freshness gate fires during Critic Loop (time-sensitive claim lacks current source)
- Article Brief explicitly requests verification
- Evidence Check identifies citation gaps

**Input:** Revised article draft + identified research needs

**Actions:**
- Search for current credible sources (prefer DOIs, stable URLs)
- Update or insert citations per Brief (APA only if required)
- Add companion-site callouts only if the Brief requests them
- **No-new-claims rule:** May replace, update, or remove evidence; must not introduce new argumentative claims
- Re-run Critic Loop silently to ensure consistency

**Output:** Research-updated article draft with current citations

**Reference:** See [Evidence-and-IP-Annex.md](../3-Annexes/Evidence-and-IP-Annex.md) for detailed research protocols

---

### 5. Final QA (Quality Gates)

**Input:** Critic-Loop-revised (and optionally research-updated) draft

**Gate checks (binding):**

#### Gate A — Baseline & Structure
- [ ] Style Anchor present (from Style Baseline; internal only)
- [ ] Implicit reference structure present (opening → mental models → workflows → caution → checklist → closing)
- [ ] Second-person voice maintained
 - [ ] For refactor workflows, output mode is diff and artifacts include a review checklist

#### Gate B — Critic Loop
- [ ] Single silent pass completed (Voice, Focus, Evidence)
- [ ] Final-line rule satisfied
- [ ] Anti-redundancy check passed
 - [ ] Workflow Schema fields present in natural language (PromptSpec, OutputMode, Artifacts, ValidationPlan, ChangeIsolation, RollbackNotes, Guardrails)

#### Gate C — Evidence & Freshness
- [ ] Citations present and credible (APA only if required by Brief)
- [ ] Dynamic freshness satisfied or claim generalized/updated
- [ ] Research Pass executed if triggered

**Actions:**
- Verify all gates passed
- If any gate fails, cycle back to appropriate step (Draft or Critic Loop)

**Output:** QA-passed article ready for references compilation

---

### 6. References (Consolidated)

**Input:** QA-passed article

**Actions:**
- Compile references per Brief (linkable by default; APA only if required)
- Include all sources cited in article
- Add DOIs or stable URLs where available
- Include accessed dates for web sources when APA is requested
- Add companion-site references only if requested by the Brief

**Output:** Complete article with consolidated references section

---

### 7. Package & Archive (Automation Hook)

**Input:** QA-passed article + consolidated references

**Actions:**
- Normalize folder layout using the packaging script so every supporting artifact lands in a predictable subfolder.
- Keep only `article.md` at the top level; move briefs, reports, references, drafts, and other assets to their respective folders.
- Move the originating chapter from `0-Article-Content/` into the article’s `sources/` directory so the intake folder stays clean while preserving traceability.
- Update CHANGELOG and manifest per standard practice once packaging succeeds.

**Helper command:**

```bash
python scripts/package_article.py \
	--article-folder "6-Completed-Articles/Article-YYYYMMDD-Slug" \
	--source-file "0-Article-Content/NN-chapter-name.md"
```

Use `--mapping pattern=folder` to extend or override default behaviors as the workflow evolves.

**Output:** Finalized article folder ready for publication handoff

---

## Precedence Order for Conflict Resolution

When instructions conflict across documents, resolve in this order:

1. **Style Baseline (Directive)**
2. **Brand Pack (Author Compass)**
3. **Article Brief (per-article)**
4. **Critic Loop (Single-Pass Self-Check)**
5. **Evidence & IP Annex (APA + IP)**
6. **Device Catalog (Annex)**

First document in list is the tiebreaker.

---

## Where Each Step Reads Its Controls

| **Step** | **Primary Control Documents** |
|----------|------------------------------|
| Plan | Article Brief Template, Brand Pack, Style Baseline |
| Draft | Article Master Spec, Article Brief, Style Baseline, Brand Pack |
| Critic Loop | Critic Loop (Single-Pass Self-Check), Article Brief, Style Baseline |
| Research Pass | Evidence & IP Annex, Article Brief |
| Final QA | Article Master Spec (compliance checklist) |
| References | Evidence & IP Annex (citation formatting per Brief) |

---

## Key Differences from Chapter Workflows

**Removed mechanics:**
- ❌ Multi-section stop-and-confirm behaviors ("Ready for next section?")
- ❌ Chapter/sub-chapter architecture and movement bridges
- ❌ Transitional bridge drafting steps
- ❌ Fixed numeric length bands (e.g., 700–1,200 words per movement)
- ❌ Hard-shape declarations and device activation headers in public text

**Retained mechanics:**
- ✅ Single silent Critic Loop (Voice, Focus, Evidence)
- ✅ Hard shape declaration and final-line rule
- ✅ Device gating via Brief activation
- ✅ Dynamic freshness with Research Pass
- ✅ APA citation and consolidated references
- ✅ Anti-redundancy checks

---

## Execution Notes

- **Context window management:** Articles are written in one continuous pass; no internal movement breaks required
- **Silent operation:** All quality checks happen internally; only final text is delivered
- **Device integration:** If planning aids (devices) are used internally, render as natural prose; never expose headers or labels
- **Length flexibility:** Write to completeness based on content strength, not to word counts

---

**Version:** 1.0  
**Date:** November 3, 2025  
**Status:** Normative — Defines the operational workflow for article production.
