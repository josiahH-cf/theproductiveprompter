**Purpose**  
Guarantee that every drafted section—whether a full chapter or a focused sub-chapter—meets the book’s style, evidence, and argument requirements **before** it reaches the human author.  
The Critic Loop enforces compliance through a **single self-review and revision cycle** embedded in every generation step.

---

### How the Critic Loop Fits in the Drafting Process

1. **Load order before drafting:**
   - Style Baseline (Directive)
   - Brand Pack (Author Compass)
   - Active Chapter Brief
   - Relevant Sub-chapter Briefs (if any)
   - Critic Loop (this document)

2. **Generation cycle:**
   - The model **drafts the section** (chapter or sub-chapter).
   - Immediately performs the Critic Loop (the three checks below).
   - Revises once—**silently**—to fix issues.
   - Returns **only the revised text**, never the intermediate or uncorrected draft.

This guarantees compliance without adding filler or meta-commentary to the final manuscript.

---

### The Three Checks

Each check is mandatory and must be applied in order.  
If any criterion fails, the model **must revise** before producing the final output.

---

#### 1. Voice Check

Ensure the draft fully aligns with the **Style Baseline (Directive)**:

- Strict **third-person narration**; no “I,” “we,” or direct second-person address except in approved quotations.
- Confident, plain-spoken, instructive tone with subtle clever humor as appropriate.
- Sentence rhythm and paragraphing consistent with Style Baseline (varied, intentional, 80–110 words per paragraph on average).

---

#### 2. Focus Check

Validate that the text fulfills the **Brand Pack’s mission** at the start of the prompt sequence and the **specific objectives and theses** of the active Chapter and Sub-chapter Briefs:

- **Written with intent** — every sentence advances the idea, provides evidence, strengthens arguments, or sets up a transition.
- No filler, repetition, or tangential digressions.
- All required narrative moves and artifacts from the briefs are present and correctly integrated (tables, Prompt Plates, decision trees, cross-references, etc.).
- Cohesion - the entire chapter should be taken into consideration when writing sections. Each section should be written with the whole in mind.
- **Movement & length compliance** — Confirm that section and movement boundaries match the approved outline and planned word ranges (≈700–1,200 words per movement) to preserve context-window integrity.
- **Hard-shape conformity** — Verify that exactly **one declared shape** (from the approved set) governs the draft end-to-end.
- **Final line rule** — Ensure the last sentence is a **verification or next action**, never a maxim.
- **Device gating** — If any narrative device appears, confirm the brief explicitly named the device and its purpose; otherwise remove it.

If anything is missing or off-focus, rewrite and integrate the missing elements.

---

#### 3. Evidence & Attribution Check

Verify that all claims meet the book’s evidence and citation standards:

- **APA-format in-text citations** for every factual claim that is not common knowledge.
- A running **references list** (or update to the parent chapter’s list) with complete APA entries and live links when allowed.
- **Freshness** — time-sensitive statistics must be drawn from credible sources and current at drafting time.
- **Freshness gate action** — If a time-sensitive claim lacks a current citation, either perform a **Research Pass** or insert a bracketed note (e.g., “[Writer to research latest adoption rate]”).
- **Gaps flagged** — when credible sources are unavailable or a claim requires further research, explicitly mark the need.

If any citation is missing, outdated, or fabricated, correct or flag it before final output.

---

### Output Requirement

After performing all three checks and making one internal revision, the model outputs:

- **Only the final, revised text**
- No checklists, reasoning notes, or compliance reports.

The Critic Loop is invisible to the reader but ensures the manuscript meets professional publishing standards.

---

### Integration Rule

The Critic Loop must be explicitly referenced in every drafting prompt.  
For example:

> “Generate the section described above. After drafting, apply the Critic Loop (Voice, Focus, Evidence) and revise once. Return only the revised text.”

**Movement scope:** Apply the Critic Loop to each internal **movement** (within a section) as well as to full sections to maintain granularity and context-window integrity.

---

### Quick Reference: What This Template Solves

- **Voice integrity:** Enforces third-person, confident, concise style and **Style Anchor binding**.
- **Argument fidelity:** Ensures every chapter or sub-chapter fulfills its objectives and avoids filler; enforces **hard-shape** and **final-line** rules.
- **Citation quality:** Guarantees fresh, verifiable APA citations; triggers **Research Pass** or flags gaps for time-sensitive claims; enforces **device gating** when applicable.