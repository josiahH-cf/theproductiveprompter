# Article Brief

## 1. Article Metadata

**Working Title:**
From Idea to Verified URL: Build a Blog Workflow That Still Sounds Like You

**Intended Audience:**
Independent creators, solo publishers, technically curious bloggers, and small content teams using AI to help research, write, or publish. Readers may understand prompts, Markdown, a CMS, or basic automation, but they should not need workflow-engine or software-architecture expertise.

**Publication Context:**
Standalone article for The Productive Prompter. The article will use the publication system that produced it as a transparent worked example.

**Estimated Scope:**
Approximately 2,000–2,700 words. Explain the smallest understandable architecture for moving a sparse idea through editorial development, iterative voice calibration, packaging, deployment, and live verification. Exclude machine-readable schemas, orchestration syntax, code-heavy setup, vendor comparisons, and a full SEO implementation guide.

## 2. Objective & Scope

**Objective:**
Help readers draw and evaluate their own AI-assisted blog-publication workflow. By the end, they should be able to define stages that produce observable artifacts, gates that make explicit decisions, a repeatable method for teaching their blog's voice, and a testable definition of "published."

**Scope:**
- Begin with the desired public outcome, then work backward to the initial seed.
- Explain the difference between a stage, gate, repair loop, bounded retry, escalation, and terminal state in plain language.
- Present two linked loops: editorial development and publication.
- Show why voice must be learned iteratively from examples, corrections, and regression cases rather than captured in one adjective list.
- Use The Productive Prompter's 31 Days experiment, Article Spec Pack, current launcher, Markdown viewer, and publication gaps as the case study.
- Cover intent, evidence, voice, packaging, deployment, and live-verification checks.
- Keep platform-specific states behind a conceptual adapter; mention Markdown/GitHub Pages and WordPress only as short examples.
- Exclude full workflow implementation, YAML/JSON, code samples, model rankings, CMS tutorials, and promises of search indexing.

**Constraints:**
Second-person, practical developer-adjacent voice; plain language; linkable citations; no private paths or operator notes; no claims that planned components already work; no unnecessary statistics; no internal quality-gate names such as Gate A/B/C. The generic terms “stage” and “gate” are explicitly required by the operator and may appear publicly.

**Required Content Blocks:**
- One uncluttered diagram showing the editorial and publication loops plus the handoff between them.
- Two or three brief mental models: workflow versus agent, stage versus gate, deployment versus verified publication.
- Four practical sections: define the finish line; build stages and gates; teach voice iteratively; publish and verify.
- A compact “what not to automate blindly” caution covering owner intent, unsupported evidence decisions, irreversible publication, credentials, and disputed voice judgments.
- A final build checklist organized as Before / During / After.

## 3. Core Argument

**Central Thesis:**
A trustworthy blog-publication automation is not one giant prompt; it is a visible sequence of artifact-producing stages, explicit decision gates, bounded repair loops, iterative voice calibration, and live verification.

**Supporting Claims:**
- Start with the verified public outcome and work backward, because “draft created” and “deployment succeeded” are weaker outcomes than “the intended article is accessible and represented correctly.”
- A stage performs work; a gate evaluates evidence and chooses what happens next. Conflating them hides failures and creates endless revision loops.
- Workflows suit repeatable editorial paths; more autonomy should be introduced only where the route genuinely cannot be predefined and verification remains available.
- A distinctive blog voice requires a versioned learning loop built from representative examples, explicit traits and anti-patterns, author-ranked near misses, and separate checks for voice fit, content preservation, and naturalness.
- Publication must be rerun-safe and verified across the page, metadata, internal discovery surfaces, and the chosen crawler/discovery outputs.
- One real article is the minimum useful test: failures should change the workflow, not be edited out of the case study.

## 4. Planning Aids

**Opening reality check:**
Open with the meta situation: this article began as one short paragraph, but a real workflow had to preserve it, research the topic, confirm intent, build a brief, and refrain from drafting too early. Contrast that with asking for “a blog post about blog automation” in one step.

**Primary diagram:**
Seed → intent → research/brief → draft → critique/voice repair → editorially ready → package → validate → deploy → inspect live page → verified URL. Show gates beneath the relevant transitions and a repair arrow returning to the exact failed stage. Keep visual labels short.

**Comparison treatment:**
Use short paired definitions rather than a dense table: stage/gate, retry/repair, deploy/publish, voice/tone.

**Project callouts:**
- The 31 Days experiment proved that content generation, bulk scheduling, and deployment could be automated, while human review and tone remained the expensive parts.
- The spec pack evolved from default style guidance to examples, criticism, and a preservation-focused final prose pass.
- The current launcher resolves the canonical workflow but does not yet implement the planned dynamic model router.
- The current public article route demonstrates why a successful Pages deployment does not complete rendered-content and discoverability verification.

