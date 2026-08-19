# Article-Spec-Pack-v1 Changelog

**Purpose**
Complete record of all changes made during migration from chapter-oriented documentation to article-oriented documentation pack.

**Migration Date:** November 3, 2025
**Migration Source:** `9 Planning Docs - Chapter by Chapter Experiment/`
**Meta-Prompt:** `meta-prompt-plan v2.md`

---

## August 19, 2026 — Article Flow 2.1 (controller 2.1.0)

- Made `capture` the plain-language raw-idea entrypoint and added `list` as a compact index of seeds, resumable runs, canonical locations, and returned live links.
- Added public-surface voice review for the article title and description, a narrow deterministic check for high-confidence formulaic display text, and `amend` so the operator can repair those fields without replaying completed research or drafting.
- Kept repairs local to the failed stage, reset exhausted route counters after an explicit repair, allowed a disclosed same-route verification fallback when no independent route exists, and stopped treating an unreachable verification network as proof that a cited source is broken.
- Made repeated review of an unchanged approved artifact safe and allowed an operator to end a run at a hard gate without pretending the gate passed.
- Added publish-capability preflight and one resumable human handoff when the active host cannot push. A handoff can advance only after the approved file hashes are present at the current remote publication-branch commit; exact live-site verification remains the final gate.
- Added regression coverage for raw capture, findability, public metadata repair, targeted repairs, route recovery, inconclusive network transport, credential handoff, remote deployment proof, and continuation into live verification.

**Maturity note:** This release completes the lean reusable controller changes identified by the first real article trial. The author still owns journey scope, passage-level voice judgments, intent, recipe selection, proofreading, and publication approval. Those decisions are not inferred from a passing software suite.

---

## August 18, 2026 — Article Flow 2.0 (controller 2.0.8)

- Replaced the model-specific final rewrite prompt with `10-Final-Prose-Naturalization/Final-Prose-Naturalization-Directive.md`. Naturalization is now a conservative, model-neutral, fact-locked stage rather than the owner of the article's voice or structure.
- Made `workflow/workflow.json` the sole machine authority, generated `1-Master/Article-Workflow-v2.md` from it, declared one precedence chain, and marked superseded prose specifications as non-authoritative with machine-readable redirects.
- Rebuilt `scripts/article_flow.py` as a provider-neutral, resumable controller with JSON schemas, append-only event hashes, run locking, bounded repairs, complete task packets, hard and soft gates, and stable exit behavior.
- Added a paragraph-or-less seed entrypoint that preserves the seed verbatim, plans research before narrowing, and requires operator confirmation for intent, recipe, voice-probe, editorial, and publication decisions.
- Promoted the claim ledger, independent post-draft and post-edit verification, locked fields, article recipe, recent-post comparison, short voice probes, held-out voice testing, and public/private provenance boundary into reusable contracts.
- Added controller-hosted OpenAI, Anthropic, Google, OpenAI-compatible, and local-command adapters; a capability registry; fixture-backed evaluation records; canary controls; failure-aware fallback; and an honest active-host default until human-calibrated evaluations exist.
- Added versioned Windows and WSL installation, native launchers, thin Codex/Claude/shared Agent Skills adapters, adapter drift checks, and an optional local stdio MCP surface. Installed releases do not depend on the caller's working directory or the development repository's location.
- Replaced copied adapter command sequences with one disposable Agent Skills pointer. Local Codex/Claude adapters resolve the installed `article-flow` entrypoint, while separately uploaded ChatGPT and Claude account/Cowork skills dereference the same repository-owned `0-START-ARTICLE.md`; workflow changes therefore happen in one place.
- Superseded the Agent Skills entrypoint and copied runtime releases with the ordinary global `article-flow` command. Invoking it without arguments returns the complete machine-readable bootstrap and continuation contract; one PATH launcher per host points directly to the single local Git checkout, while installation retires controller-managed skills, redundant Windows launchers, and generated release copies. No account upload or provider-specific prompt remains.
- Added deterministic SHA-256 manifest build/check/explain commands and split health reporting into launcher, authoring, and release scopes. Protected drift blocks packaging, and release/publication require an approved clean checkout.
- Defined one package contract with `public/article.md` as the private-to-public source, rendered `docs/{slug}.html` as the public page, preserved prior article history across the home page, blog, feed, and sitemap, and separated package, publication plan, scoped approval, execution, and exact live verification.
- Added correction, refresh, supersession, and archival request states that preserve the current revision and require an explicit redirect/surface plan before any public change.
- Recorded the pre-implementation working tree byte-for-byte, classified all 22 observed entries, preserved three archival moves, and removed only the confirmed 46-byte `NUL` shell-error artifact.
- Independently verified the existing live article and discovery surfaces before changing publication templates; the live article and blog bytes matched the approved local revision at the time of the receipt.
- Controllers 2.0.1–2.0.7 made copied releases self-contained and hardened their provenance and portability checks. Controller 2.0.8 keeps the manifest, schema, clean-checkout, cross-host, and post-suite launcher proofs but makes both global launchers resolve the one editable local Git checkout instead of copying the controller. Product-specific discovery layers are replaced by the self-describing command.

