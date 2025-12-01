# PDF-Upload Quick-Start Guide (Gemini 2.5 Pro Web GUI)

**Purpose:** Enable one-shot article generation using Article-Spec-Pack-v1 in Gemini 2.5 Pro web interface with PDF uploads only (no folder access, no file system, no real-time web search).

**Target Environment:** Google AI Studio or Gemini web GUI with PDF upload capability

**Constraints:**
- ✅ PDF uploads supported (multiple files)
- ❌ No folder structure access
- ❌ No real-time web search
- ❌ No file system operations (no archival to 6-Completed-Articles/)
- ❌ No manifest.json updates (static files only)

---

## Step 1: Prepare PDFs (One-Time Setup)

### Required PDFs (11 Total)

Convert the following markdown files from **Article-Spec-Pack-v1** to PDF:

#### Master Documents (Folder: 1-Master/)
1. **Article-Master-Spec.md** → `1-Article-Master-Spec.pdf`
2. **Article-Process-Map.md** → `2-Article-Process-Map.pdf`
3. **Critic-Loop-(Single-Pass-Self-Check).md** → `3-Critic-Loop.pdf`

#### Templates (Folder: 2-Templates/)
4. **Article-Brief-Template.md** → `4-Article-Brief-Template.pdf`

#### Annexes (Folder: 3-Annexes/)
5. **Device-Catalog.md** → `5-Device-Catalog.pdf`
6. **Evidence-and-IP-Annex.md** → `6-Evidence-and-IP-Annex.pdf`

#### Carryover/Updated (Folder: 4-Carryover-Updated/)
7. **Brand-Pack-(Author-Compass).md** → `7-Brand-Pack.pdf`
8. **Style-Baseline-(Directive).md** → `8-Style-Baseline.pdf`
9. **Default-Style-Anchor-Card.md** → `9-Default-Style-Anchor-Card.pdf`

#### Execution & Examples (Root folder)
10. **Article-Execution-Meta-Prompt.md** → `10-Article-Execution-Meta-Prompt.pdf`
11. **Sample-Completed-Article-Annotated.md** → `11-Sample-Article-Annotated.pdf`

### PDF Naming Convention
Use numbered prefixes (1–11) to maintain precedence order when uploading. Gemini may process files in upload order, so numbering ensures correct precedence hierarchy.

### PDF Conversion Tools
- **Recommended:** Pandoc (`pandoc filename.md -o filename.pdf`)
- **Alternative:** Online converters (Markdown to PDF)
- **Manual:** Copy markdown to Google Docs, export as PDF

---

## Step 2: Create Your Article Brief

Before uploading to Gemini, create an **Article Brief** following the template in `4-Article-Brief-Template.pdf`.

Save as: `My-Article-Brief.pdf` (convert markdown brief to PDF)

**Example Brief:**
```markdown
# Article Brief: Understanding Retrieval-Augmented Generation (RAG)

## Article Metadata
**Title:** What Is RAG? A Practical Guide to Retrieval-Augmented Generation  
**Intended Audience:** Business leaders exploring AI solutions (minimal technical background)  
**Publication Context:** Standalone web article  
**Estimated Scope:** ~2,000 words

## Objective & Scope
**Objective:** Explain RAG in business terms, enabling leaders to evaluate RAG solutions.

**Scope:**
- Covers what RAG is, how it works (high-level), and business use cases
- Includes comparison to standard LLMs (with/without RAG)
- Excludes technical implementation details

**Constraints:** 1,500–2,500 words; accessible to non-technical readers

## Core Argument
**Central Thesis:** RAG combines LLM capabilities with domain-specific data retrieval to reduce hallucinations and improve accuracy for enterprise applications.

**Supporting Claims:**
- RAG reduces hallucinations by 60–80% in domain-specific tasks
- Retrieval step grounds responses in verifiable sources
- Business use cases: customer support, internal knowledge bases, compliance

## Device Activations
**Device 1: Comparison Grid**
- **Purpose:** Compare standard LLM vs. RAG-enabled LLM outputs
- **Placement:** After explaining RAG mechanism

**Device 2: Case Vignette**
- **Purpose:** Show RAG in customer support scenario
- **Placement:** In use case section

## Freshness Expectations
**Time-Sensitive Topics:**
- RAG capability claims: 2023–2024 sources required
- Business adoption stats: 2023–2024

**Stable Topics:**
- Core RAG mechanism: Foundational sources acceptable

## Success Criteria
- [ ] Reader can explain RAG in one sentence
- [ ] Article includes Comparison Grid and Case Vignette
- [ ] All claims have citations (or flagged as training-data-only)
- [ ] Ends with verification + next action
```

Convert this brief to PDF → `My-Article-Brief.pdf`

---

## Step 3: Upload PDFs to Gemini

