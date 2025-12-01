# Completed Articles

**Purpose:** This folder contains finalized articles and their associated briefs/metadata. Note: Public article text must not include internal scaffolding labels (Device/Gate/Hard Shape/Style Anchor). Any gate/device details here are internal QA metadata.

---

## Folder Structure

Each completed article gets its own subfolder with the following layout:

```
6-Completed-Articles/
├── [article-name]/
│   ├── article.md                   ← Public-ready article (only top-level file)
│   ├── briefs/
│   │   └── brief.md                 ← Approved Article Brief
│   ├── reports/
│   │   └── Article-YYYYMMDD-Title-v1.0.md (and any later versions)
│   ├── references/
│   │   └── references.md            ← APA reference list (if used)
│   ├── sources/
│   │   └── [chapter-source].md      ← Original intake file moved from `0-Article-Content/`
│   └── drafts/ (optional)
│       └── additional experiments, redlines, etc.
└── ...
```

> Keep `article.md` as the only top-level deliverable. Everything else belongs in a clearly named subfolder so the final post is immediately accessible while supporting assets stay available but tidy.

---

## Metadata Schema

Each `metadata.json` (optional; use when execution tooling produced one) contains:

```json
{
  "title": "Article Title",
  "topic": "topic-slug",
  "created_date": "YYYY-MM-DD",
  "completion_date": "YYYY-MM-DD",
  "word_count": 0,
  "gates_passed": {
    "gate_a": true,
    "gate_b": true,
    "gate_c": true
  },
  "devices_used": ["Prompt Plate", "What the Papers Say"],
  "hard_shape": "Claim→Evidence×4",
  "research_pass_executed": false,
  "critic_loop_runs": 1,
  "brief_checksum": "md5hash",
  "article_checksum": "md5hash",
  "execution_run_id": "run-001"
}
```

---

## Quality Assurance

All articles in this folder have been verified to meet internal quality gates (silent in public outputs):

- **Gate A:** Developer voice, invisible structure, anti-leak (no internal labels in article text)
- **Gate B:** Critic Loop passed (Voice, Focus, Evidence); final-line rule satisfied; planning behaviors rendered naturally
- **Gate C:** Citations/links compliant per Evidence & IP Annex; freshness satisfied or gaps bracketed; Research Pass if needed

---

## Spec Conformance (Author-Facing)

For any article containing workflows, the following must be evident in natural prose (no labels exposed):

- PromptSpec present (role, objective, constraints, success criteria)
- Output mode stated (e.g., “return a unified diff”, “draft a 7–10 item checklist”)
- Expected artifacts clear (diff, checklist, codemod prototype, grep pattern)
- Validation plan stated (tests to add/adjust; logs/metrics to compare; compare script)
- Change isolation and exclusions articulated
- Rollback notes included (how to revert per step/PR)
- Guardrails stated (vendor-neutral; no new deps; avoid authZ/authN/compliance)

Note: For refactor workflows, prefer diff output and include a code review checklist artifact.

---

## Publication Workflow

Before moving an article into this folder, run the packaging checklist:

1. Create the article subfolder (use slug `Article-YYYYMMDD-Title/`).
2. Place the final manuscript at `article.md` (no other files at the root).
3. Move the approved brief to `briefs/brief.md`.
4. Move Critic Loop summaries, gate validations, and versioned drafts to `reports/`.
5. Move APA lists or evidence logs to `references/`.
6. Move the originating chapter from `0-Article-Content/` into `sources/` (retains the original filename for traceability and clears the intake folder).
7. Add any interim drafts or experimental passes to `drafts/` (optional).

Following this checklist keeps every finished article self-contained: one click to reach the publishable file, with all supporting history available in predictable locations.

### Automation helper (run at end of Phase 7)

Use the packaging script to apply the checklist in one shot:

```bash
python scripts/package_article.py \
  --article-folder "6-Completed-Articles/Article-YYYYMMDD-Slug" \
  --source-file "0-Article-Content/NN-chapter-name.md"
```

Add `--mapping pattern=folder` arguments if new artifact types emerge; the script already skips `article.md` and only reorganizes files in the specified folder.

Articles here are ready for:
1. Final human editorial review
2. Formatting for publication platform
3. Companion website upload (if needed)
4. Integration into book manuscript (if applicable)

---

## Archive Policy

Completed articles remain in this folder indefinitely unless:
- Published and archived separately
- Superseded by updated version (move old version to `9-Archive/`)
- User initiates cleanup protocol

---

**All files are read-only once placed here.** Any revisions require creating a new article with updated brief. Historical content may retain legacy markers in metadata; do not treat legacy internal labels as public template guidance.