**Maturity note:** The controller and local conformance suite are implemented, but empirical claims remain evidence-bound. Provider ranking is not promoted until the operator calibrates frozen fixtures across configured providers; the voice profile remains provisional until author judgments pass held-out checks; Gemini command invocation cannot be claimed until Gemini is installed; and each native host is reported separately until its launcher is actually exercised.

Entries below this point are historical migration records. They may describe superseded rules and do not override `workflow/workflow.json`, the current house policy, or an approved article recipe.

---

## Summary

This changelog documents the transformation of 9 chapter-oriented planning documents into a streamlined article-oriented specification pack. All changes align with the four binding decisions:

1. **Device authority:** Article Brief is the sole activation authority
2. **Length policy:** Dynamic, content-driven (no fixed bands)
3. **Stop-point protocol:** Disabled for single-pass articles
4. **Freshness horizon:** Dynamic, not fixed 12-month default

---

## New Documents Created

### 1-Master/

| File | Source | Change Type | Description |
|------|--------|-------------|-------------|
| `Article-Master-Spec.md` | Decomposed from `Meta-Prompt Instruction.md` | New | Single source of truth for article production; consolidates voice, structure, device gating, formatting, citations, QA gates, anti-redundancy, final-line rule, dynamic length policy |
| `Article-Process-Map.md` | Decomposed from `Meta-Prompt Instruction.md` | New | Single-pass workflow sequence without multi-section stop-points; replaces chapter movement mechanics |
| `Critic-Loop-(Single-Pass-Self-Check).md` | Updated from `Critic Loop (Single-Pass Self-Check).md` | Updated & Relocated | Updated Focus Check to reference Article Brief instead of Chapter/Sub-chapter Briefs; removed movement-level application; clarified article-scale scope |

### 2-Templates/

| File | Source | Change Type | Description |
|------|--------|-------------|-------------|
| `Article-Brief-Template.md` | Transformed from `Chapter Brief Template (Authoring Spec).md` | Transformed | Removed chapter movement/bridge/architecture steps; added fields for device activation (name, purpose, placement), dynamic freshness expectations, and evaluation criteria; positioned as device activation authority |

### 3-Annexes/

| File | Source | Change Type | Description |
|------|--------|-------------|-------------|
| `Device-Catalog.md` | Merged from `Device Toggle Guidance.md` + `Narrative Device Guidance and Formatting.md` | Merged | Consolidated device definitions, purposes, structural rules, and formatting; removed chapter-specific length bands and movement references; enforced activation header requirement; unified reflow-only formatting rules |
| `Evidence-and-IP-Annex.md` | Merged from `Citations & IP Note (APA + IP).md` + `Fact-Checking & Citation Protocol (APA Alignment).md` | Merged | Combined APA 7 usage, attribution/trademark guidance, companion-site callouts with Research Pass protocol; replaced fixed 12-month horizon with dynamic freshness policy (topic-specific, Article Brief-driven); retained "no-new-claims" rule and Critic Loop re-run requirement |

### 4-Carryover-Updated/

| File | Source | Change Type | Description |
|------|--------|-------------|-------------|
| `Brand-Pack-(Author-Compass).md` | Updated from `Brand Pack (Author Compass).md` | Updated | Updated precedence chain to reference Article Brief (position 3); removed chapter/sub-chapter mentions; clarified article-scale flowability; emphasized dynamic freshness policy; retained voice/neutrality guidance |
| `Style-Baseline-(Directive).md` | Updated from `Style Baseline (Directive).md` | Updated | Verified third-person requirement, prohibited practices, and compliance check remain intact; removed chapter-specific references; clarified article-scale application; retained all core voice and structural requirements including Style Anchor binding |

