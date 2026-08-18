# Adversarial Review

**Target:** `draft-v1.md`
**Review posture:** Attempt to falsify the article's claims, break its workflow, expose voice drift, and simplify anything a first-time reader would struggle to apply.

## Attack 1 — Evidence and overclaiming

### Findings

1. **Voice research is easy to overstate.** The draft correctly limits Wang et al. to the conclusion that examples alone were insufficient under the study's setup and names the lack of large-scale human evaluation. Keep this limitation adjacent to the claim.
2. **The three-part voice gate is a synthesis.** Mir et al. studies style transfer rather than personal blog voice. The draft labels the adaptation; preserve that label through all edits.
3. **The project retrospective is self-report.** Keep its timing, quality, model-ranking, employment, and industry claims out of the article. Phrase retained lessons as “the retrospective reports.”
4. **The site inspection is a dated observation.** Add “at the time of this review” to sitemap/feed and metadata findings. State that JavaScript updates the browser title after load so the raw shell is not mistaken for the final browser output.
5. **Google's mechanisms are not guarantees.** The draft correctly excludes guaranteed indexing and rich results. Preserve “can help,” “chosen discovery surface,” and asynchronous indexing language.
6. **The launcher claim describes current local work.** Simplify the technical router language and distinguish working discovery/control loading from planned per-task model selection.

### Verdict

Pass after the time-bound project wording and launcher simplification are applied.

## Attack 2 — Workflow failure modes

### Findings

1. **The article never explicitly calls the diagram/checklists a human-readable schema.** Add that connection so the original “workflow and schema” promise is fulfilled without YAML.
2. **Portability is asserted but not demonstrated.** Add one short adapter example: internal editorial states remain stable while Markdown/Git and WordPress express them differently.
3. **Version binding is under-specified.** Require each run to record the workflow version, voice-profile version, and deployed revision so later changes do not rewrite history.
4. **Concurrent or partial publication could fool verification.** The live check must verify the exact intended revision, not merely any page at the expected URL.
5. **Retry, repair, and escalation are properly separated.** The timeout example and bounded subjective loop survive the attack.
6. **Human review could become approval theater.** Keep human ownership limited to intent, disputed evidence/voice, credentials, risk, and irreversible actions; do not require manual approval at every gate.

### Verdict

Three material repairs required: name the schema, show the platform adapter, and bind the live result to the intended revision.

## Attack 3 — Voice and meaning preservation

### Findings

1. **Cadence broadly matches the selected references.** The opening is concrete, the definitions are operational, and the close is an action.
2. **The voice section contains avoidable contrast formulas.** Replace “A voice document is useful. A voice-learning loop is better” with a demonstrated relationship. Replace the example-guidance “starting point/proof” contrast with one direct sentence.
3. **One project sentence is too implementation-heavy.** Replace “dynamic model router” with plain language describing task-specific model selection.
4. **The phrase “That is what the next publication loop should close” is a generic summary.** Remove it.
5. **No first-person singular narration appears outside a quoted near-miss example.** Pass.
6. **No repeated six-word-or-longer sequences were found.** Pass.
7. **The draft averages roughly 14 words per sentence, with one unquoted prose sentence over 35 words.** Readability is acceptable; split only if the naturalization pass reveals friction.

### Verdict

Pass after targeted de-formulaic edits. Do not globally shorten the prose; the current rhythm is part of the intended voice.

## Attack 4 — Reader complexity and usefulness

### Findings

1. **The single vertical diagram survives mobile-width scrutiny.** Keep it as plain text because the current site does not render Mermaid.
2. **The article contains many lists, but they perform the operator-requested checklist function.** Do not add a comparison table or machine-readable example.
3. **“Canonical URL” needs a plain-language gloss on first use.** Add “preferred public address.”
4. **The academic voice section is the densest part.** Retain only sources that change the method, and keep limitations in plain language.
5. **The build checklist yields a small first trial.** Add workflow/profile version recording but do not expand into implementation steps.

### Verdict

Pass after the terminology gloss and version-record item are added.

## Mechanical Checks on Draft v1

- Word count: 2,310 — within brief target.
- Duplicate sequences: no repeated six-, seven-, or eight-word sequences detected.
- Link check: all 13 unique public links returned successful HTTP responses on 2026-08-18.
- Prohibited marketing-language scan: no material hits.
- Internal scaffold scan: no Gate A/B/C, Style Anchor, Critic Loop, or Research Pass labels in public prose.

## Required Repair List

- [x] Name the diagram/checklists as the human-readable schema.
- [x] Add a short internal-state/platform-adapter example.
- [x] Bind each run to workflow version, voice-profile version, and deployed revision.
- [x] Verify the live page corresponds to the intended revision.
- [x] Define canonical URL in plain language.
- [x] Time-bound the current site observation.
- [x] Simplify planned model-routing language.
- [x] Remove three formulaic or generic summary constructions.
- [x] Re-run evidence, voice, link, and preservation checks after repair.

## Post-Repair Verification

- Final word count remains within the brief's 2,000–2,700-word target.
- All 14 unique public links returned successful HTTP responses on 2026-08-18.
- No repeated six-, seven-, or eight-word sequences were detected.
- No unquoted first-person singular narration, private paths, placeholders, or internal Gate A/B/C labels remain.
- The plain-text diagram has balanced code fences and a valid heading hierarchy.
- The final naturalization inventory scan returned no material matches.
- The final prose pass introduced no new claims, examples, citations, numbers, or opinions.

## Held-Out Voice Regression Results

1. **Safe publication retry:** Pass. The article explains inspection-before-repeat and duplicate-side-effect risk without requiring protocol jargon.
2. **Client-rendered route:** Pass. It distinguishes initial HTML from browser-rendered content and makes no unsupported indexing diagnosis.
3. **Voice evidence:** Pass. It preserves the Wang study's human-evaluation limitation and labels the three-part gate as a practical synthesis.
4. **Launcher boundary:** Pass. It separates working discovery/control loading from planned task-specific model selection.
5. **Closing action:** Pass. The final sentence directs one real trial and one recorded failed check.

**Status:** Adversarial review complete; publication candidate ready for operator review.
