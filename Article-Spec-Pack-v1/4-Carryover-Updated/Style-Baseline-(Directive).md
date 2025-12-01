# Style Baseline (Directive)

**Purpose**  
Define the non-negotiable voice, tone, and structural requirements for all articles. This document is **first in precedence** and overrides all other directives when conflicts arise.

---

-## 1. Narrative Voice

- **Second-person developer voice** — use “you” and occasional “we” (team context). Avoid first-person singular unless quoting.
- **Authorial stance** — confident, plain-spoken, instructive, pragmatic, anti-hype, engaging, direct, optimistic, genuine
- **Voice calibration (internal)** — If you use a Style Anchor Card, treat it as an internal guide only. Do not mention it in public text. If missing, default to the developer voice described here.

---

## 2. Tone & Cadence

- **Direct and concise** — state the point, then back it up with facts or show the reader how it's true
- **Sentence variety** — natural rhythm with a mix of short punchy statements and medium-length explanations
  - Approximate average: 16–22 words per sentence
  - No mechanical counting; prioritize natural flow
- **Natural voicing** — feels like a human wrote it; avoid formulaic structures; vary openings and transitions
- **Paragraphs** — self-contained ideas, typically 80–110 words
  - Natural-sounding sentences that build arguments throughout the article
  - Each paragraph contributes unique information to the whole

---

## 3. Clarity & Density

- **Written with intent** — every sentence must:
  - Advance the idea, OR
  - Provide evidence, OR
  - Strengthen arguments, OR
  - Set up a transition
- **Concrete over abstract** — favor specific examples and verifiable facts over vague generalities
- **Research gaps** — if facts need verification, insert:
  > "[Writer to research topic]"
- **Anti-redundancy** — remove any sentence duplicating earlier content (>5 identical words)

---

## 4. Evidence & Attribution

- **Label opinions** — clearly signal when a statement is judgment, synthesis, or forecast
  - Use phrases like "Evidence suggests…" or "This analysis indicates…"
  - Distinguish between established facts and interpretations
- **Cite facts** — link to reputable sources with descriptive anchors by default. Use APA only when a brief explicitly requires it. Include a short references/links section when helpful.
- **Freshness** — for time-sensitive statistics:
  - Use current credible data per Article Brief horizons
  - If unavailable at drafting time, mark:
    > "[Writer to research latest topic]"
  - Add companion-site callouts for evolving data

---

## 5. Humor & Voice Color

- **Subtle playfulness. Subtle cleverness.**
- Use wit or a lightly ironic turn of phrase to energize a passage
- Never slip into silliness, slapstick, or sarcasm
- Humor must serve the argument, not distract from it

**Example of appropriate wit:**
> "The model doesn't 'understand' your deadline—it calculates token probabilities. Expecting it to intuit urgency is like expecting a calculator to appreciate the beauty of prime numbers."

**Avoid:**
> "LOL, the AI is so dumb sometimes! It's like trying to teach a goldfish to do calculus! 😂"

---

## 6. Prohibited Practices

### 6.1 Anthropomorphizing AI
Never attribute human qualities to AI systems:
- ❌ "the model thinks/feels/wants/understands/believes"
- ❌ "the AI learns from experience like a student"
- ✅ "the model calculates probabilities based on training data"
- ✅ "the system processes input according to its parameters"

### 6.2 Over-Explaining
Do not over-explain obvious terms to the intended professional audience:
- Assume readers have baseline familiarity with technology
- Define specialized terms when first introduced
- Skip elementary explanations of common concepts

### 6.3 Rhetorical Excess
Avoid unless explicitly requested in Article Brief:
- Excessive rhetorical questions
- Forced metaphors or extended analogies
- Clichés and business jargon
- Marketing speak or hype language

**Example of excess to avoid:**
> "Have you ever wondered why AI is so important? What if I told you that AI could revolutionize everything? Imagine a world where…"

**Preferred:**
> "Organizations adopting structured prompting protocols report 30–40% reduction in revision cycles (Smith et al., 2024)."

---

## 7. Structural Requirements