### Root-Level Documentation

| File | Source | Change Type | Description |
|------|--------|-------------|-------------|
| `0-README.md` | N/A | New | Pack overview, quick start guide, folder structure, precedence hierarchy, usage workflow, migration summary |
| `CHANGELOG.md` | N/A | New | This file; complete migration history with file-by-file changes |

---

## Documents Archived (Superseded)

### 9-Archive/_Superseded/

These documents are chapter-specific and replaced by article-focused equivalents:

| File | Reason for Superseding | Replacement |
|------|------------------------|-------------|
| `Sub-chapter Brief Template (Focused Spec).md` | Sub-chapter architecture not applicable to single-pass articles | `Article-Brief-Template.md` handles all article planning |
| `Meta-Prompt Instruction.md` | Chapter-oriented meta-prompt with stop-points and movement mechanics | Decomposed into `Article-Master-Spec.md` + `Article-Process-Map.md` |

**Note:** Original documents also copied to `9-Archive/_Originals/` for historical reference.

---

## Documents Archived (Originals)

### 9-Archive/_Originals/

Unmodified copies of all source documents for historical reference:

- `Brand Pack (Author Compass).md`
- `Chapter Brief Template (Authoring Spec).md`
- `Citations & IP Note (APA + IP).md`
- `Critic Loop (Single-Pass Self-Check).md`
- `Device Toggle Guidance.md`
- `Fact-Checking & Citation Protocol (APA Alignment).md`
- `Narrative Device Guidance and Formatting.md`
- `Style Baseline (Directive).md`
- `Sub-chapter Brief Template (Focused Spec).md`
- `Meta-Prompt Instruction.md`

---

## Detailed Changes by Document

### Article-Master-Spec.md (New)

**Created from:** Norms extracted from Meta-Prompt Instruction.md + consolidation of cross-document requirements

**Content:**
- Section 1: Scope & Application (article-specific, no chapter architecture)
- Section 2: Voice & Narrative Standards (from Style Baseline)
- Section 3: Dynamic Length Policy (content-strength-driven, no numeric bands)
- Section 4: Structural Requirements (hard shape, anti-redundancy, final-line rule)
- Section 5: Formatting & Reflowability (Kindle/EPUB3 requirements)
- Section 6: Device Activation & Gating (Article Brief as sole authority)
- Section 7: Evidence & Citation Standards (APA 7, dynamic freshness)
- Section 8: Quality Gates (A: Baseline & Shape, B: Critic Loop, C: Evidence & Freshness)
- Section 9: Single-Pass Article Workflow (one continuous draft cycle)
- Section 10: Precedence Model (Style Baseline → Brand Pack → Article Brief → etc.)
- Section 11: Compliance Checklist (binary gates)
- Section 12: Integration with Other Documents (cross-references)

**Removed:**
- Chapter/sub-chapter references
- Movement mechanics (700–1,200 word bands)
- Multi-section stop-points
- Chapter bridge directives

**Added:**
- Dynamic length policy language
- Article-scale scope definitions
- Single-pass workflow emphasis
- Links to annexes and templates

---

### Article-Process-Map.md (New)

**Created from:** Workflow sequence extracted from Meta-Prompt Instruction.md, adapted for articles

**Content:**
- Process overview (single-pass, no stop-points)
- Step 1: Plan (Article Brief)
- Step 2: Draft (complete article)
- Step 3: Critic Loop (silent self-check)
- Step 4: Research Pass (conditional, triggered by freshness gate)
- Step 5: Final QA (Gates A–C)
- Step 6: References (consolidated APA list)
- Precedence order for conflict resolution
- Control document mapping per step
- Key differences from chapter workflows

**Removed:**
- Multi-section drafting with stop-points ("Ready for next section?")
- Movement-level planning and bridges
- Chapter closing and transitional bridge steps
- Numeric length targets per movement

**Added:**
- Single-pass continuous drafting flow
- Dynamic freshness gate integration
- Conditional Research Pass trigger logic
- Comparison table (removed vs. retained mechanics)

