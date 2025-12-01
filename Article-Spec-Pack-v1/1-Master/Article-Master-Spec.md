# Article Master Spec (Aligned with Developer-Facing Consolidated Spec)

**Purpose**  
This master spec defines internal mechanics (planning, review, and archival) for article production. Public-facing articles must follow the workflow-first, developer-facing behavior defined in `Article-Spec-Consolidated.md` without exposing internal scaffolding (devices, gates, shapes, style anchors).

---

## 1. Scope & Application

This specification governs the production of **single-pass articles** for _The Productive Prompter_. Articles are standalone pieces written in one continuous draft cycle and delivered as clean, publication-ready manuscripts with no visible internal scaffolding.

**Key behavior for public outputs:**
- No internal labels or scaffolding in article text (no Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass)
- Invisible structure: hook → models/definitions → 2–4 workflows → pitfalls → next steps → optional references
- Developer voice (second person), pragmatic, anti-hype

---

## 2. Voice & Narrative Standards

### 2.1 Voice for Public Articles
- **Second-person developer voice** — “you” and occasional “we” (team context)
- **Authorial stance** — confident, plain-spoken, instructive, pragmatic, direct, optimistic, genuine

### 2.2 Tone & Cadence
- **Direct and concise** — state the point, then back it up with facts or show the reader how it's true
- **Sentence variety** — natural rhythm with a mix of short punchy statements and medium-length explanations (approx. 16–22 words on average, no mechanical counting)
- **Natural voicing** — feels like a human wrote it
- **Paragraphs** — self-contained ideas, typically 80–110 words; natural-sounding sentences that build arguments throughout the article

### 2.3 Clarity & Density
- **Written with intent** — every sentence must advance the idea, provide evidence, strengthen arguments, or set up a transition
- **Concrete over abstract** — favor specific examples and verifiable facts over vague generalities
- If facts need research, insert **[Writer to research topic]**

### 2.4 Humor & Voice Color
- **Subtle playfulness. Subtle cleverness.**
- Use wit or a lightly ironic turn of phrase to energize a passage; never slip into silliness, slapstick, or sarcasm

### 2.5 Prohibited Practices
- Anthropomorphizing AI (e.g., "the model thinks/feels/wants")
- Over-explaining obvious terms to the intended professional audience
- Excessive rhetorical questions or forced metaphors unless explicitly requested in the Article Brief

---

## 3. Dynamic Length Policy

**Principle:** Article length is determined by **content strength and scope**, not fixed word counts.

- Articles should be **generally** 1,500–2,500 words for developer posts; expand only when added detail provides concrete value (workflows, prompts, code).
- Length **must vary based on:**
  - Depth of argument required
  - Evidence complexity
  - Number of activated devices
  - Topic scope defined in the Article Brief
- **No numeric bands or rigid targets** — write to completeness, not to a counter

**Quality gate:** Every article must feel **complete** — no padded filler to hit a target, no rushed compression that sacrifices clarity.

---

## 4. Structural Requirements

### 4.1 Invisible Structure (Public)
- Follow this outline implicitly (do not name shapes in the article):
  1) Hook/scenario → 2) Mental models/definitions → 3) 2–4 practical workflows → 4) Risks/pitfalls → 5) What to do next → (optional) Further reading.

### 4.2 Anti-Redundancy Rule
- Remove any sentence duplicating an earlier idea (>5 identical words)
- Each paragraph must contribute unique information to the whole
- Ensure flowability across the entire article — each section flows naturally into the next

### 4.3 Final-Line Rule
- The last sentence of the article must be a **verification or next action**, never a maxim or aphorism
- Must provide closure or a clear takeaway

---

## 5. Formatting & Reflowability

All formatting must support Kindle/EPUB3 reflowability:

- **No images for core information** — all tables, callouts, and decision trees must be semantic text
- **Tables:** Use Markdown or HTML-like structures that preserve headings and columns
- **Callouts/Boxes:** Format as clearly labeled text blocks, not graphics
- **Lists:** Use semantic nested lists (bullets or numbered) for complex structures
- **Provide alt text** if diagrams are later designed by publisher

---

## 6. Narrative Behaviors (Planning Only)