### Upload Order (Recommended)
Upload in numbered order to establish precedence:

1. `1-Article-Master-Spec.pdf`
2. `2-Article-Process-Map.pdf`
3. `3-Critic-Loop.pdf`
4. `4-Article-Brief-Template.pdf`
5. `5-Device-Catalog.pdf`
6. `6-Evidence-and-IP-Annex.pdf`
7. `7-Brand-Pack.pdf`
8. `8-Style-Baseline.pdf`
9. `9-Default-Style-Anchor-Card.pdf`
10. `10-Article-Execution-Meta-Prompt.pdf`
11. `11-Sample-Article-Annotated.pdf`
12. **`My-Article-Brief.pdf`** (your specific article brief)

**Gemini Web GUI:** Click "Attach files" → Select all 12 PDFs → Upload

---

## Step 4: Use This Meta-Prompt

Copy-paste this prompt into Gemini **after uploading all 12 PDFs**:

```
You have been provided with 12 PDF files containing a complete specification pack for autonomous article generation (Article-Spec-Pack-v1). These files define normative requirements, workflow phases, quality gates, and precedence hierarchy for producing publication-ready articles.

PRECEDENCE HIERARCHY (binding order for public articles):
1. Article-Spec-Consolidated.pdf — Developer-facing, workflow-first behavior (no scaffolding leakage)
2. Style-Baseline-(Directive).pdf — Voice and tone calibration (internal only)
3. Brand-Pack-(Author-Compass).pdf — Authorial values, anti-patterns
4. My-Article-Brief.pdf — Article-specific instructions
5. Critic-Loop.pdf — Silent self-checks (Voice/Focus/Evidence/Redundancy)
6. Evidence-and-IP-Annex.pdf — Citation and freshness guidance (APA only if required)
7. Device-Catalog.pdf — Planning aids; render naturally (no activation headers)

TASK:
Execute the 7-phase workflow defined in "Article-Execution-Meta-Prompt.pdf" to generate a complete article based on "My-Article-Brief.pdf".

PHASE 0: INTEGRITY CHECK (Adapted for PDF Environment)
- You cannot verify MD5 checksums in this environment
- You cannot access manifest.json
- SKIP checksum verification
- Proceed to Phase 1 after confirming all 12 PDFs uploaded successfully

PHASE 1: TOPIC INTAKE & BRIEF ACTIVATION
- Read "My-Article-Brief.pdf"
- Extract: title, audience, scope, constraints, thesis, devices, freshness expectations
- Confirm brief is complete (all required sections present)
- Echo brief summary for user verification

PHASE 2: PACK ADAPTATION
- Apply dynamic length policy from Article-Master-Spec.pdf
- Apply freshness horizons from Evidence-and-IP-Annex.pdf (Section 4: Dynamic Freshness Policy)
- Identify activated devices from brief and reference Device-Catalog.pdf for formatting
- Note: You do NOT have real-time web search. Follow Section 7 of Evidence-and-IP-Annex.pdf: "Citation Guidance for Models Without Real-Time Web Search"

PHASE 3: APPROVAL LOOP (User Checkpoint)
- Present adapted plan to user:
  * Confirmed scope & length
  * Invisible outline (hook → models/definitions → 2–4 workflows → pitfalls → next steps)
  * Planned narrative behaviors (scenario, Q&A subheading, table, checklist, prompt before/after)
  * Freshness strategy (no real-time search; use training data + flag gaps)
  * Voice notes (developer voice; any internal calibration)
- Wait for user approval before proceeding

PHASE 4: DRAFT GENERATION
- Generate article following the consolidated spec:
  * Second-person developer voice
  * Follow invisible outline; do not name shapes publicly
  * Render planned behaviors naturally; no activation headers or internal labels
  * Use linkable citations by default (APA only if brief requires); do not print research placeholders
  * Final-line rule: verification + next action (NOT maxim)

PHASE 5: GATE VALIDATION (Silent)
- GATE A: Developer voice; invisible structure; no scaffolding leakage in article text
- GATE B: Silent self-check (Voice, Focus, Evidence, Final-line, Natural behaviors, Anti-redundancy)
- GATE C: Citations (links or APA if required), freshness policy, references/links section
- If any gate fails, revise and re-validate before proceeding

PHASE 6: ARCHIVAL & LOGGING (Adapted for PDF Environment)
- You cannot save files to 6-Completed-Articles/ (no file system access)
- Instead: Present final output using "Article-Output-Format-Template.pdf" structure
- Include all metadata, article text, gate validation summary, metrics
- Provide archival instructions for user to execute manually

OUTPUT FORMAT:
Use the structure defined in "Article-Output-Format-Template.pdf" (uploaded as one of the 12 PDFs). Include:
1. Article Metadata (title, word count, gates passed, etc.)
2. Complete Article Text (clean, deliverable version)
3. Gate Validation Summary (Gates A, B, C status with notes)
4. Article Metrics (word count, citations, devices, etc.)
5. Copy-Paste Ready Version (optional, for immediate use)
6. Archival Information (manual instructions for user)

EXECUTION CONTEXT:
- Environment: Gemini 2.5 Pro web GUI (PDF uploads only)
- No file system access (cannot save to folders)
- No real-time web search (use training data + flag gaps)
- No manifest updates (static execution)
- User will manually archive outputs after delivery

CONSTRAINTS:
- Follow all normative requirements in Article-Master-Spec.pdf
- Apply precedence hierarchy (Article Brief = highest authority)
- Pass all three quality gates before final delivery
- Use Default Style Anchor Card (uploaded) unless brief specifies alternative
- Apply dynamic freshness policy (Evidence-and-IP-Annex.pdf Section 4)
- Flag research gaps with [RESEARCH GAP] brackets when training data insufficient

CONFIRMATION REQUIRED:
Before starting Phase 1, confirm:
1. All 12 PDFs successfully uploaded and readable? [YES/NO]
2. My-Article-Brief.pdf contains complete brief? [YES/NO]
3. Ready to proceed with Phase 1 (Topic Intake)? [YES/NO]

Proceed when ready.
```