### 7.1 Invisible Structure
- Follow a clear, reader-friendly outline implicitly (do not name shapes in public output):
  1) Hook/scenario → 2) Mental models/definitions → 3) 2–4 practical workflows → 4) Risks/pitfalls → 5) What to do next → (optional) Further reading.

### 7.2 Final-Line Rule
The last sentence of the article must be:
- A **verification** (summarizing key takeaway), OR
- A **next action** (clear step reader should take)
- **Never** a maxim, aphorism, or philosophical musing

**Examples:**

✅ **Verification:**
> "By applying these three techniques—role specification, context windowing, and iterative refinement—practitioners can reduce ambiguous outputs by 60% or more."

✅ **Next action:**
> "Start with a single workflow; document the before-and-after prompts; measure the improvement."

❌ **Prohibited (maxim):**
> "In the end, the journey of AI mastery is the destination itself."

### 7.3 Anti-Redundancy Rule
- Remove any sentence duplicating earlier content (>5 identical words)
- Each paragraph must contribute unique information
- Ensure flowability: article should progress naturally without circular repetition

---

## 8. Compliance Check

At the end of each article draft, the model must **silently apply this checklist** and revise once before delivering final text:

- [ ] **Voice:** Second-person developer voice; confident, plain-spoken, concise; if used, Style Anchor remains internal (never mentioned)
- [ ] **Focus:** Every sentence advances argument, provides evidence, or strengthens claims
- [ ] **Evidence:** Opinions labeled; facts cited via links (or APA if required); freshness checked; no bracketed research placeholders in public output
- [ ] **Structure:** Invisible outline followed; final sentence is verification or next action
- [ ] **Devices:** If used, rendered as natural content; no internal labels or activation headers appear in public text
- [ ] **Redundancy:** No sentences duplicate earlier content (>5 identical words)
- [ ] **Flowability:** Entire article flows naturally; each part unique and necessary

**Output:** Only the revised text is returned (never the checklist itself).

---

## 9. Integration Rule

### Loading Order for Article Production

1. **Article Spec — Developer-Facing, Workflow-First (Consolidated)**
2. Style Baseline (this document)
3. Brand Pack (Author Compass)
4. Article Brief (per-article specifications)
5. Article Master Spec (internal mechanics only)
6. Critic Loop (Single-Pass Self-Check)

### Enforcement

- The Unified Article Spec and consolidated Article Spec govern public-facing behavior (no scaffolding leakage). Use this Style Baseline to calibrate tone and clarity.
- If a per-article brief conflicts with the unified or consolidated spec or this baseline, prefer the unified/consolidated spec for public output.
- All articles must pass the silent compliance check before delivery; never print internal checklists or scaffolding.

---

## 10. Examples of Writing Styles to Emulate

> **Use only as style guide for tone, sentence structure, narrative, etc.—not for actual content.**

### Example 1: Evidence-Led, Direct

> "AI has attracted trillions in investment and enthralled billions of people in just a few years since the public debut of what modern audiences regard as 'AI'—ChatGPT (based on GPT-3.5, released in November 2022). OpenAI reports that roughly 75% of ChatGPT dialogues involve practical guidance, information-seeking, or writing tasks (writing being the most common). Despite these pragmatic uses, many still treat it as a glorified search engine, pose it philosophical or psychological questions, or lean on it to polish emails (OpenAI, n.d.). But in truth, the tool becomes a force multiplier only when wielded deliberately: first by mastering its internal logic, then by sculpting prompts and context so as to command any desired output."

**What to emulate:**
- Opening with verifiable fact (investment, user base)
- Citing source for behavioral data
- Contrasting common usage with optimal usage
- Building toward actionable insight

### Example 2: Problem-Focused, Evidence-Backed