---

### Article-Brief-Template.md (Transformed)

**Source:** Chapter Brief Template (Authoring Spec).md

**Changes:**
- Removed: Chapter architecture, movements, bridges, sub-chapter coordination
- Renamed: "Local Thesis" → "Central Thesis" (no chapter-level parent)
- Added: Device Activations section (name, purpose, placement fields)
- Added: Freshness Expectations section (dynamic horizons, time-sensitive vs. stable topics)
- Added: Success Criteria section (evaluation checks, quality benchmarks)
- Added: Risks & Assumptions section
- Simplified: Core Moves → Supporting Claims (argumentative structure, not movement sequence)
- Clarified: Article Brief is device activation authority and freshness source
- Retained: Objective, scope, constraints, integration notes

**New Fields:**
- Section 4: Device Activations (explicit name/purpose/placement per device)
- Section 5: Freshness Expectations (topic-specific horizons, companion-site policy)
- Section 6: Success Criteria (evaluation checks beyond standard gates)
- Section 7: Risks & Assumptions

---

### Device-Catalog.md (Merged)

**Sources:**
- Device Toggle Guidance.md
- Narrative Device Guidance and Formatting.md

**Merge Strategy:**
- Combined device purposes, activation rules, and formatting specifications
- Unified reflowability requirements
- Consolidated activation header enforcement

**Content:**
- Core Principles (OFF by default, activation header required, reflowable only)
- Activation Requirements (Article Brief authority, name/purpose/placement)
- Device Definitions:
  1. Prompt Plate
  2. Decision Tree / Checklist
  3. What the Papers Say
  4. Code Example Block (added)
- Formatting Standards (reflowability, accessibility, visual hierarchy)
- Device Gating Enforcement (Critic Loop checks)
- Future Device Extensions
- Quick Reference Checklist

**Removed:**
- Chapter-specific movement assumptions
- Numeric length bands for chapters/sub-chapters
- Sub-chapter device coordination

**Added:**
- Code Example Block device definition
- Unified activation header format enforcement
- Accessibility requirements
- Future extension protocol

---

### Evidence-and-IP-Annex.md (Merged)

**Sources:**
- Citations & IP Note (APA + IP).md
- Fact-Checking & Citation Protocol (APA Alignment).md

**Merge Strategy:**
- Combined APA citation standards with Research Pass protocol
- Integrated dynamic freshness policy throughout
- Unified companion-site callout guidance

**Content:**
- Section 1: Citation Standards (APA 7, format, content rules, common knowledge)
- Section 2: Dynamic Freshness Policy (principles, horizons by topic type, Article Brief controls, freshness gate trigger)
- Section 3: Research Pass Protocol (when to execute, 6-step process, no-new-claims rule)
- Section 4: Companion Website Integration (purpose, when to add callouts, placement)
- Section 5: Attribution of Third-Party Content (IP, trademarks, figures, datasets)
- Section 6: Reference List Requirements (structure, APA 7 formatting, DOIs/URLs, quality checks)
- Section 7: Integration with Drafting Process (during drafting, Research Pass, Final QA)
- Section 8: Error Handling (conflicting sources, unverifiable claims, paywalled sources)
- Quick Reference Checklist

**Removed:**
- Fixed 12-month freshness horizon
- Chapter-level fact-checking coordination
- Movement-scoped research passes

**Added:**
- Dynamic freshness horizons by topic type (rapidly evolving: 3–18 months; stable: any period)
- Article Brief as source of custom freshness requirements
- Detailed Research Pass 6-step protocol
- Error handling section (conflicting sources, unverifiable claims)
- Expanded companion-site integration guidance

---

### Brand-Pack-(Author-Compass).md (Updated)

**Source:** Brand Pack (Author Compass).md

**Changes:**
- Updated precedence chain: Position 3 now "Article Brief" (was "Chapter Brief")
- Updated precedence list to include Article Brief, remove Chapter/Sub-chapter Briefs
- Removed references to "chapter" and "sub-chapter" throughout
- Clarified: "Article Brief may override general guidance... but never overrides Style Baseline or Brand Pack voice fundamentals"
- Updated device policy: "activate only if Article Brief explicitly names..." (was "Chapter or Sub-chapter Brief")
- Updated integration notes: "At Article Start" (was "Movement Preamble")
- Updated freshness gate: "Dynamic freshness policy: No fixed 12-month default" (was implicit 12-month)
- Updated enforcement: References "article" instead of "chapter"
- Added: "Voice Consistency Across Articles" section (article-scale variation guidance)
- Added: Brand voice examples (preferred vs. avoid)