---

## Step 5: Monitor Execution

### Expected Workflow

**Phase 1: Topic Intake**
- Gemini will read your brief and echo a summary
- Verify the summary matches your intent
- Respond "Approved" or provide corrections

**Phase 2: Pack Adaptation**
- Gemini will present adapted plan:
  * Scope, length, shape, devices, freshness strategy
- Review the plan
- Respond "Approved" or request changes

**Phase 3: Approval Loop**
- Final checkpoint before drafting
- Gemini presents complete execution plan
- Respond "Approved" to proceed to drafting

**Phase 4: Draft Generation**
- Gemini generates article following specs
- May take 1–3 minutes depending on length
- Watch for progress indicators

**Phase 5: Gate Validation**
- Gemini runs internal quality checks
- Gates A, B, C validated
- If any gate fails, Gemini will revise automatically

**Phase 6: Final Output**
- Gemini delivers article using output format template
- Includes metadata, article text, gate summary, metrics
- Copy article text for immediate use

---

## Step 6: Manual Archival (Post-Execution)

Since Gemini cannot access your file system, manually save outputs:

### Save Article
1. Copy article text from Gemini output (Section 2 or Section 5)
2. Paste into new markdown file: `Article-YYYYMMDD-[Topic]-v1.0.md`
3. Save to: `Article-Spec-Pack-v1/6-Completed-Articles/`

### Archive Brief
1. Move your brief PDF or markdown version to: `Article-Spec-Pack-v1/9-Archive/_Completed-Briefs/`
2. Rename if needed: `Article-Brief-YYYYMMDD-[Topic].md`

### Update CHANGELOG.md
1. Open: `Article-Spec-Pack-v1/CHANGELOG.md`
2. Add entry: `YYYY-MM-DD: Completed Article: [Title] (v1.0)`

### Update Manifest (If Spec Docs Changed)
- If you modified any spec PDFs during execution, regenerate checksums
- Otherwise, no manifest updates needed

---

## Troubleshooting

### Issue: Gemini Says "Cannot Read PDF"
- **Cause:** PDF may be corrupted or password-protected
- **Fix:** Re-export markdown to PDF using Pandoc or Google Docs

### Issue: Gemini Skips Quality Gates
- **Cause:** Meta-prompt may not emphasize gate validation
- **Fix:** Add to prompt: "CRITICAL: Do not proceed to Phase 6 until all gates (A, B, C) pass."

### Issue: Gemini Includes First-Person Voice ("I think...")
- **Cause:** Style Baseline not applied
- **Fix:** Remind Gemini: "Use third-person voice throughout. No 'I/we/you'."

### Issue: No Citations or All Citations Are [RESEARCH GAP]
- **Cause:** Gemini may not be leveraging training data effectively
- **Fix:** Add to prompt: "Use training data for foundational claims. Only flag [RESEARCH GAP] for time-sensitive statistics or recent events."

### Issue: Article Exceeds Target Length
- **Cause:** Dynamic length policy may be interpreted as "no limit"
- **Fix:** In your brief, specify hard max: "Constraints: 2,000 words MAXIMUM (hard cap)"

### Issue: Scaffolding Leakage (Device/Gate/Shape labels)
- **Cause:** Internal planning terms included in public text
- **Fix:** Remind in prompt: "Render planned behaviors naturally; do not print any internal labels (Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass)."

---

## Best Practices

