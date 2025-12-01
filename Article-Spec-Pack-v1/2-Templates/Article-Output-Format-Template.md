# Article Output Format Template

**Purpose:** Standardized delivery format for Phase 6 (Archival & Logging) of the Article-Execution-Meta-Prompt workflow. Public-facing article text must not expose internal scaffolding (devices, gates, shapes, style anchors).

**Usage:** After completing all quality gates (A, B, C), format final output using this template for archival and user delivery.

---

## Section 1: Article Metadata

```markdown
## ARTICLE METADATA

**Title:** [Insert article title]
**Brief Used:** [Filename of Article Brief from 5-Active-Briefs/]
**Generation Date:** [YYYY-MM-DD]
**Word Count:** [Actual word count]
**Target Scope:** [From Article Brief: min-max words or "dynamic"]
**Internal Shape (do not print in article):** [e.g., "Claim→Evidence×3"]
**Internal Voice Calibration (do not print):** [e.g., "Default Style Anchor Card" or custom note]
**Internal Devices Used (do not print):** [e.g., "Prompt Plate ×4, Case Vignette ×2"]
**Gate Status (internal only):** [Gate A: ✅, Gate B: ✅, Gate C: ✅]
**Revision Number:** [v1.0, v1.1, etc.]
```

**Example:**
```markdown
## ARTICLE METADATA

**Title:** Five Principles for Writing Effective AI Prompts
**Brief Used:** Article-Brief-20250120-Five-Principles.md
**Generation Date:** 2025-01-20
**Word Count:** 2,100
**Target Scope:** 2,000–3,000 words
**Hard Shape:** Claim→Evidence×4
**Style Anchor:** Default Style Anchor Card
**Devices Activated:** Prompt Plate ×5
**Quality Gates:** Gate A: ✅, Gate B: ✅, Gate C: ✅
**Revision Number:** v1.0
```

---

## Section 2: Article Text (Full)

```markdown
## ARTICLE TEXT

[Insert complete article here. Requirements:]
- Clean, public-facing text only (no internal labels like Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass)
- Title (H1) and clear section headings
- Tables/lists reflowable (Markdown); code blocks as needed
- Citations: linkable sources by default; use APA only if required by the brief
- Optional references/links section at end

[Example:]

# Five Principles for Writing Effective AI Prompts

Effective prompts follow five structural principles that reduce ambiguity and align AI outputs with user intent...

[Continue with full article text...]

## References

Chen, L., Park, S., & Zhang, M. (2024)...
```

---

## Section 3: Gate Validation Summary (Internal Only — exclude from public article)

```markdown
## GATE VALIDATION SUMMARY

### Gate A: Baseline & Shape Declared
- [ ] Style Anchor declared and named
- [ ] Hard shape declared
- [ ] Third-person voice verified

**Gate A Status:** [✅ PASS / ❌ FAIL]
**Notes:** [Any relevant notes about baseline decisions]

---

### Gate B: Critic Loop (Single-Pass Self-Check)
- [ ] Voice Check: Style Anchor patterns followed
- [ ] Focus Check: Argument integrity maintained, no filler
- [ ] Evidence Check: All claims cited or common knowledge
- [ ] Final-line rule: Verification + next action (not maxim)
- [ ] Device gating: All activated devices have headers
- [ ] Anti-redundancy: No duplicate sentences

**Gate B Status:** [✅ PASS / ❌ FAIL]
**Voice Check Notes:** [Specific patterns verified]
**Focus Check Notes:** [Areas confirmed]
**Evidence Check Notes:** [Citation count, any gaps]
**Final-line Notes:** [Verification method + next action described]
**Device Notes:** [Number activated, headers confirmed]
**Anti-redundancy Notes:** [Verification method]

---

### Gate C: Evidence & Freshness
- [ ] APA compliance verified
- [ ] Freshness policy applied (topic-specific horizons)
- [ ] No research gaps flagged
- [ ] Consolidated references section complete

**Gate C Status:** [✅ PASS / ❌ FAIL]
**APA Notes:** [Number of sources, DOI status]
**Freshness Notes:** [Topic type, acceptable horizon, source years]
**Research Gap Notes:** [Any flagged gaps or acceptable limitations]
**References Notes:** [Reference count, formatting verification]
```