**Retained:**
- All core voice requirements (neutral, precise, evidence-led, third-person)
- Device policy fundamentals (OFF by default)
- Freshness gate mechanism (trigger Research Pass or bracket)
- Enforcement checks (Style Anchor, shape, final-line, device activation, freshness)

---

### Style-Baseline-(Directive).md (Updated)

**Source:** Style Baseline (Directive).md

**Changes:**
- Updated Section 8 Compliance Check: "article" instead of "chapter/section"
- Updated Section 9 Integration Rule: "Article Brief" in loading order (was "Chapter Brief")
- Added note: "All articles must pass compliance check before delivery"
- Clarified: Style Baseline is "first in precedence" for articles
- Updated examples: Removed chapter context, generalized to article scale
- Retained all prohibited practices and examples
- Added: "Anti-Patterns to Avoid" section with examples

**Retained:**
- All core voice requirements (third-person only, Style Anchor binding)
- All tone & cadence guidance (sentence variety, natural voicing, paragraph structure)
- All clarity & density requirements (written with intent, concrete over abstract)
- All prohibited practices (anthropomorphizing AI, over-explaining, rhetorical excess)
- Hard shape declaration requirement
- Final-line rule
- Anti-redundancy rule
- All writing style examples (use as style guide, not content)
- Full compliance checklist

**No chapter dependencies found** — Style Baseline was already content-agnostic.

---

### Critic-Loop-(Single-Pass-Self-Check).md (Updated & Relocated)

**Source:** Critic Loop (Single-Pass Self-Check).md
**New Location:** `1-Master/` (was in general planning docs folder)

**Changes:**
- Section title: "How the Critic Loop Fits in Article Production" (was "Drafting Process")
- Updated load order: "Article Brief" (was "Active Chapter Brief" and "Relevant Sub-chapter Briefs")
- Updated generation cycle: "complete article" (was "section (chapter or sub-chapter)")
- Updated Voice Check: Removed chapter-specific language
- Updated Focus Check:
  - "Article objective & thesis alignment" (was "Brand Pack's mission... Chapter and Sub-chapter Briefs")
  - Removed "Movement & length compliance" check (700–1,200 word bands)
  - Retained hard-shape conformity, final-line rule, device gating, anti-redundancy
- Updated Evidence Check: "Article Brief freshness horizons" (was implicit chapter-level)
- Updated Integration section: "Article Workflow" (was chapter workflow with movements)
- Updated precedence position: Shows Article Brief at position 3
- Added: "Re-Running After Research Pass" subsection
- Added: "Quality Gate Integration" section (Gate B)

**Retained:**
- Three-check structure (Voice, Focus, Evidence)
- Single silent pass requirement
- Output requirement (only final revised text, no notes)
- All check criteria and revision requirements
- "What This Document Solves" summary

---

## Precedence Chain Changes

**Original (Chapter-Oriented):**
1. Style Baseline (Directive)
2. Brand Pack (Author Compass)
3. Chapter Brief
4. Sub-chapter Brief
5. Critic Loop
6. Citations & IP Note
7. Narrative Devices

**New (Article-Oriented):**
1. Style Baseline (Directive)
2. Brand Pack (Author Compass)
3. **Article Brief** ← Changed
4. Critic Loop (Single-Pass Self-Check) ← Promoted
5. Evidence & IP Annex (APA + IP) ← Merged & renamed
6. Device Catalog (Annex) ← Merged & renamed

**Changes:**
- Removed: Chapter Brief, Sub-chapter Brief (replaced by single Article Brief)
- Renamed: "Citations & IP Note" → "Evidence & IP Annex"
- Renamed: "Narrative Devices" → "Device Catalog"
- Promoted: Critic Loop from position 5 to position 4

---

## Key Principle Changes

