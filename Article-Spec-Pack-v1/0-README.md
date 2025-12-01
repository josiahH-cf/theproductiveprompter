# Article Specification Pack v1

**Purpose**  
This pack contains the complete documentation set for producing publication-ready articles for _The Productive Prompter_. It replaces the previous chapter-oriented documentation with a streamlined, article-focused workflow.

---

## Quick Start

### "Write the next article" (No inputs)

1. Drop your general content into `0-Article-Content/` (e.g., `20251113-topic.md`).
2. Say: "write the next article".
3. The system reads the newest intake file, auto-generates a brief, drafts the blog with invisible structure and link-based citations, applies silent QA, and packages to `6-Completed-Articles/`.

### For Manual Article Production

1. Read **[Article-Master-Spec.md](1-Master/Article-Master-Spec.md)** for complete normative requirements
2. Review **[Article-Process-Map.md](1-Master/Article-Process-Map.md)** for workflow overview
3. Create an **Article Brief** using **[Article-Brief-Template.md](2-Templates/Article-Brief-Template.md)**
4. Draft article following the Master Spec
5. Apply **[Critic-Loop-(Single-Pass-Self-Check).md](1-Master/Critic-Loop-(Single-Pass-Self-Check).md)** silently
6. Compile references per **[Evidence-and-IP-Annex.md](3-Annexes/Evidence-and-IP-Annex.md)**

### For Autonomous Execution (Recommended)

1. Read **[Article-Execution-Meta-Prompt.md](Article-Execution-Meta-Prompt.md)** for autonomous workflow
2. Load the entire `Article-Spec-Pack-v1/` folder into your AI model
3. Provide a topic or idea
4. Use approval commands: `APPROVE`, `REVISE:<instruction>`, or `PROCEED`
5. Model executes Phases 0–6 with anti-degradation controls
6. Completed article appears in `6-Completed-Articles/[article-name]/`

### Blog-Ready Output (End-State) — Intake Mode

When your goal is a finalized expert blog from general content (notes, bullets, or a PDF):

1. Provide a topic and paste your general content.
2. Auto-generate an Article Brief from the intake using `7-Intake-Mode/Intake-Brief-Autofill-Template.md`.
3. Draft the blog using `Blog-Output-Format-Template.md` with invisible structure and natural rendering of planning behaviors.
4. Apply the Critic Loop silently; validate Gates A–C internally.
5. Create `6-Completed-Articles/Article-[N]-[slug]/index.md` with YAML front matter (title, date, slug, tags, description).
6. Include link-based citations and a references section (APA only if required).
7. Keep public text clean: no internal labels (Device/Gate/Hard Shape/Style Anchor).

**Autonomous mode includes:**
- Integrity checking (manifest.json verification)
- Automatic brief generation
- Pack adaptation proposals (with diffs)
- Gate validation and correction
- Checksum tracking and rollback protection

---

## Folder Structure

```
Article-Spec-Pack-v1/
├── 0-README.md                          ← You are here
├── 0-Article-Content/                   ← Drop intake files; used by "write the next article"
├── CHANGELOG.md                         ← Complete migration history
├── manifest.json                        ← Integrity checksums for anti-degradation
├── Article-Execution-Meta-Prompt.md     ← Autonomous execution controller
├── Blog-Output-Format-Template.md       ← Blog-ready delivery format (front matter + clean text)
├── copilot-instructions.md              ← How to “write the next blog post” automatically
├── 1-Master/                            ← Core operational documents
│   ├── Article-Master-Spec.md           ← Single source of truth (normative)
│   ├── Article-Process-Map.md           ← Workflow sequence
│   └── Critic-Loop-(Single-Pass-Self-Check).md  ← Quality enforcement
├── 2-Templates/                         ← Fill-in templates
│   └── Article-Brief-Template.md        ← Per-article planning document
├── 3-Annexes/                           ← Supporting specifications
│   ├── Device-Catalog.md                ← Narrative devices & formatting
│   └── Evidence-and-IP-Annex.md         ← Citations, freshness, IP rules
├── 4-Carryover-Updated/                 ← Updated foundation documents
│   ├── Brand-Pack-(Author-Compass).md   ← Brand voice & policy
│   └── Style-Baseline-(Directive).md    ← Voice, tone, structure (highest precedence)
├── 5-Active-Briefs/                     ← Article Briefs in development
│   └── README.md                        ← Brief workflow & status tracking
├── 6-Completed-Articles/                ← Finalized articles with metadata
│   └── README.md                        ← Completion workflow & structure
├── 7-Intake-Mode/                       ← Intake-driven blog generation
│   ├── README.md                        ← Overview (general content → blog)
│   ├── Intake-Workflow.md               ← Step-by-step intake instructions
│   ├── Intake-Prompt.md                 ← One-shot meta-prompt for intake mode
│   └── Intake-Brief-Autofill-Template.md← Mapping intake → Article Brief
└── 9-Archive/                           ← Historical documents
    ├── _Originals/                      ← Unmodified source documents
    └── _Superseded/                     ← Retired chapter-specific docs
```