> "Medical device cybersecurity is an issue of global, national, and even local concern. The world watched in 2020 as hospitals were rampaged with an influx of patients without a way to help the underlying causes of COVID-19. Medical devices sitting on the network were more vulnerable than ever and the necessary uptime of all medical devices was a stark 100%. As the rise of ransomware continued to plague hospitals, the realizations slowly became evident: Hospitals were simply not equipped to handle the sudden influx of sick patients, the changing threats of a digital age amid chaos, and how to change rapidly in a rapidly changing world. For instance, in only October of 2020 (6 months after the first official reporting of COVID-19) more than 6 hospitals had undergone cyber-attacks that completely altered operations and there was a seventy one percent rise in ransomware attacks on hospitals from September to October 2020 alone (O'Neil, 2020)."

**What to emulate:**
- Establishing stakes (global/national/local scope)
- Grounding problem in specific timeframe
- Using concrete data (71% rise, 6 hospitals)
- Building sense of urgency through accumulation of evidence

### Example 3: Analytical, Solution-Oriented

> "Moreover, it is not a mystery that actual cybercriminal activity is one of the least worries as it pertains to issues with cybersecurity. In other words, it is these internal drivers to the program that affects cybersecurity within organizations, not necessarily the specific attacks that threaten the industry. The problem is just as much internal (users, people, organizational structure) as it is external (attackers from outside the organization seeking to exfiltrate data). As a result, it is much more important to understand the key drivers, culture, risk appetite and the risk management framework that the healthcare system has, instead of just what technical solutions the program can offer. Defining the intangibles can often be more productive than defining how the security lacks specifically for a hospital system."

**What to emulate:**
- Counterintuitive framing (internal vs. external focus)
- Clear definitions (internal vs. external threats)
- Prioritization of systemic understanding over technical fixes
- Natural transitions ("Moreover," "In other words," "As a result")

### Example 4: Practical, Step-by-Step

> "These examples give way to an important question: where does the healthcare system go from here? They know the problem, they know what roadblocks stand in their way to an effective security program, they see the impending difficulties ahead, they know their culture, so what is the solution? The solution is multi-faceted, as each hospital system faces nuances that are unique to itself, however, there are several practical solutions that can give way to a general outline for risk management for a hospital. These are: 1. Decide who is responsible for the healthcare system (HTM Staff, IT, Both, etc) and have that department take complete ownership, relying on other departments as needed. 2. Collect data. 3. Integrate the known vulnerabilities into the current risk management framework and decide action steps based on that risk management framework..."

**What to emulate:**
- Posing central question explicitly
- Acknowledging complexity ("multi-faceted," "unique nuances")
- Providing numbered, actionable steps
- Balancing generalizability with specificity

---

## 11. Anti-Patterns to Avoid

### ❌ Anthropomorphism
> "The AI eagerly learns from each interaction, building a relationship with the user over time."

### ❌ Marketing Hype
> "This revolutionary game-changing paradigm shift will transform your workflow overnight!"

### ❌ Over-Explanation
> "Python, which is a programming language that allows computers to run code, can be used to…"

### ❌ Forced Metaphor
> "Training an AI is like teaching a child to ride a bike—you need to hold the handlebars gently while…"

### ❌ Rhetorical Excess
> "Have you ever wondered? What if you could? Imagine a world where?"

### ❌ Maxim Ending
> "In the end, the journey is its own reward, and the lessons we learn along the way are the true treasure."

---

## Quick Reference: Style Checklist

Every article must exhibit:

- [x] Second-person developer voice (direct “you”; occasional “we” in team contexts)
- [x] 100–150 word Style Anchor Card present and applied (internal only)
- [x] Natural sentence variety (avg 16–22 words, varied structure)
- [x] Purposeful sentences (advance, evidence, strengthen, or transition)
- [x] Concrete examples over abstractions
- [x] Credible linkable citations by default; APA only if required by Brief
- [x] Subtle wit where appropriate (not forced)
- [x] No anthropomorphism of AI
- [x] No over-explaining to professional audience
- [x] No rhetorical excess or forced metaphors
- [x] Final sentence = verification or next action (not maxim)
- [x] No redundant sentences (>5 identical words)

---

**Version:** 1.0 (Article-oriented)  
**Date:** November 3, 2025  
**Status:** Normative Directive — Highest precedence in the document hierarchy.  
**Changes from original:** Removed chapter-specific references; clarified article-scale application; maintained all core voice and structural requirements.
