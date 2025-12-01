This document has been archived.

See: `9-Archive/_Superseded/MIGRATION-COMPLETE.md`

---

## What Was Created

A complete, self-contained specification pack for producing publication-ready articles without chapter-oriented architecture.

### New Folder Structure

```
Article-Spec-Pack-v1/
├── 0-README.md                          ← Start here
├── CHANGELOG.md                         ← Complete migration history
├── 1-Master/                            ← Core operational documents
│   ├── Article-Master-Spec.md           ← Single source of truth ⭐
│   ├── Article-Process-Map.md           ← Workflow guide
│   └── Critic-Loop-(Single-Pass-Self-Check).md
├── 2-Templates/
│   └── Article-Brief-Template.md        ← Planning template
├── 3-Annexes/
│   ├── Device-Catalog.md                ← Device definitions
│   └── Evidence-and-IP-Annex.md         ← Citations & freshness
├── 4-Carryover-Updated/
│   ├── Brand-Pack-(Author-Compass).md   ← Brand voice
│   └── Style-Baseline-(Directive).md    ← Voice requirements ⭐
└── 9-Archive/
    ├── _Originals/                      ← All source documents
    └── _Superseded/                     ← Retired docs with notes
```

---

## Quick Start Guide

### For Article Production

1. **Read the Master Spec**  
   → `1-Master/Article-Master-Spec.md` — Everything you need to know

2. **Create an Article Brief**  
   → Use `2-Templates/Article-Brief-Template.md`

3. **Load documents in order:**
   - Style-Baseline-(Directive).md
   - Brand-Pack-(Author-Compass).md
   - Your Article Brief
   - Article-Master-Spec.md
   - Critic-Loop-(Single-Pass-Self-Check).md

4. **Draft article** following the Master Spec

5. **Apply Critic Loop** silently (Voice → Focus → Evidence)

6. **Compile references** per Evidence-and-IP-Annex.md

### For Understanding the Migration

1. **Read the README**  
   → `0-README.md` — Overview and usage

2. **Review the CHANGELOG**  
   → `CHANGELOG.md` — Every change documented

3. **Check superseded notes**  
   → `9-Archive/_Superseded/` — Why documents were retired

---

## Key Changes from Chapter Pack

### ✅ What's New

- **Dynamic length policy** — Content-driven, not fixed word counts
- **Single-pass workflow** — No stop-and-confirm behaviors
- **Article Brief as device authority** — Single activation source
- **Dynamic freshness** — Topic-specific horizons, not fixed 12-month
- **Unified device catalog** — All devices in one reference
- **Merged evidence annex** — APA + freshness + research protocol

### ❌ What's Removed

- Chapter/sub-chapter architecture
- Movement-level drafting (700–1,200 word segments)
- Multi-section stop-points ("Ready for next section?")
- Transitional bridges between sections
- Fixed numeric length bands
- Fixed 12-month freshness default

### ♻️ What's Updated

- **Brand Pack** — References Article Brief instead of Chapter/Sub-chapter Briefs
- **Style Baseline** — Clarified article-scale application
- **Critic Loop** — Updated Focus Check to reference Article Brief

---

## Precedence Chain (Conflict Resolution)

When instructions conflict, this order wins:

1. **Style-Baseline-(Directive).md** ← Highest precedence
2. Brand-Pack-(Author-Compass).md
3. Article Brief (your specific article)
4. Critic-Loop-(Single-Pass-Self-Check).md
5. Evidence-and-IP-Annex.md
6. Device-Catalog.md

**First in list is the tiebreaker.**

---

## Four Binding Decisions

All documents enforce these four decisions from the meta-prompt:

1. **Device authority:** Article Brief is the sole activation authority
2. **Length policy:** Dynamic, content-driven (no fixed bands)
3. **Stop-point protocol:** Disabled for single-pass articles
4. **Freshness horizon:** Dynamic, not fixed 12-month default

---

## Document Summaries

### 📘 Article-Master-Spec.md
**The single source of truth for article production.**

