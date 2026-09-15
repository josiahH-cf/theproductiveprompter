# Final Prose Naturalization Directive

**Purpose:** Apply a mandatory final style edit after the article's intent, facts, evidence, and structure are settled. Return the same article in direct, natural prose without formulaic AI-style language.

This is a style edit, not a summary, fact-check, authorship claim, or detector-evasion guarantee.

---

## 1. Runtime Contract

This directive is part of a CLI-driven, model-agnostic article system.

- All normal execution enters through the repository's article CLI. A web interface, manual upload flow, provider-specific agent, or named model must not be a required part of the process.
- The CLI filters configured routes by capability and recorded reachability. Drafting, voice candidates, and this edit share the run's assigned writing-experiment model. The default assignment rotates through the configured pool; it is not a quality ranking. Before voice selection, an unavailable assignment may use a recorded pool fallback, preferring promoted stage evaluations when available. Other stages use promoted task-specific evidence or explicitly uncalibrated routing.
- Selection is task-specific. For this naturalization pass, an eligible model must be able to preserve long-form meaning, follow detailed editing constraints, and retain Markdown, links, citations, code, quotations, and identifiers accurately.
- The operator's runtime policy may constrain quality, privacy, locality, cost, and latency. Within those constraints, demonstrated task fitness and gate performance determine the choice.
- If the selected model cannot pass preservation and naturalization checks, use the bounded repair path. After the author chooses a voice, do not silently replace the writing model. An unavailable pinned writer or exhausted repairs blocks the run explicitly.
- Preserve the workflow's truthful public drafting-model disclosure. Exact routes, versions, fallbacks, and evaluation limitations remain in the run records.

The same article requirements and quality gates apply regardless of which model performs the task.

---

## 2. Editing Target

Edit the complete publication candidate supplied by the article workflow. Treat it as the source of truth.

Do not rewrite source code, commands, configuration, formulas, structured data, logs, direct quotations, cited excerpts, or generated metadata unless the article brief explicitly targets them. Edit only the surrounding prose.

---

## 3. Hard Character Policy

Do not use the em dash character U+2014 in editable public prose. This is a deterministic character rule, not a contextual cliché judgment. It applies to drafts, edited articles, titles, descriptions, and new publication strings.

Replace each occurrence according to meaning with a comma, colon, parentheses, or separate sentences. Do not mechanically substitute one punctuation mark everywhere.

If a locked quotation, code sample, identifier, or other protected field contains U+2014, do not silently alter it. Reopen the evidence or quotation decision, then paraphrase, omit, or replace the protected material through the appropriate workflow gate. A publication candidate containing U+2014 does not pass.

---

## 4. Preservation Contract

Preserve:

- Meaning, facts, numbers, dates, names, qualifications, and uncertainty
- Intent, commitments, conditions, exceptions, warnings, and limitations
- Audience, tone, language, useful specificity, and recognizable voice
- Useful Markdown structure, links, citations, footnotes, filenames, paths, and identifiers
- Code fences, inline code, commands, URLs, formulas, data, and configuration exactly
- Direct quotations exactly unless paraphrasing was explicitly requested
- Required legal, regulatory, contractual, policy, and compliance wording

Do not add facts, evidence, examples, anecdotes, claims, opinions, promises, humor, emotion, personal experience, or authority that the source does not contain. Do not imply that a human wrote the article.

---

## 5. Required Editing Pass

Use a substantive but conservative pass:

1. Remove throat-clearing and generic setup that adds no meaning.
2. Delete canned transitions or replace them with the direct logical connection.
3. Turn staged questions and rhetorical fragments into normal prose when the staging adds no value.
4. Replace inflated verbs, vague abstractions, nominalizations, and generic praise with exact source-supported language.
5. Remove redundant qualifiers, stacked adjectives, repeated summaries, and duplicated conclusions.
6. Rewrite formulaic contrasts as one direct statement or demonstrate the distinction with evidence already in the source.
7. Vary sentence length and structure naturally; combine choppy fragments and divide overloaded sentences.
8. Prefer concrete nouns and active verbs while preserving intentional passive voice.
9. Remove every U+2014 em dash from editable public prose using context-appropriate punctuation or sentence boundaries.
10. Keep the result close to the original length unless repetition warrants removal or the article brief requests another length.
11. Preserve natural phrasing that already works. Do not rewrite solely for surface variation.
12. Read each section as continuous prose. Merge one-line dramatic stanzas when they repeat the surrounding explanation; inspect repeated openings, negative-positive contrasts, staged questions, symmetrical lists, and repeated conclusions across paragraphs. Preserve short paragraphs when they serve an actual instruction, transition, or example. Do not flatten useful code prompts or operational lists into prose.

When a cliché carries a real proposition, keep the proposition and rewrite its delivery. Delete it only when it contributes no information.

---

## 6. Formulaic-Prose Inventory

Inspect grammatical, tense, punctuation, capitalization, and close semantic variants. This inventory is a diagnostic seed, not a literal blacklist.

### Staged insight and generic setup

- `At its core`, `Here's the thing`, `The punchline is`, `The key takeaway`, `Worth naming`, `That's not nothing`
- `It's important to note`, `It's worth noting`, `You already know`, `Sit with that`
- `In today's world`, `In an ever-evolving`, `In the realm of`, `In a world where`, `In the age of`
- `When it comes to`, `Let's unpack`, `Let's explore`, `Delve into`, `Dive into`
- `Picture this`, `Imagine a world`, `The result?`, `The catch?`

### Repetitive rhetoric and artificial contrast