**Checklists:**
- Gate checklist: artifact, decision criteria, owner, pass path, repair path, attempt limit, escalation, recorded evidence.
- Voice checklist: representative examples, stable voice traits, situational tone, anti-patterns, near-miss feedback, preservation check, held-out test.
- Before / During / After build checklist as the closing activation.

## 5. Freshness Expectations

**Time-Sensitive Topics:**
- Anthropic workflow and evaluation guidance: use current official documentation and clearly separate general principles from product-specific behavior.
- Google Search guidance: use current Search Central documentation for Article structured data, JavaScript rendering, canonicals, sitemaps, and inspection; do not imply that submission guarantees indexing.
- GitHub Pages and Actions deployment controls: use current official documentation if implementation details appear.
- Current state of The Productive Prompter: verify directly against local source and the live site immediately before finalizing.

**Stable Topics:**
- Workflow modeling concepts from BPMN and state machines: authoritative foundational sources are acceptable.
- Provenance concepts from W3C PROV-O and structural validation concepts from JSON Schema: use as background, not as required reader homework.
- Text-style evaluation research: peer-reviewed work from 2019 onward is acceptable when its limits are stated.
- HTTP idempotence: use the current RFC as the normative source.

**Research Gaps:**
- Do not generalize results from sentiment/style-transfer benchmarks directly to authorial blog voice; identify any recommendation built by inference.
- Do not claim the current project performs full idea-to-live automation or dynamic model routing.
- Do not infer search-indexing failure from a client-rendered shell; describe only the observed response and Google's documented rendering model.

**Companion-Site Policy:**
No generic companion-site freshness callouts. Link directly to authoritative sources and the public project materials when useful.

## 6. Success Criteria

**Evaluation Checks:**
- [ ] A reader can redraw the two-loop workflow without learning a workflow language.
- [ ] A reader can distinguish stages, gates, retries, repair loops, escalations, and terminal states using the article's examples.
- [ ] Every recommended gate names an observable artifact and a pass/fail consequence.
- [ ] The voice section provides a repeatable calibration loop, not a list of flattering adjectives.
- [ ] Voice fit, meaning preservation, and naturalness are evaluated separately.
- [ ] The case study distinguishes demonstrated capabilities, current gaps, and intended architecture.
- [ ] “Published” ends with a verified URL and page/discovery checks, without promising search indexing.
- [ ] The final checklist gives readers a small first implementation they can test with one article.

**Quality Benchmarks:**
The article must remain understandable on a first read, use no machine-readable schema, avoid framework sprawl, and cite primary or authoritative sources near material claims. The diagram and checklists must reduce complexity rather than repeat prose.

## 7. Risks & Assumptions

**Risks:**
- Over-engineering a personal blog workflow and intimidating the intended reader.
- Turning “voice” into surface mimicry or allowing a rewrite to alter facts, uncertainty, citations, or the author's position.
- Presenting an evaluator's score as a substitute for author judgment.
- Treating every failure as retryable and accidentally duplicating publication-side effects.
- Confusing a green deployment with a rendered, discoverable, correct article.
- Hiding the example project's incomplete components and undermining the case study's credibility.
- Letting research citations overwhelm the practical throughline.

**Assumptions:**
- Readers already use or are considering AI during article creation.
- They can adapt a conceptual workflow to a CMS, static site, or mixed toolchain.
- They want a workflow that preserves ownership and distinctiveness, not maximum autonomous throughput.
- The article may honestly discuss current gaps while keeping private local details out of public prose.

## 8. Integration Notes

**Cross-References:**
- Anthropic, “Building effective agents,” prompting best practices, and evaluation guidance.
- Google Search Central guidance for Article structured data, JavaScript SEO, canonical URLs, sitemaps, and URL inspection.
- AWS state-machine choice and error-handling documentation as implementation background.
- W3C PROV-O, JSON Schema, NIST AI RMF, GitHub deployment environments, WordPress post states, and RFC 9110 where they clarify a specific claim.
- Mailchimp and Nielsen Norman Group guidance on voice versus tone.
- Wang et al. on personal-style imitation and Mir et al. on style-transfer evaluation tradeoffs.
- Public 31 Days articles and Article Spec Pack documentation from The Productive Prompter.

**Tone Adjustments:**
Direct, curious, and practical. Let the meta example provide personality. Use occasional dry understatement, but avoid performance, hype, or over-polished motivational language. Prefer concrete contrasts and operational questions.

**Special Instructions:**
- The project is evidence, not a victory lap.
- Label cross-source synthesis as inference where sources do not directly establish the recommendation.
- Treat adversarial review as four independent attacks: evidence, workflow failure modes, voice/meaning drift, and reader complexity.
- The last sentence must direct the reader to run one article through the workflow and record the first failed check.

**Status:** Operator-approved intent translated into binding Article Brief on 2026-08-18.