### 1. Brief Quality Determines Output Quality
- Spend time crafting a detailed brief
- Specify devices explicitly (name, purpose, placement)
- Set clear constraints (word count, audience, scope)
- Define success criteria (what reader should be able to do)

### 2. Use Developer Voice; Style Anchor Optional
- Default developer voice works for most use cases
- Use a Style Anchor only for internal calibration; never mention it in public text

### 3. Expect Research Gaps for Time-Sensitive Topics
- Gemini's training data has a cutoff date
- Recent statistics, events, product releases will be flagged
- Plan to manually research and fill gaps post-generation

### 4. Review Gate Validation Summary Carefully
- Don't assume gates passed without checking
- Look for specific evidence (e.g., "6 citations verified")
- If gate notes are vague, ask Gemini to elaborate

### 5. Iterate on Brief, Not Article
- If output doesn't match expectations, revise your brief
- Add more constraints, clarify scope, specify devices
- Re-run execution with updated brief rather than editing article manually

---

## Advanced: Custom Style Anchor Card

If Default Style Anchor doesn't match your voice, create a custom anchor:

### Create Custom Style Anchor Card (Markdown)

```markdown
# Custom Style Anchor Card: [Your Voice Name]

**Anchor Text (100–150 words):**
[Paste 100–150 words of your authentic writing that represents your voice]

**Cadence Patterns:**
- [Describe sentence rhythm, e.g., "Short declarative sentences; occasional longer elaborations"]
- [Describe paragraph structure, e.g., "Claim + 2-3 evidence lines"]

**Lexicon Patterns:**
- [List characteristic words/phrases you use frequently]
- [Note words you AVOID]

**Voice Examples:**
1. [Example sentence showing your voice]
2. [Example sentence showing your voice]
3. [Example sentence showing your voice]

**Integration with Critic Loop:**
This Style Anchor binds the Voice Check (Critic Loop, Section 4.1). During Gate B, verify:
- Cadence patterns match anchor
- Lexicon patterns consistent
- Voice examples reflected in article tone
```

### Convert to PDF
- Save as: `Custom-Style-Anchor-[YourName].pdf`
- Upload as 13th PDF alongside the original 12
- Update meta-prompt: Replace "Default Style Anchor Card" with "Custom Style Anchor [YourName]"

---

## Example Execution (Start to Finish)

### Scenario: Generate article on "Prompt Engineering Best Practices"

**Step 1:** Create brief → `My-Article-Brief-Prompt-Engineering.pdf`

**Step 2:** Upload 12 spec PDFs + brief (13 total files)

**Step 3:** Paste meta-prompt into Gemini

**Step 4:** Gemini executes:
- Phase 1: Echoes brief summary → User approves
- Phase 2: Presents adapted plan → User approves
- Phase 3: Final checkpoint → User approves
- Phase 4: Generates 2,300-word article
- Phase 5: Validates Gates A, B, C → All pass
- Phase 6: Delivers formatted output

**Step 5:** User copies article text, saves to `6-Completed-Articles/Article-20250120-Prompt-Engineering-v1.0.md`

**Step 6:** User moves brief to `9-Archive/_Completed-Briefs/`

**Step 7:** User updates `CHANGELOG.md` with completion entry

**Total Time:** ~10 minutes (5 min drafting, 5 min review/archival)

---

## Quick Reference: Minimal Meta-Prompt (For Simple Articles)

If you're confident in your brief and want faster execution, use this condensed prompt:

```
Execute Article-Execution-Meta-Prompt.pdf workflow using My-Article-Brief.pdf. Apply all specs from the 12 uploaded PDFs. Pass Gates A, B, C before delivery. Output using Article-Output-Format-Template.pdf structure. Confirm ready to start.
```

**Use when:**
- Brief is very clear and detailed
- You trust automated execution
- No need for approval loops

**Avoid when:**
- First-time using the system
- Complex or ambiguous brief
- Want to review plan before drafting

---

## Summary Checklist

- [x] Convert 11 spec markdown files to PDFs (numbered 1–11)
- [ ] Create article brief following template
- [ ] Convert brief to PDF
- [ ] Upload all 12 PDFs to Gemini web GUI
- [ ] Paste meta-prompt into Gemini
- [ ] Approve Phase 1 (Topic Intake) after summary echo
- [ ] Approve Phase 2 (Pack Adaptation) after plan review
- [ ] Approve Phase 3 (Final checkpoint) before drafting
- [ ] Review Phase 5 (Gate Validation) results
- [ ] Copy Phase 6 output (article text)
- [ ] Manually save article to 6-Completed-Articles/
- [ ] Archive brief to 9-Archive/_Completed-Briefs/
- [ ] Update CHANGELOG.md with completion entry

---

**This guide enables one-shot article generation in Gemini 2.5 Pro web GUI using PDF uploads only.**
