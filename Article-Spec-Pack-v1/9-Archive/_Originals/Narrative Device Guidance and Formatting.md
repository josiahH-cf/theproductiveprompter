**Purpose**  
Define how to include optional narrative devices that make _The Productive Prompter_ vivid and practical, while preserving strict voice control and reflowable formatting for Kindle/EPUB3.  
These devices are **off by default** and appear **only when explicitly requested** in a Chapter or Sub-chapter Brief.

---

### 1. Prompt Plates

**Purpose**
- Show principle-first prompting in action.
- Demonstrate “before/after” contrasts to prove claims about better outputs and reduced prompt counts.

**When to Use**
- To illustrate a specific prompting principle, troubleshooting pattern, or repeatable workflow.
- To provide a concrete, re-usable template readers can adapt.

**Integration Instructions**
- Present as a **reflowable table** or **code block**, not an image.
- Columns typically include: _Scenario_, _Prompt (before)_, _Prompt (after)_, and _Outcome_.
- Keep examples real or clearly labeled as representative tests (e.g., from live prompt logs or controlled experiments).
- Include a brief lead-in sentence explaining the principle the plate proves.
- Cite sources or personal workflow data if relevant, in APA format.
- **Activation header (required when used):** Add a single line immediately before the device:  
  `Device: Prompt Plate — Purpose: {copied verbatim from brief}`

---

### 2. Decision Trees / Checklists

**Purpose**
- Provide structured, repeatable guidance for complex tasks.
- Help readers troubleshoot or plan in a logical, branching format.

**When to Use**
- To guide readers through a multi-step reasoning process (e.g., diagnosing poor model outputs).
- To illustrate a workflow or conditional sequence (e.g., “If the model refuses, then …”).

**Integration Instructions**
- Render as **semantic nested lists** (bullets or numbered outlines) for Kindle/EPUB3 reflow.
- Keep branch labels short and imperative (e.g., “Check context length → Revise prompt → Test again”).
- Introduce each tree with a sentence or two explaining its purpose and scope.
- Provide APA citations if the tree is derived from external research or best practices.
- **Activation header (required when used):** Add a single line immediately before the device:  
  `Device: Decision Tree / Checklist — Purpose: {copied verbatim from brief}`

---

### 3. What the Papers Say

**Purpose**
- Distill key academic or industry findings that validate or challenge the book’s arguments.
- Offer authoritative evidence in a digestible format.

**When to Use**
- To highlight a pivotal whitepaper, peer-reviewed study, or market report that substantiates a claim.
- To keep fast-moving research accessible without derailing the narrative.

**Integration Instructions**
- Use a short, clearly labeled callout box.
- Include:
  - **Paper/Source name and authors.**
  - **One-paragraph summary of the finding.**
  - **Direct APA citation and live link** (to DOI or official source) where possible.
- Conclude with one sentence linking the finding back to the chapter’s Local Thesis.
- **Freshness gate (required for time-sensitive claims):** If the cited finding contains statistics or market measures, confirm it is current per the brief’s freshness horizon; otherwise add  
  `[Writer to research latest <topic>]` and reference the companion site as needed.
- **Activation header (required when used):** Add a single line immediately before the device:  
  `Device: What the Papers Say — Purpose: {copied verbatim from brief}`

---

### 4. Optional Devices & Future Extensions

Other devices (e.g., **Illustrative Analogies**, **Cross-reference boxes**, or **Live Code Experiments**) may be added if a Chapter or Sub-chapter Brief explicitly requires them.  
Integration follows the same rules: reflowable format, concise explanatory lead-in, and APA citation where applicable.  
- **Activation header (required when used):**  
  `Device: {Device Name} — Purpose: {copied verbatim from brief}`

---

### 5. Integration Rule

- Use best judgement when determining if a Narrative Device would be well suited for the sub-chapter.
- **Activation:** A Chapter or Sub-chapter Brief must explicitly name the device and specify its function.
- **Execution:** When activated, the model:
  1. Drafts the section text.
  2. Integrates the device as instructed (table, nested list, callout) **preceded by the required Activation header line**.
  3. Runs the **Critic Loop** to ensure voice, focus, and evidence compliance.

---

### 6. Kindle/EPUB3 Reflowability Requirements

- **No images for core information.** All tables, checklists, and callout boxes must be semantic so text can reflow on any e-reader.
- **Use Markdown or HTML-like structures** that preserve headings, bullets, and table columns for clean export.
- **Provide alt text** if diagrams are later designed by the publisher, ensuring accessibility.