| Principle | Chapter-Oriented | Article-Oriented |
|-----------|------------------|------------------|
| **Workflow** | Multi-section with stop-points ("Ready for next section?") | Single-pass continuous draft |
| **Length** | Fixed bands (700–1,200 words per movement, 4,500–9,000 per chapter) | Dynamic, content-driven (generally ~2,000–5,000, varies by scope) |
| **Device Authority** | Chapter Brief OR Sub-chapter Brief | Article Brief ONLY |
| **Freshness** | Implicit 12-month default for time-sensitive claims | Dynamic, topic-specific (3–18 months for evolving; any period for stable) |
| **Structure** | Chapters → Sub-chapters → Movements → Sections | Single article (no internal architecture) |
| **Bridges** | Transitional bridges between movements/sub-chapters | Not applicable (single continuous piece) |
| **Critic Loop Scope** | Per movement or section | Entire article after complete draft |
| **Research Pass** | Movement-level or chapter-level | Article-level (after full draft) |

---

## File Moves & Migrations

### Created (New Files)
- `0-README.md` (root)
- `CHANGELOG.md` (root)
- `1-Master/Article-Master-Spec.md`
- `1-Master/Article-Process-Map.md`
- `1-Master/Critic-Loop-(Single-Pass-Self-Check).md` (relocated)
- `2-Templates/Article-Brief-Template.md`
- `3-Annexes/Device-Catalog.md`
- `3-Annexes/Evidence-and-IP-Annex.md`
- `4-Carryover-Updated/Brand-Pack-(Author-Compass).md`
- `4-Carryover-Updated/Style-Baseline-(Directive).md`

### Archived (Originals)
All source documents copied to `9-Archive/_Originals/`:
- `Brand Pack (Author Compass).md`
- `Chapter Brief Template (Authoring Spec).md`
- `Citations & IP Note (APA + IP).md`
- `Critic Loop (Single-Pass Self-Check).md`
- `Device Toggle Guidance.md`
- `Fact-Checking & Citation Protocol (APA Alignment).md`
- `Narrative Device Guidance and Formatting.md`
- `Style Baseline (Directive).md`
- `Sub-chapter Brief Template (Focused Spec).md`
- `Meta-Prompt Instruction.md`

### Archived (Superseded)
Moved to `9-Archive/_Superseded/`:
- `Sub-chapter Brief Template (Focused Spec).md` (replaced by Article Brief Template)
- `Meta-Prompt Instruction.md` (decomposed into Article Master Spec + Process Map)

---

## Quality Gate Changes

**Original (Chapter):**
- Gate checks were chapter/movement-scoped
- Length compliance against numeric bands
- Movement-level review

**New (Article):**
- **Gate A — Baseline & Shape Declared:** Style Anchor present, single hard shape declared, third-person voice
- **Gate B — Critic Loop:** Voice/Focus/Evidence checks completed, final-line rule satisfied, device activations validated, anti-redundancy passed
- **Gate C — Evidence & Freshness:** APA compliance verified, dynamic freshness satisfied or gaps bracketed, Research Pass executed if triggered

All gates apply to complete article as single unit.

---

## Testing & Validation

**Acceptance Criteria (from meta-prompt):**
- [x] New `Article-Spec-Pack-v1/` folder exists with exact structure
- [x] All chapter-specific documents archived; no chapter-only constraints in master/specs
- [x] Device activation governed solely by Article Brief
- [x] Length policy dynamic and not expressed as numeric bands
- [x] Freshness rules dynamic with topic-specific horizons; no fixed 12-month default
- [x] Gates A–C referenced by name across relevant files
- [x] Complete CHANGELOG.md records all changes and destinations

**Sanity Checks:**
- [x] All normative rules for article production in Article-Master-Spec.md
- [x] No contradictory requirements in annexes/templates
- [x] Precedence chain consistent across all documents
- [x] All cross-references use correct file paths
- [x] Device activation requirements consistent (Article Brief authority)
- [x] Dynamic freshness policy applied throughout (no fixed horizons)

---

## Migration Statistics

- **Source documents:** 10 (9 planning docs + 1 meta-prompt instruction)
- **New documents created:** 10
- **Documents updated and carried over:** 4
- **Documents merged:** 4 (into 2 annexes)
- **Documents superseded:** 2
- **Total lines of normative text:** ~2,800 (estimated)
- **Precedence chain positions:** 6 (reduced from 7)

---

## Version Control

**Pack Version:** 1.0
**Migration Date:** November 3, 2025
**Status:** Production-ready