- Use device definitions as internal planning aids (see [Device-Catalog.md](../3-Annexes/Device-Catalog.md)).
- Render all behaviors naturally in public text (scenes, Q&A subheadings, tables, checklists, prompt before/after), with no activation headers or labels.
- If a brief specifies a behavior, ensure its intent is met without exposing internal scaffolding.

---

## 7. Evidence & Citation Standards

### 7.1 Public Citations
- Prefer concise, linkable sources with descriptive anchors. Use APA 7 only if a brief explicitly requires it.
- Include a short references/links section when helpful to readers.

### 7.2 Dynamic Freshness Policy
- **No fixed 12-month default**
- Freshness horizons are **dynamic** and defined by:
  - Topic type (rapidly evolving vs. stable)
  - Article Brief specifications
  - Best available information at time of drafting
- For time-sensitive claims, find the **most current credible source**
- If no current source exists, insert **[Writer to research latest <topic>]**

### 7.3 Research Pass
- Triggered when freshness gates fire or Article Brief specifies
- **No-new-claims rule:** May replace, update, or remove evidence, but must not introduce new argumentative claims
- Re-run Critic Loop after research changes

**Reference:** See [Evidence-and-IP-Annex.md](../3-Annexes/Evidence-and-IP-Annex.md) for detailed citation and freshness protocols.

---

## 8. Quality Gates (Silent)

Every article must pass three sequential gates:

### Gate A — Baseline
- Developer voice aligned (second person)
- Invisible structure followed (no public shape labels)
- No scaffolding leakage (no Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass in article text)

### Gate B — Silent Self-Check
- Single silent pass completed (Voice, Focus, Evidence)
- Final-line rule satisfied (verification or next action)
- Natural rendering of planned behaviors (no activation headers)
- Anti-redundancy check passed

### Gate C — Evidence & Freshness
- APA compliance verified
- Dynamic freshness satisfied or gaps bracketed
- Research Pass executed if triggered
- Companion-site callouts added where appropriate

**Enforcement:** Gates are checked silently. Only compliant final text is returned.

---

## 9. Single-Pass Article Workflow

1. **Plan:** Create Article Brief defining scope, intent, device activations, and freshness expectations
2. **Draft:** Write complete article in one pass following this Master Spec
3. **Critic Loop:** Silently apply Voice, Focus, and Evidence checks; revise once
4. **Research Pass (if triggered):** Update citations and verify freshness
5. **Final QA:** Confirm all gates passed
6. **References:** Compile consolidated APA references

**Reference:** See [Article-Process-Map.md](./Article-Process-Map.md) for detailed workflow.

---

## 10. Precedence Model

When conflicts arise among directive documents, resolve in this order:

1. **Style Baseline (Directive)**
2. **Brand Pack (Author Compass)**
3. **Article Brief (per-article)**
4. **Critic Loop (Single-Pass Self-Check)**
5. **Evidence & IP Annex (APA + IP)**
6. **Device Catalog (Annex)**

The first document in this list takes precedence as the tiebreaker.

---

## 11. Compliance Checklist (Silent)

Before finalizing any article, confirm:

- [ ] Second-person developer voice maintained throughout
- [ ] Invisible structure followed; no shape named in public text
- [ ] Final sentence is verification or next action
- [ ] No redundant sentences (>5 identical words to prior content)
- [ ] All non-common-knowledge claims cited in APA format
- [ ] Dynamic freshness requirements met or gaps bracketed
- [ ] Behaviors planned via device concepts rendered naturally; no activation headers
- [ ] Reflowable formatting used for all tables/callouts
- [ ] Silent self-check executed (Voice, Focus, Evidence)
- [ ] Quality Gates A–C passed (internal)

---

## 12. Integration with Other Documents

- **Article Spec (Consolidated):** Governs public-facing behavior, structure, voice, and non-leakage
- **Style Baseline (Directive):** Calibrates tone and prohibited practices (internal reference)
- **Brand Pack (Author Compass):** Establishes brand voice and neutrality
- **Article Brief Template:** Provides activation authority for devices and freshness horizons
- **Device Catalog:** Defines available devices and formatting rules
- **Evidence & IP Annex:** Specifies APA standards and dynamic freshness protocols
- **Critic Loop:** Enforces quality checks silently before output

---

**Version:** 1.1  
**Date:** November 13, 2025  
**Status:** Normative — Internal mechanics aligned to consolidated developer-facing spec.