**Example:**
```markdown
## GATE VALIDATION SUMMARY

### Gate A: Baseline & Shape Declared
- [x] Style Anchor declared and named
- [x] Hard shape declared
- [x] Third-person voice verified

**Gate A Status:** ✅ PASS
**Notes:** Default Style Anchor Card applied; Claim→Evidence×4 shape; third-person voice maintained throughout.

---

### Gate B: Critic Loop (Single-Pass Self-Check)
- [x] Voice Check: Style Anchor patterns followed
- [x] Focus Check: Argument integrity maintained, no filler
- [x] Evidence Check: All claims cited or common knowledge
- [x] Final-line rule: Verification + next action (not maxim)
- [x] Device gating: All activated devices have headers
- [x] Anti-redundancy: No duplicate sentences

**Gate B Status:** ✅ PASS
**Voice Check Notes:** Concrete claims, accumulation patterns, purposeful sentences verified.
**Focus Check Notes:** All five principles supported with evidence; no filler paragraphs.
**Evidence Check Notes:** 6 APA citations; all specific claims cited.
**Final-line Notes:** Ends with verification (measure results) + next action (apply template).
**Device Notes:** 5 Prompt Plates activated, all with proper headers.
**Anti-redundancy Notes:** Checked via text diff; no duplicate sentences found.

---

### Gate C: Evidence & Freshness
- [x] APA compliance verified
- [x] Freshness policy applied (topic-specific horizons)
- [x] No research gaps flagged
- [x] Consolidated references section complete

**Gate C Status:** ✅ PASS
**APA Notes:** 6 sources, all with DOIs, alphabetized, APA 7 format.
**Freshness Notes:** AI capabilities (2023–2024 required); all sources within range.
**Research Gap Notes:** No gaps; all claims supported or common knowledge.
**References Notes:** 6 references, consolidated at end, formatted correctly.
```

---

## Section 4: Article Metrics (Internal)

```markdown
## ARTICLE METRICS

**Word Count:** [Total words]
**Paragraph Count:** [Total paragraphs]
**Average Paragraph Length:** [~X words]
**Sentence Length Distribution:** [Brief description, e.g., "varied, 15–35 words"]
**Internal Shape:** [Name]
**Shape Adherence:** [✅ Maintained / ⚠️ Partial / ❌ Violated]
**Internal Devices:** [Count and types]
**Citations:** [Count, e.g., "8 sources"]
**Citation Density:** [Citations per 1,000 words]
**Third-Person Voice:** [✅ Maintained / ❌ Violated]
**Final-Line Rule:** [✅ Compliant / ❌ Non-compliant]
```

**Example:**
```markdown
## ARTICLE METRICS

**Word Count:** 2,100
**Paragraph Count:** 22
**Average Paragraph Length:** ~95 words
**Sentence Length Distribution:** Varied, 18–32 words average
**Hard Shape:** Claim→Evidence×4
**Shape Adherence:** ✅ Maintained throughout
**Devices Activated:** 5 (Prompt Plate ×5)
**Citations:** 6 sources
**Citation Density:** 2.9 citations per 1,000 words
**Third-Person Voice:** ✅ Maintained
**Final-Line Rule:** ✅ Compliant
```

---

## Section 5: Copy-Paste Ready Version (Optional)

```markdown
## COPY-PASTE READY VERSION

[This section provides the article text in a format optimized for immediate use in CMS, word processors, or publishing platforms. Includes:]

- Clean markdown formatting (no annotations)
- Proper heading hierarchy (H1 for title, H2 for sections)
- Tables formatted for reflow (Kindle/EPUB3 compatible)
- References section formatted per APA 7
- No metadata headers (article text only)

[Insert clean article text here]
```

---

## Section 6: Archival Information (Internal)