- Repeated `No X, no Y`, `Did not X, did not Y`, or `Don't X it; Y it` chains
- `Not just X, but Y`, `It's not about X, it's about Y`, `This isn't merely X; it is Y`, `More than just`
- `The question is no longer X, but Y`, `The real question is`, `Whether you're X or Y`, `From X to Y`
- Rhetorical question-and-answer pairs used only for drama
- Repeated negative-positive contrasts that restate one idea twice

### Inflated significance, metaphor, and hype

- `A testament to`, `Serves as a reminder`, `A powerful reminder`, `Underscores the importance`
- `Sheds light on`, `Paves the way`, `Bridge the gap`, `At the intersection of`, `Intricate interplay`
- `Unlock the power`, `Harness the power`, `Game-changer`, `Paradigm shift`, `New era`
- `Rich tapestry`, `Journey`, `Cornerstone`, `Catalyst`, `Transformative`
- `Revolutionize`, `Disrupt`, `Redefine`, or `Reshape` without source support
- Decorative metaphors and unsupported claims of significance

### Corporate and marketing language

- `Leverage X to Y` when `use` names the action
- `Seamless`, `Robust and scalable`, `Holistic approach`, `Multifaceted`, `Actionable insights`
- `Foster`, `Empower`, `Elevate`, `Future-proof`, `Frictionless`, `End-to-end`, `Turnkey`, `Mission-critical`
- `Data-driven`, `Customer-centric`, or `User-centric` when they replace a concrete description
- `Cutting-edge`, `State-of-the-art`, `Best-in-class`, `World-class`, `Next-level`
- Generic praise such as `dynamic`, `comprehensive`, `innovative`, `powerful`, `crucial`, `vital`, or `essential`
- `Enable`, `Facilitate`, `Ensure`, `Optimize`, or `Enhance` when a more exact verb exists

### Generic urgency, balance, and future claims

- `Now more than ever`, `No longer optional`, `The possibilities are endless`, `Only scratching the surface`
- `No one-size-fits-all`, `A delicate balance`, `Challenges and opportunities`
- `Moving forward`, `As we look ahead`, `The future of X`, `X is poised to`, `Only time will tell`
- `There is no denying`, `One thing is clear`, `Cannot be overstated`

### Canned transitions and conclusions

- `Ultimately`, `In conclusion`, `At the end of the day`, `Simply put`, `That said`
- `With that in mind`, `The answer lies in`, `By doing so`, `What this means is`
- `Make no mistake`, `The reality is`, `The truth is`, `Against this backdrop`
- `It goes without saying`, `Needless to say`, `It bears mentioning`, `Without further ado`
- `The bottom line`, `In essence`, `To summarize`, `This is where X comes in`, `Enter X`
- Repeated `Additionally`, `Moreover`, `Furthermore`, or `However` openings

### Generated-looking structure

- Excessive three-part adjective or verb sequences
- Staccato slogans such as `Faster. Smarter. Better.`
- Repeated sentence openings, paragraph formulas, summaries, or closing formulas
- Excessive one-sentence paragraphs, headings, bold labels, or mechanically symmetrical lists
- Generic second-person claims and unsupported universals such as `everyone`, `always`, `never`, or `the only solution`
- Vague quantifiers when the source supports a more precise statement
- Double hedges such as `may potentially`, `could possibly`, or `might perhaps`
- Inflated noun phrases such as `the implementation of`, `the utilization of`, or `the optimization of`
- Artificial `on the one hand / on the other hand` balance when no real balance exists

Keep a listed phrase when it is deliberate, quoted, technically necessary, legally required, or the clearest accurate wording in context.

---

## 7. Safe Rewrite Order

1. Delete language that contributes no information.
2. State the underlying proposition directly.
3. Replace an inflated or vague word with the exact supported verb, noun, or condition.
4. Convert staged contrast into one affirmative sentence.
5. Replace a rhetorical question with its answer when the question adds no value.
6. Replace abstract significance with observable behavior already present in the source.
7. Merge repeated conclusions into the strongest single statement.
8. Keep the original when a replacement would lose precision, voice, legal effect, quotation fidelity, or technical meaning.

---

## 8. Output and Final Check

Return only the revised Markdown article. Do not include a preface, explanation, change log, score, checklist, authorship claim, or offer for further revision.

Before returning it, verify silently:

- Meaning, facts, intent, uncertainty, and requested action are unchanged.
- No new claims or examples were introduced.
- Formulaic AI-style language was removed or rewritten where supported.
- No U+2014 em dash remains in editable public prose.
- Listed phrases were not removed blindly when context made them accurate or necessary.
- The prose is direct, specific, readable, and natural without artificial errors or gimmicks.
- Tone, audience, language, formatting, links, citations, code, and quoted material remain intact.

If the article already satisfies this directive and no supported edit improves it, return it unchanged.

## 9. Contextual Review and Learning

The later editorial assessment must record exact excerpts and specific reasons for four checks: language, rhetoric, structure, and preservation. A clean phrase scan cannot establish naturalness. A whole-article PASS cannot override an unresolved passage finding. Keep this review private; the naturalization editor still returns only the article.

Read the active voice profile and its paired examples. A selected paragraph is local evidence about that passage's wording and cadence. Candidate letters are not stable style categories, and one choice does not isolate every declared trait. Compare selected and unselected examples, preserve shared qualities, and avoid inventing the author's reason. New guidance remains provisional until independent articles and author feedback support it. Do not treat growing profile history as proof that writing quality has improved.

---

**Version:** 1.2
**Date:** September 15, 2026
**Status:** Normative, model-agnostic, CLI-enforced final-prose gate for all publication candidates.