All documents in `1-Master/`, `2-Templates/`, `3-Annexes/`, and `4-Carryover-Updated/` are normative and binding for article production as of this date.

---

## Future Changelog Entries

Future updates to this pack should append to this file with:
- Date of change
- Document(s) affected
- Change type (addition, update, removal, merge)
- Rationale
- Version number increment

**Format:**
```
## [Version X.Y] - YYYY-MM-DD

### Changed
- File: description of change

### Added
- File: description of addition

### Removed
- File: description of removal (with superseding document if applicable)
```

---

**End of Changelog**

---

## [Article Completion] - 2025-11-14 (From Logic to Prediction)

### Added
- `6-Completed-Articles/Article-20251114-From-Logic-to-Prediction-v1.0.md` — Final article with metadata, gates summary, and metrics
- `6-Completed-Articles/Article-20251114-From-Logic-to-Prediction/article.md` — Clean public article text (copy-paste ready)
- `6-Completed-Articles/Article-20251114-From-Logic-to-Prediction/brief.md` — Brief used for this article (archival copy alongside article)

### Moved
- Brief archived to `9-Archive/_Completed-Briefs/Article-Brief-from-logic-to-prediction.md` and copied to `6-Completed-Articles/Article-20251114-From-Logic-to-Prediction/brief.md`

### Notes
- Gates A–C passed on draft; single APA citation (Vaswani et al. 2017 — Transformer paper)
- Word count: 1,784 (within acceptable range for scope)
- Execution mode: One-shot audacious (all phases in single pass)
- Article bridges foundational concepts (Articles 1-2) to technical mechanics (Articles 4-5)

---

## [Version 1.1] - 2025-11-03 (Post-Migration Enhancement)

### Added
- **File:** `Article-Execution-Meta-Prompt.md` — Autonomous execution controller with 7-phase workflow, anti-degradation controls, and human-in-the-loop approval gates
- **File:** `manifest.json` — Integrity manifest with MD5 checksums for all normative documents, precedence tracking, and verification rules
- **Folder:** `5-Active-Briefs/` — Storage for Article Briefs in development with status tracking
- **Folder:** `6-Completed-Articles/` — Archive for finalized articles with metadata and quality gate verification
- **File:** `5-Active-Briefs/README.md` — Workflow documentation for brief creation and approval
- **File:** `6-Completed-Articles/README.md` — Structure documentation for completed article storage

### Changed
- **File:** `0-README.md` — Updated folder structure to include new folders and execution meta-prompt; added "Autonomous Execution Mode" section; enhanced Quick Start with manual vs. autonomous workflows

### Rationale
Enhancement to support fully automated article production with integrity checking and anti-degradation safeguards. The execution meta-prompt provides a controlled, traceable workflow that prevents semantic drift and ensures all articles meet quality gates A–C.

**Key Features:**
- Checksum verification prevents silent document changes
- Lock/unlock mechanism protects normative files
- Diff enforcement ensures transparency of all modifications
- Run ID tracking provides complete audit trail
- Phase-based execution with approval gates maintains human oversight

---

## [Version 1.2] - 2025-11-03 (One-Shot Execution Components)

### Added
- **File:** `Sample-Completed-Article-Annotated.md` — Annotated example article showing compliance with all Article-Spec-Pack-v1 requirements, including Article Brief, complete article text with inline annotations, Gate A/B/C validation, and article metrics
- **File:** `Article-Output-Format-Template.md` — Standardized delivery format for Phase 6 (Archival & Logging) with 6 sections: Article Metadata, Article Text, Gate Validation Summary, Article Metrics, Copy-Paste Ready Version, and Archival Information
- **File:** `PDF-Upload-Quick-Start-Guide.md` — Deployment guide for Gemini 2.5 Pro web GUI (PDF upload only), including PDF preparation, meta-prompt template, execution workflow, troubleshooting, and manual archival instructions
- **File:** `4-Carryover-Updated/Default-Style-Anchor-Card.md` — Default 112-word Style Anchor for articles that don't specify custom voice, with cadence patterns, lexicon patterns, and Critic Loop integration

### Changed
- **File:** `3-Annexes/Evidence-and-IP-Annex.md` — Added Section 7 "Citation Guidance for Models Without Real-Time Web Search" with no-search citation strategies, source hierarchy tiers, and bracketing templates; renumbered subsequent sections (7→8: Integration, 8→9: Error Handling)