---

## Autonomous Execution Mode

### Article-Execution-Meta-Prompt.md

The pack includes an **autonomous execution controller** that orchestrates the entire article production workflow with anti-degradation safeguards.

**Features:**
- **7 Execution Phases:** Integrity Check → Topic Intake → Pack Adaptation → Approval Loop → Draft Generation → Gate Validation → Archival & Logging
- **Integrity Checking:** Verifies `manifest.json` checksums before every phase
- **Human-in-the-Loop:** Approval gates (APPROVE, REVISE, PROCEED commands)
- **Anti-Degradation Controls:** Checksum registry, diff enforcement, rollback on failure, lock/unlock mechanism, echo validation
- **Complete Traceability:** All changes logged in CHANGELOG.md with Run IDs

**When to use:**
- You want fully automated article production with quality controls
- You need verifiable integrity across multiple article generations
- You want to ensure zero semantic drift or rule degradation
- You need audit trails for all modifications

**How to use:**
1. Load entire `Article-Spec-Pack-v1/` folder into AI model
2. Provide topic: "Write an article about [topic]"
3. Model executes Phase 0 (Integrity Check) automatically
4. Respond to approval gates with: APPROVE, REVISE:<instruction>, or PROCEED
5. Model delivers completed article in `6-Completed-Articles/`
6. Immediately run `python scripts/package_article.py --article-folder <folder> --source-file <intake-file>` so the packaging helper normalizes artifacts and moves the source file out of `0-Article-Content/`

See **[Article-Execution-Meta-Prompt.md](Article-Execution-Meta-Prompt.md)** for complete details.

---

When conflicts arise, resolve in this order:

1. **[Article-Spec-Consolidated.md](1-Master/Article-Spec-Consolidated.md)** — Governs public behavior (developer voice; invisible structure; anti-leak)
2. **[Style-Baseline-(Directive).md](4-Carryover-Updated/Style-Baseline-(Directive).md)** — Voice, tone, prohibited practices (internal calibration only; never mention Style Anchor publicly)
3. **[Brand-Pack-(Author-Compass).md](4-Carryover-Updated/Brand-Pack-(Author-Compass).md)** — Brand voice & neutrality
4. **Article Brief** — Per-article specifications (planning aids, freshness)
5. **[Critic-Loop-(Single-Pass-Self-Check).md](1-Master/Critic-Loop-(Single-Pass-Self-Check).md)** — Quality checks (silent)
6. **[Evidence-and-IP-Annex.md](3-Annexes/Evidence-and-IP-Annex.md)** — Citations & freshness
7. **[Device-Catalog.md](3-Annexes/Device-Catalog.md)** — Planning aids; internal-only

**First document in list wins tiebreaker.**

---

## Key Principles

### Single-Pass Articles
- Write complete article in one continuous draft
- No multi-section stop-points or chapter architecture
- Apply Critic Loop after full draft, not per-section

### Dynamic Length Policy
- Article length driven by **content strength**, not fixed word counts
- Generally similar scale to prior guidance (~2,000–5,000 words typical)
- Write to completeness, not to a counter

### Planning Behaviors (Internal-Only)
- All narrative devices are planning aids, OFF by default.
- The **Article Brief** may request behaviors (scenario, Q&A, table, before/after), but they must render naturally in public text with no labels.

### Dynamic Freshness
- **No fixed 12-month default**
- Freshness horizons set by:
  - Topic type (rapidly evolving vs. stable)
  - Article Brief specifications
  - Best available information at drafting time

### Quality Gates (Silent)
- **Gate A:** Baseline & Structure (developer voice; invisible structure; anti-leak)
- **Gate B:** Critic Loop (Voice, Focus, Evidence)
- **Gate C:** Evidence & Freshness (links by default; APA if required)

---

## Migration from Chapter-Oriented Pack

This pack replaces the **"9 Planning Docs - Chapter by Chapter Experiment"** folder with article-focused documentation.