Contains:
- Voice & narrative standards (third-person, purposeful sentences)
- Dynamic length policy (content-driven)
- Structural requirements (hard shape, anti-redundancy, final-line rule)
- Formatting & reflowability (Kindle/EPUB3)
- Device activation & gating (Article Brief authority)
- Evidence & citation standards (APA 7, dynamic freshness)
- Quality gates (A: Baseline & Shape, B: Critic Loop, C: Evidence & Freshness)
- Compliance checklist

**When to use:** Reference for all article production requirements.

---

### 🗺️ Article-Process-Map.md
**The single-pass workflow guide.**

Steps:
1. Plan (Article Brief)
2. Draft (complete article)
3. Critic Loop (silent Voice/Focus/Evidence checks)
4. Research Pass (if triggered by freshness gate)
5. Final QA (verify Gates A–C)
6. References (consolidated APA list)

**When to use:** Understand the workflow sequence and where each step reads its controls.

---

### 📝 Article-Brief-Template.md
**The planning template for each article.**

Sections:
- Objective & scope
- Core argument (thesis + supporting claims)
- **Device activations** (name, purpose, placement)
- **Freshness expectations** (dynamic, topic-specific)
- Success criteria
- Risks & assumptions

**When to use:** Create before drafting any article. This is the device activation authority.

---

### 🎨 Style-Baseline-(Directive).md
**The highest-precedence voice requirements.**

Requirements:
- Third-person only (no "I/we/you")
- Style Anchor binding (100–150 words)
- Purposeful sentences (advance, evidence, strengthen, transition)
- Prohibited practices (no anthropomorphizing AI, over-explaining, rhetorical excess)
- Hard shape declaration
- Final-line rule (verification or next action, not maxim)
- Anti-redundancy

**When to use:** First document to load. Non-negotiable requirements.

---

### 🧭 Brand-Pack-(Author-Compass).md
**Brand voice and neutrality standards.**

Covers:
- Neutral, precise, evidence-led voice
- Precedence rule (position 2)
- Device policy (OFF by default)
- Integration with drafting process
- Freshness gate (dynamic)
- Enforcement checks

**When to use:** Second document to load. Establishes brand voice.

---

### ✅ Critic-Loop-(Single-Pass-Self-Check).md
**The quality enforcement protocol.**

Three checks:
1. **Voice Check** — Third-person, Style Anchor binding, tone/cadence
2. **Focus Check** — Intent, objectives, hard shape, final line, devices, anti-redundancy
3. **Evidence Check** — APA citations, freshness, opinion labeling, research gaps

**When to use:** Apply silently after complete article draft. One revision cycle.

---

### 🎭 Device-Catalog.md
**All approved narrative devices and formatting rules.**

Devices:
1. Prompt Plate (before/after prompts with outcomes)
2. Decision Tree / Checklist (structured troubleshooting)
3. What the Papers Say (academic findings)
4. Code Example Block (executable code)

**When to use:** Reference when Article Brief activates a device. Defines formatting and mechanics.

---

### 📚 Evidence-and-IP-Annex.md
**APA citations, freshness policy, and IP rules.**

Covers:
- APA 7 citation standards
- Dynamic freshness policy (topic-specific horizons)
- Research Pass protocol (6-step process)
- Companion website integration
- Third-party content attribution (trademarks, IP)
- Reference list requirements

**When to use:** Reference for all citation needs and Research Pass execution.

---

## Common Workflows

### Writing a New Article

```
1. Fill out Article-Brief-Template.md
   - Define objective, scope, thesis
   - Activate devices (if needed)
   - Set freshness expectations

2. Load documents:
   - Style-Baseline-(Directive).md
   - Brand-Pack-(Author-Compass).md
   - Your Article Brief
   - Article-Master-Spec.md
   - Critic-Loop-(Single-Pass-Self-Check).md

3. Draft complete article
   - Declare one hard shape
   - Write to completeness (content-driven length)
   - Insert APA citations as you write
   - Add devices with activation headers (if activated)

4. Apply Critic Loop (silent)
   - Voice Check
   - Focus Check
   - Evidence Check
   - Revise once

5. Research Pass (if triggered)
   - Find current sources
   - Update citations
   - Add companion-site callouts
   - Re-run Critic Loop

6. Final QA
   - Verify Gates A–C passed

7. Compile References
   - Consolidated APA list
   - Alphabetized
   - DOIs/URLs included
```