```markdown
## ARCHIVAL INFORMATION

**Archive Location:** [Folder path, e.g., "6-Completed-Articles/"]
**Archive Filename:** [Filename, e.g., "Article-20250120-Five-Principles-v1.0.md"]
**Brief Archived To:** [Location, e.g., "9-Archive/_Completed-Briefs/"]
**Brief Filename:** [Filename, e.g., "Article-Brief-20250120-Five-Principles.md"]
**Execution Log:** [If maintained, reference log entry or ID]
**Related Files:** [Any supporting files, images, data files]

**Next Actions:**
1. [e.g., "Move Article Brief from 5-Active-Briefs/ to 9-Archive/_Completed-Briefs/"]
2. [e.g., "Save this output to 6-Completed-Articles/ as Article-20250120-Five-Principles-v1.0.md"]
3. [e.g., "Update CHANGELOG.md with completion entry"]
4. [e.g., "Update manifest.json if any spec documents were modified during execution"]
```

**Example:**
```markdown
## ARCHIVAL INFORMATION

**Archive Location:** 6-Completed-Articles/
**Archive Filename:** Article-20250120-Five-Principles-v1.0.md
**Brief Archived To:** 9-Archive/_Completed-Briefs/
**Brief Filename:** Article-Brief-20250120-Five-Principles.md
**Execution Log:** Entry #12 (2025-01-20, 14:32 UTC)
**Related Files:** None

**Next Actions:**
1. Move Article-Brief-20250120-Five-Principles.md from 5-Active-Briefs/ to 9-Archive/_Completed-Briefs/
2. Save this output to 6-Completed-Articles/Article-20250120-Five-Principles-v1.0.md
3. Update CHANGELOG.md with: "2025-01-20: Completed Article: Five Principles for Writing Effective AI Prompts (v1.0)"
4. No spec documents modified; manifest.json unchanged
```

---

## TEMPLATE USAGE NOTES

### When to Use This Template
- **Phase 6 (Archival & Logging):** After all gates pass and article is finalized
- **Post-revision:** When delivering updated versions (v1.1, v2.0, etc.)
- **Handoff to editor:** When transferring article to human review/editing

### When NOT to Use This Template
- **During drafting:** This is for final output only
- **Gate failures:** If any gate fails, fix issues before formatting final output
- **Interim checkpoints:** Use brief internal notes, not full template

### Template Flexibility
- **Optional sections:** Section 5 (Copy-Paste Ready) is optional; include if user needs clean version separate from metadata
- **Expandable:** Add custom sections for project-specific needs (e.g., "SEO Metadata," "Image Placeholders," "Translation Notes")
- **Collapsible:** For simple workflows, combine Sections 3 & 4 into single "Quality Validation" section

### Integration with Execution Meta-Prompt
This template implements the deliverables specified in **Article-Execution-Meta-Prompt.md, Phase 6 (Archival & Logging)**:

> "Produce a structured output containing:
> - Article metadata (title, brief used, word count, gates passed)
> - Complete article text (clean, deliverable version)
> - Gate validation summary
> - Archival instructions (where to save brief, article, update logs)"

All required elements are present in Sections 1–6 above.

---

## QUICK REFERENCE: Minimal Output Format

For simple workflows, this minimal version satisfies all requirements:

```markdown
## [ARTICLE TITLE]

**Metadata:** [Word count] words | Brief: [Brief filename] | Shape: [Hard shape] | Style: [Anchor name] | Gates: A✅ B✅ C✅

---

[ARTICLE TEXT - FULL]

---

**Gates Passed:**
- Gate A: Style Anchor declared, hard shape declared, third-person voice ✅
- Gate B: Voice/Focus/Evidence/Final-line/Devices/Anti-redundancy ✅
- Gate C: APA compliance, freshness, references complete ✅

**Metrics:** [X] paragraphs, [Y] citations, [Z] devices activated

**Archive:** Save to 6-Completed-Articles/[filename].md | Move brief to 9-Archive/_Completed-Briefs/
```

---

**This template standardizes Phase 6 delivery for all articles produced via Article-Spec-Pack-v1.**