### Rationale
Enables true one-shot article generation in constrained environments (Gemini web GUI with PDF uploads only). The sample article provides a concrete reference, the output template standardizes deliverables, the PDF guide enables deployment, the Default Style Anchor fills a common gap, and the no-search citation guidance supports models without web access.

**Key Features:**
- Sample article demonstrates all requirements with annotations for clarity
- Output template ensures consistent Phase 6 delivery across all executions
- PDF guide provides complete workflow for environments without file system access
- Default Style Anchor provides ready-to-use voice baseline (eliminates blocker)
- No-search citation guidance supports training-data-only execution environments

---

**Changelog updated with one-shot execution components**

---

## [Documentation Update] - 2025-11-13 (Blog Workflow + Copilot Instructions)

### Added
- **File:** `Blog-Output-Format-Template.md` — CMS/blog-ready format with YAML front matter, device headers, reflowable tables, and APA references.
- **File:** `copilot-instructions.md` — One-command operator flow to “write the next blog post” using Phases 0–9, precedence model, Gates A–C, packaging, and logging requirements.

### Changed
- **File:** `0-README.md` — Added Blog-Ready Output (End-State), Blog Packaging step, and references to the new template and Copilot instructions.

### Completed
- Finalized blog folder for Article 1 at `6-Completed-Articles/Article-1-Beyond-the-Hype/index.md`.
- Updated full article (Research Pass + voice refinement) at `6-Completed-Articles/Article-20251113-Beyond-the-Hype-Defining-Todays-AI-v1.1.md`.

### Rationale
Sets the end-state as a finalized, CMS-ready blog folder and provides a repeatable Copilot entrypoint to produce compliant blog posts that adhere to the Brand Pack, Style Baseline, and quality Gates A–C.

### Maintenance
- Retired `6-Completed-Articles/Article-20251113-Beyond-the-Hype-Defining-Todays-AI-v1.0.md` in favor of v1.1 as the single source of truth.
- Moved active brief out of `5-Active-Briefs` (archived Markdown copy already in `9-Archive/_Completed-Briefs/`).

---

## [Article Completion] - 2025-11-13 (Professionals Playbook — Early Win)

### Added
- `6-Completed-Articles/Article-20251113-Professionals-Playbook-Early-Win-v1.0.md` — Final article with metadata, internal gate summary, and metrics.
- `6-Completed-Articles/Article-20251113-Professionals-Playbook-Early-Win/article.md` — Clean public article text (copy‑paste ready).
- `6-Completed-Articles/Article-20251113-Professionals-Playbook-Early-Win/brief.md` — Brief used for this article (archival copy alongside article).

### Moved
- Brief archived to `6-Completed-Articles/Article-20251113-Professionals-Playbook-Early-Win/brief.md` and copied to `9-Archive/_Completed-Briefs/Article-Brief-professionals-playbook-early-win.md`.

### Notes
- Gates A–C passed on draft; no APA references required (no quantitative claims). Word count recorded at 1,753.


---

## [Article Completion] - 2026-03-17 (AI First Principles: Right Tool)

### Added
- 6-Completed-Articles/Article-20260317-ai-first-principles-right-tool/article.md - Clean public article text following the consolidated article spec.
- 6-Completed-Articles/Article-20260317-ai-first-principles-right-tool/briefs/brief.md - Approved brief used for the article.
- 6-Completed-Articles/Article-20260317-ai-first-principles-right-tool/reports/Article-20260317-ai-first-principles-right-tool-v1.0.md - Versioned draft/report copy.
- 6-Completed-Articles/Article-20260317-ai-first-principles-right-tool/references/references.md - Link-based supporting references.

### Moved
- Source intake moved from 0-Article-Content/20260317-ai-first-principles-right-tool.md to 6-Completed-Articles/Article-20260317-ai-first-principles-right-tool/sources/20260317-ai-first-principles-right-tool.md via scripts/package_article.py.

### Notes
- Public article kept the consolidated spec constraints: developer-facing voice, no internal scaffolding terms, practical workflow guidance, and link-based references.
- Article generated from vault intake source AI first principles and deciding when AI is the right tool.md and packaged into the completed-articles structure.