### Activating a Device

```
1. In your Article Brief, add to "Device Activations" section:

   ### Device: Prompt Plate
   - **Purpose:** Demonstrate how adding role context reduces ambiguous outputs
   - **Placement:** After introducing the concept of role specification

2. In your article draft, add activation header before device:

   Device: Prompt Plate — Purpose: Demonstrate how adding role context reduces ambiguous outputs

   [Then insert the actual Prompt Plate table/content]

3. Critic Loop will verify:
   - Device is in Article Brief
   - Activation header is present
   - Device format follows Device-Catalog.md
```

### Handling Freshness

```
1. In Article Brief, set topic-specific horizons:

   **Time-Sensitive Topics:**
   - AI capability benchmarks: Use sources from past 6 months
   - Market adoption rates: Use sources from past 12 months

   **Stable Topics:**
   - Foundational prompt engineering concepts: Authoritative sources from any period

2. During drafting:
   - Cite current sources for time-sensitive claims
   - If no current source exists, insert: [Writer to research latest <topic>]

3. During Evidence Check:
   - Verify all time-sensitive claims have current citations
   - Trigger Research Pass if needed

4. During Research Pass:
   - Find current sources
   - Update citations
   - Add: "For the latest information on <topic>, visit https://theproductiveprompter.com."
```

---

## Files to Read First

1. **0-README.md** ← Overview (start here)
2. **Article-Master-Spec.md** ← Complete requirements
3. **Article-Process-Map.md** ← Workflow guide
4. **Article-Brief-Template.md** ← Planning template
5. **CHANGELOG.md** ← Migration details (if curious)

---

## Archive Reference

### 9-Archive/_Originals/
Contains unmodified copies of all source documents:
- All 9 planning docs from original folder
- Meta-Prompt Instruction.md

**Purpose:** Historical reference; do not use for new work.

### 9-Archive/_Superseded/
Contains notes on retired documents:
- Sub-chapter-Brief-Template-SUPERSEDED.md
- Meta-Prompt-Instruction-SUPERSEDED.md

**Purpose:** Explains why documents were retired and what replaced them.

---

## Testing & Validation

All acceptance criteria from meta-prompt verified:

- ✅ Article-Spec-Pack-v1/ folder exists with exact structure
- ✅ Chapter-specific documents archived
- ✅ Device activation via Article Brief only
- ✅ Dynamic length policy (no numeric bands)
- ✅ Dynamic freshness (no fixed 12-month)
- ✅ Quality Gates A–C referenced
- ✅ Complete CHANGELOG.md

**Status: Production-ready for article production.**

---

## Next Steps

1. **Try creating an Article Brief** using the template
2. **Review the Master Spec** to understand all requirements
3. **Reference the Process Map** when drafting
4. **Keep the precedence chain** visible (Style Baseline → Brand Pack → Article Brief → ...)
5. **Use the Device Catalog** if activating devices
6. **Follow the Evidence Annex** for citations and freshness

---

## Questions?

- **Precedence conflicts?** → Style-Baseline-(Directive).md wins
- **Device rules unclear?** → Device-Catalog.md has full definitions
- **Citation questions?** → Evidence-and-IP-Annex.md has APA 7 guidance
- **Workflow confusion?** → Article-Process-Map.md shows the sequence
- **General guidance?** → Article-Master-Spec.md is single source of truth

---

**The Article-Spec-Pack-v1 is complete and ready for use.** 🎉

All documents are in place, all originals are archived, and the complete migration is documented in the CHANGELOG.

**Start with:** `0-README.md` → `Article-Master-Spec.md` → `Article-Brief-Template.md`
