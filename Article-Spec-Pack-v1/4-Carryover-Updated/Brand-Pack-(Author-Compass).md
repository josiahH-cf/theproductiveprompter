# Brand Pack (Author Compass)

**Purpose**  
Define the brand voice, neutrality standards, and device policy for _The Productive Prompter_. This document establishes the foundational voice and relationship framework that applies to all articles.

---

## Brand Voice

- **Neutral, precise, and evidence-led**
- **Second person by default for developer articles** (direct “you” with occasional “we” in team context); first person singular only if explicitly briefed
- **No marketing speak; minimal metaphor** — use only when it sharpens understanding
- **Confident and instructive** — write with authority grounded in evidence
- **Plain-spoken** — favor clarity over cleverness; subtle wit only when it serves the point

---

## Relationship to Other Documents

### Precedence Rule

When conflicts arise, resolve them in this exact order:

1. **Style Baseline (Directive)**
2. **Unified/Consolidated Article Spec**
3. **Brand Pack (Author Compass)** ← This document
4. **Article Brief** (per-article specifications)
5. **Critic Loop (Single-Pass Self-Check)**
6. **Evidence & IP Annex (APA + IP)**

This order is **binding** and must be logged if a conflict is resolved.

**Article-specific note:** The **Article Brief** may override general guidance in this document for specific articles (e.g., tone adjustments, device activations, freshness horizons), but **never** overrides Style Baseline or Brand Pack voice fundamentals.

---

## Device Policy (Planning Aids)

Treat narrative devices as **internal planning aids**. They must never be labeled or surfaced in public text.

**Activation authority:** The Article Brief may request specific behaviors (e.g., scenario vignette, Q&A, comparison table), but outputs render as natural prose with no activation headers.

**Prohibition:** Do not include activation headers or internal labels in public articles.

---

## Integration with Drafting Process

### At Article Start

**Follow the implicit reference structure** (do not label it in public text):
Opening reality check → 2–3 mental models → 3–5 workflows (When/Why/Pattern/Steps) → caution → tri-stage checklist → closing activation → optional further reading.

**Load order:**
1. Style Baseline (Directive)
2. Unified/Consolidated Article Spec
3. Brand Pack (Author Compass) ← This document
4. Article Brief
5. Critic Loop

### During Drafting

- Ensure each paragraph is well-formed and contributes unique information; avoid repetition
- Use **credible linkable citations by default**; apply APA only if the Article Brief requires it
- Apply **anti-redundancy checks** (no sentences duplicating earlier content with >5 identical words)
- **Flowability:** The entire article should flow naturally from section to section; each part necessary and unrepeated
 - **Workflow Schema (silent):** When workflows are present, express PromptSpec (role/objective/constraints/success criteria), OutputMode, expected artifacts, ValidationPlan, ChangeIsolation, RollbackNotes, and Guardrails in natural prose (do not expose labels). For refactor workflows, prefer diff output and include a review checklist artifact.

### After Drafting

- Apply the **Critic Loop** only after the article is complete
- Normalize tone without adding new facts
- Consider the whole of the article — each part necessary and unrepeated

---

## Freshness Gate

**Dynamic freshness policy:** No fixed 12-month default. Freshness is determined by:
1. **Topic type** (rapidly evolving vs. stable)
2. **Article Brief specifications** (topic-specific horizons)
3. **Best available information** at time of drafting

**If article contains time-sensitive claims** (e.g., market size, adoption rate, regulation update):
- **Trigger a Research Pass** to find current citation, or generalize/remove the claim
- Do not insert bracketed placeholders into public text
- Add companion-site callouts only if requested by the Article Brief

**Reference:** See [Evidence-and-IP-Annex.md](../3-Annexes/Evidence-and-IP-Annex.md) for detailed freshness protocols.

---

## Enforcement

All articles are checked against:
- **Style Anchor Card presence** (internal; 100–150 words)
- **Implicit structure** (reference flow present; no labels)
- **Final-line verification** (last sentence is verification or next action, not a maxim)
- **No scaffolding leakage** (no device/activation headers, gates, shapes in public text)
- **Freshness gating** (time-sensitive claims have current sources or are generalized; no public brackets)
 - **Vendor-neutrality:** Prefer generic techniques and tools; avoid vendor lock-in language unless briefed.
 - **Security-sensitive exclusions:** Do not outsource authN/authZ, compliance logic, or secrets handling to AI outputs; treat as human-owned domains.

**Failure on any check stops publication until corrected.**

---

## Voice Consistency Across Articles

While each article may have specific focus areas, all articles share:
- **Third-person narration** (except when Article Brief explicitly permits first person)
- **Evidence-led argumentation** (claims backed by APA citations)
- **Neutral, precise language** (no marketing speak, hype, or unsubstantiated enthusiasm)
- **Purposeful sentences** (every sentence advances, evidences, or transitions)
- **Subtle cleverness** (wit where appropriate, never forced)

**Variation permitted:** Article Briefs may request:
- Emphasis on practical vs. theoretical
- More or fewer examples
- Technical depth adjustments
- Specific tone colors within Style Baseline constraints

These variations **do not override** core voice requirements.

---

## Quality Gates Integration

Articles pass through three quality gates:

**Gate A — Baseline & Structure**
- Style Anchor present (internal)
- Implicit structure present
- Second-person developer voice enforced (for developer articles)

**Gate B — Critic Loop**
- Voice, Focus, Evidence checks completed
- Final-line rule satisfied
- Device activations validated

**Gate C — Evidence & Freshness**
- Citations credible (APA only if required by Brief)
- Dynamic freshness satisfied or claims generalized/updated
- Research Pass executed if triggered

**Reference:** See [Article-Master-Spec.md](../1-Master/Article-Master-Spec.md) for detailed gate criteria.

---

## Brand Voice Examples

**Preferred (neutral, precise, evidence-led):**
> "Research from Stanford's Center for Research on Foundation Models (2024) shows that larger context windows reduce error rates in multi-turn dialogues by 18–22%. Organizations can leverage this capability by structuring prompts to include relevant history, reducing the need for repeated context setting."

**Avoid (marketing speak, unsubstantiated claims):**
> "AI is revolutionizing everything! With amazing new context windows, you'll never have to worry about losing information again. It's a game-changer that will transform your entire workflow overnight!"

**Preferred (subtle cleverness):**
> "The model doesn't 'understand' your deadline—it calculates token probabilities. Expecting it to intuit urgency is like expecting a calculator to appreciate the beauty of prime numbers."

**Avoid (forced metaphor, anthropomorphization):**
> "The AI wakes up each morning ready to learn from you, eagerly absorbing your feedback like a sponge soaking up water. It's a journey you take together, hand in hand."

---

## Integration Notes

- This document applies to **all articles** unless Article Brief specifies exceptions
- Voice and neutrality requirements are **non-negotiable** (Style Baseline takes precedence)
- Device policy and freshness gates are **binding** (no devices without activation; no stale claims without bracketing)
- Precedence chain ensures conflicts are resolved deterministically

---

**Version:** 1.0 (Article-oriented)  
**Date:** November 3, 2025  
**Status:** Normative — Updated from chapter-oriented version to support article production.  
**Changes from original:** Removed chapter/sub-chapter references; updated precedence chain to reference Article Brief; clarified dynamic freshness policy; emphasized article-scale flowability.
