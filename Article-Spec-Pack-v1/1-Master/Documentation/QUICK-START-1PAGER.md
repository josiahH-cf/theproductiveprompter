# Article-Spec-Pack-v1 Quick Start (1 Pager)

**Time Required:** ~15 minutes first execution | ~10 minutes subsequent executions

---

## TASK 1: Understand What You're Doing (3 min)

Read these files **in order** to understand the pack:
1. `0-README.md` — Overview of what this pack does
2. `Sample-Completed-Article-Annotated.md` — See what a finished article looks like
3. **This page** — You're reading it ✓

**Key Concept:** You provide a brief → AI generates article → You archive it. All quality gates automated.

---

## TASK 2: Create Your Article Brief (5 min)

**File to use:** `2-Templates/Article-Brief-Template.md`

**Copy this template into a new document and fill in:**

- **Title:** What's your article about?
- **Intended Audience:** Who reads it? (e.g., "Business leaders, 0-2 years AI experience")
- **Estimated Scope:** How long? (e.g., "~2,000 words")
- **Objective:** What should readers be able to do after reading?
- **Scope:** What topics IN, what topics OUT?
- **Constraints:** Any limits? (word count, audience level, tone, etc.)
- **Central Thesis:** One-sentence main argument
- **Supporting Claims:** 3-5 key points
- **Device Activations:** Any special elements? (tables, examples, checklists)
- **Freshness Expectations:** How recent should sources be?
- **Success Criteria:** How will you know it worked?

**Save as:** `My-Article-Brief-[Topic].md`

**Example:** `My-Article-Brief-RAG.md` for "What is RAG?"

---

## TASK 3: Convert to PDF (2 min)

**Convert these to PDF format:**

**Option A - Using Pandoc (Recommended):**
```
pandoc "My-Article-Brief-[Topic].md" -o "My-Article-Brief-[Topic].pdf"
```

**Option B - Manual:**
- Copy markdown text → Paste into Google Docs → Export as PDF

**Files to Convert (12 total):**
- 11 spec files from pack (see list in Step 4)
- 1 your brief (just created)

**Pro Tip:** Use a folder called `PDFs-for-Gemini/` and convert all 12 there

---

## TASK 4: Upload to Gemini (2 min)

**Go to:** https://aistudio.google.com/app/apikey (or Gemini web GUI)

**Upload in this order:**
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
12. `My-Article-Brief-[Topic].pdf` ← **Your brief**

**Click:** "Attach files" → Select all 12 PDFs → Upload

---

## TASK 5: Execute Meta-Prompt (1 min)

**Copy this prompt and paste into Gemini:**

```
You have been provided with 10 PDF files containing a complete specification pack 
for autonomous article generation. These files define 
normative requirements, workflow phases, quality gates, and precedence hierarchy 
for producing publication-ready articles.

PRECEDENCE HIERARCHY (binding order):
1. Style-Baseline-(Directive).pdf — Voice requirements
2. Brand-Pack-(Author-Compass).pdf — Brand values
3. My-Article-Brief-[Topic].pdf — YOUR SPECIFIC INSTRUCTIONS (HIGHEST AUTHORITY)
4. Critic-Loop.pdf — Quality checks
5. Evidence-and-IP-Annex.pdf — Citations, research, freshness
6. Device-Catalog.pdf — Special elements (tables, examples, etc.)

TASK:
Execute the 7-phase workflow from "Article-Execution-Meta-Prompt.pdf" to 
generate a complete article based on "My-Article-Brief-[Topic].pdf".

PROCEED TO Phase 1 and confirm: "All 10 PDFs uploaded successfully?"
```

**Click Send.** Gemini will confirm uploads and ask to proceed.

---

## TASK 6: Approve 3 Checkpoints (3 min)

**Gemini will ask you 3 times to approve. Each time:**

**Checkpoint 1 (Phase 1):** Brief Summary
- Gemini echoes your brief
- Verify it's correct
- **Respond:** "Approved" or describe corrections

**Checkpoint 2 (Phase 2):** Execution Plan
- Gemini shows: scope, length, devices, freshness strategy
- Verify it matches your intent
- **Respond:** "Approved" or request changes

**Checkpoint 3 (Phase 3):** Final Go-Ahead
- Gemini asks "Ready to draft?"
- **Respond:** "Approved" or "Hold"

---

## TASK 7: Review Article (3 min)

**Gemini generates complete article.** Look for:
- ✅ Article title matches your brief
- ✅ Word count near your target
- ✅ All devices you requested (tables, examples, etc.)
- ✅ Citations present (APA format or [RESEARCH GAP] markers)
- ✅ Ends with verification + next action (not just a maxim)

**If something is wrong:**
- Note the issue
- Revise your brief
- Re-run with updated brief (don't edit article manually)

**If it's good:**
- Proceed to Task 8

---

## TASK 8: Copy & Archive (2 min)

**Copy Article Text:**
- Select Gemini output (Section 2 or 5 of output template)
- Copy complete article text

**Save Article:**
1. Open notepad or VS Code
2. Paste article text
3. Save as: `Article-[Date]-[Topic]-v1.0.md`
   - Example: `Article-20251103-RAG-v1.0.md`
4. Save location: `Article-Spec-Pack-v1/6-Completed-Articles/`

**Archive Brief:**
1. Find your original brief file
2. Move to: `Article-Spec-Pack-v1/9-Archive/_Completed-Briefs/`

**Update Log (Optional):**
1. Open `Article-Spec-Pack-v1/CHANGELOG.md`
2. Add this line at the top of history:
   ```
   2025-11-03: Completed Article: [Your Title] (v1.0)
   ```

---

## 🎯 YOU'RE DONE!

| Step | Task | Time | ✓ |
|------|------|------|---|
| 1 | Read 0-README + Sample Article | 3 min | |
| 2 | Create Article Brief | 5 min | |
| 3 | Convert 12 files to PDF | 2 min | |
| 4 | Upload to Gemini | 2 min | |
| 5 | Paste meta-prompt | 1 min | |
| 6 | Approve 3 checkpoints | 3 min | |
| 7 | Review article | 3 min | |
| 8 | Copy & archive | 2 min | |
| | **TOTAL FIRST TIME** | **21 min** | |

---

## TROUBLESHOOTING

**"PDF won't convert"**
→ Use Google Docs method (copy → paste → export)

**"Gemini can't read PDFs"**
→ Re-save with simpler filenames (no emoji, spaces OK)

**"Article is too long/short"**
→ Revise brief constraints → Re-run (don't edit manually)

**"Missing citations"**
→ Check Evidence-and-IP-Annex.pdf for no-search guidance

**"Gates failed?"**
→ Gemini will note which gate. Review brief and re-run.

---

## NEXT TIME (Faster)

After first article, subsequent ones take **~10 minutes**:
- Create brief (2 min)
- Upload PDFs (1 min)
- Approve phases (2 min)
- Review article (2 min)
- Archive (1 min)
- **Repeat**

---

## GETTING HELP

- **How does this work?** → Read `0-README.md`
- **I want to see an example** → Open `Sample-Completed-Article-Annotated.md`
- **How do I deploy to Gemini?** → Read `PDF-Upload-Quick-Start-Guide.md`
- **Something went wrong** → Check troubleshooting in PDF guide

---

**Ready? Start with TASK 1. Come back here if you get stuck.**
