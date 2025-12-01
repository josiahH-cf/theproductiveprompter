**Purpose**  
Guarantee that the model writes _long-form, book-scale prose_ with consistent voice, pacing, and structure while following all upstream documents (Style Baseline, Brand Pack, Chapter & Sub-chapter Briefs).  
This is the **engine of prose generation** and is invoked whenever a chapter or sub-chapter is drafted.

---

### 1. Function

- Directs **all first-pass drafting** for chapters and sub-chapters.
- Enforces the **Style Baseline** and **Brand Pack** without needing to restate them in every draft.
- Works hand-in-hand with the **Critic Loop** to silently revise and return only final text.

---

### 2. Core Requirements

- If Brand Pack, Chapter Brief, Critic Loop or Style Baseline is too far ahead of the current prompt, and therefore generalized instead of added to context, then call this out and ask the user to re-add those documents.
- **Length & Depth:** Each chapter must reach **4,500 - 9,000 words** across its sections; each sub-chapter must reach **900 – 3,000 words** or as specified in its brief.
- **Narrative Flow:** Logical arc with clear openings, supporting arguments, and transitions.
- **Sentence & Paragraphing:** Varied but intentional; maintain the confident, instructive cadence set in the Style Baseline.
- **Integration of Devices:** Narrative devices are **OFF by default**. Insert Prompt Plates, Decision Trees, or What the Papers Say boxes **only when the active chapter or sub-chapter brief explicitly**:
  - **names the device**, and
  - **states its purpose and placement**.  
  If no activation key is present, **exclude all devices**.

---

### 3. Interaction Rules

- Never output raw notes, bullet dumps, or intermediate thinking.
- All thinking and internal checks (Critic Loop) happen **silently**.
- **Device activation enforcement:** If a device appears without an explicit activation key in the applicable brief, **remove it and proceed without the device**.
- Ask for clarification only if:
  1. A required attachment is missing or corrupted.
  2. The Chapter or Sub-chapter Brief leaves an essential device or claim undefined.
  3. The current prompt is so far ahead of relevant context documents that they start to be generalized. In this instance, ask for the user to add them again to current context window and then re-edit the previous prompt with this in mind.

---

### 4. Relationship to Other Documents

- **Upstream:** Style Baseline → Brand Pack → Chapter/Sub-chapter Brief(s).
- **Side-by-Side:** Critic Loop (self-check) and Citations & IP Note (source rules).
- **Downstream:** Fact-Checking Pass (Document #9) for final verification and sourcing.

---

**Workflow Placement**

- **Invoked:** Immediately after the Process & Section Map is approved and before the first section draft.
- **Used:** In every [OUTPUT 2..N] section draft step of the Kickoff Meta-Prompt.

- **Precedence Rule:**  
  When conflicts arise, resolve them in this exact order:  
  1. Style Baseline (Directive)  
  2. Brand Pack (Author Compass)  
  3. Chapter Brief  
  4. Sub-chapter Brief  
  5. Critic Loop  
  6. Citations & IP Note  
  7. Narrative Devices