**What changed:**
- ✅ Removed chapter/sub-chapter architecture and movement mechanics
- ✅ Removed multi-section stop-and-confirm behaviors
- ✅ Removed fixed numeric length bands (e.g., 700–1,200 words per movement)
- ✅ Replaced fixed 12-month freshness default with dynamic horizons
- ✅ Consolidated device guidance into single Device Catalog
- ✅ Merged fact-checking and citation protocols into Evidence & IP Annex
- ✅ Updated precedence chain to reference Article Brief instead of Chapter/Sub-chapter Briefs

**What stayed the same:**
- ✅ Third-person voice requirement (Style Baseline)
- ✅ Hard shape declaration and final-line rule
- ✅ APA 7 citation standards
- ✅ Single silent Critic Loop (Voice, Focus, Evidence)
- ✅ Device gating (OFF by default, activation required)
- ✅ Anti-redundancy and purposeful sentence requirements

**See [CHANGELOG.md](CHANGELOG.md) for complete migration details.**

---

## Usage Workflow

### 1. Plan
- Fill out **[Article-Brief-Template.md](2-Templates/Article-Brief-Template.md)**
- Define objective, scope, success criteria
- Activate devices (if needed)
- Set freshness expectations

### 2. Draft
- Load control documents in precedence order
- Write complete article following **[Article-Master-Spec.md](1-Master/Article-Master-Spec.md)**
- Declare one hard shape and follow end-to-end
- Insert APA citations as you write
- Add activated devices with headers

### 3. Critic Loop
- Apply **[Critic-Loop-(Single-Pass-Self-Check).md](1-Master/Critic-Loop-(Single-Pass-Self-Check).md)** silently
- **Voice Check:** Third-person, Style Anchor binding, tone/cadence
- **Focus Check:** Intent, objectives, hard shape, final line, devices, anti-redundancy
- **Evidence Check:** APA citations, freshness, opinion labeling, research gaps
- Revise once internally
- Return only final text

### 4. Research Pass (if triggered)
- Execute if Evidence Check identifies freshness gaps or Article Brief requires
- Find current sources per **[Evidence-and-IP-Annex.md](3-Annexes/Evidence-and-IP-Annex.md)**
- Update citations, add companion-site callouts
- **No-new-claims rule:** update evidence only, don't introduce new arguments
- Re-run Critic Loop after updates

### 5. Final QA
- Verify Gates A–C passed
- Confirm all compliance checklist items

### 6. References
- Compile consolidated APA references list
- Alphabetize, format per APA 7
- Include DOIs/URLs, accessed dates

### 7. Blog Packaging (Optional but Recommended)
- Use `Blog-Output-Format-Template.md`
- Create `6-Completed-Articles/Article-[N]-[slug]/index.md`
- Add YAML front matter (title/date/slug/tags/description)
- Confirm tone: third-person, neutral, precise, no metaphors/hype (Brand Pack)
- Publish-ready headings, reflowable tables, devices with headers

---

## For Future Models Executing This Pack

### Loading Order
```
1. Style Baseline (Directive)
2. Brand Pack (Author Compass)
3. Article Brief (from user)
4. Article Master Spec
5. Critic Loop
```

### Operational Flow
```
Plan → Draft → Critic Loop → [Research Pass if triggered] → Final QA → References
```

### Quality Enforcement
- Silently apply all checks
- Never output reasoning or compliance notes
- Only deliver final revised text

### Device Integration
- Check Article Brief for activations
- Insert activation header before each device
- Remove any device not activated in Brief

### Freshness Handling
- Use Article Brief horizons (not fixed 12-month)
- Trigger Research Pass for stale/missing sources
- Add companion-site callouts for evolving data

---

## Document Status

**Version:** 1.0  
**Date:** November 3, 2025  
**Status:** Production-ready

All documents in `1-Master/`, `2-Templates/`, `3-Annexes/`, and `4-Carryover-Updated/` are **normative** and binding for article production.

Archive documents (`9-Archive/`) are historical reference only and should not be used for new article production.

---

## Questions or Issues?

- **Precedence conflicts:** Follow the hierarchy above (Style Baseline wins)
- **Missing guidance:** Check Article Master Spec first, then relevant annexes
- **Unclear device rules:** Consult Device Catalog; if device not listed, it's not approved
- **Citation questions:** See Evidence & IP Annex for APA 7 and freshness protocols

---

## Version History

- **v1.0 (November 3, 2025):** Initial article-oriented pack migrated from chapter-oriented documentation
