# Intent-Discovery Research

## Status

Intent-discovery and pre-draft research are complete enough to draft. Adopted claims and exclusions are tracked in `claim-ledger.md`; source entries below remain a broader research record and should not all appear in public prose.

## Local baseline reviewed

### Personal Growth project

- `Documenting My Journey.md` defines the desired end-to-end outcome: a low-friction raw idea becomes a researched, vetted article at the canonical website endpoint, with traceable artifacts and intervention at defined escalations.
- `Define the Right Way to Build Something.md` supplies the methodological pressure behind the project: research before building, determine the method against verifiable information, make it reusable, and prove it through one real use.
- `Personal Growth - Litmus Test.md` turns the desired outcome into falsifiable questions rather than treating a written design as proof of completion.
- `Personal Growth - Global Project Tracker.md` records the decisions that led to the fresh-session trial and distinguishes demonstrated behavior from planned behavior.

### Article-system mechanism

- The global `$start-article` skill is intentionally thin. It runs `article-flow doctor`, resolves the repository-owned `0-START-ARTICLE.md`, and defers to that file so workflow updates stay centralized.
- `article_flow.py` currently performs discovery, preflight, context reporting, and entrypoint resolution. It does not execute the full workflow or perform dynamic per-task model routing.
- `0-START-ARTICLE.md` adds the current trial contract: preserve the raw seed; separate explicit input from assumptions; research before narrowing; ask focused questions; record research, intent, and trial friction; require intent confirmation before a brief or draft.
- `Article-Process-Map.md` models the lifecycle as understand → plan → draft → criticize/repair → research if triggered → final QA → references → package and publish.
- `Unified-Article-Spec.md` contains a separate, internal workflow-content schema for workflows taught inside an article: objective and constraints, requested output, expected artifacts, validation, change isolation, rollback, and guardrails.
- The completed-article README and website handoff define a third schema layer: package layout, metadata, publication files, and the public URL shape.

## External research queries

- `official guidance LLM workflows versus agents prompt chaining evaluator optimizer`
- `workflow modeling standard events activities gateways sequence flow`
- `provenance standard entities activities agents derivation responsibility`
- `JSON Schema structural validation official specification`
- `NIST AI workflow human oversight roles validation documentation`
- `Google Article structured data workflow versus publication schema`

## Direct sources and possible contribution

1. [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
   - Distinguishes workflows, which follow predefined code paths, from agents, which dynamically direct their own execution.
   - Recommends beginning with the simplest workable design and describes prompt chaining and evaluator–optimizer patterns.
   - Possible use: explain why a bounded article workflow can be the starting point before adding autonomous routing.
   - Operator takeaway: leverage this source. Stages and gates are crucial, and its evaluator–optimizer pattern may help explain iterative voice development.

2. [Object Management Group — BPMN 2.0.2](https://www.omg.org/spec/BPMN/)
   - Provides a formal vocabulary for events, activities, gateways, and sequence flow.
   - Possible use: test whether the article should describe the workflow schema as states, transitions, and decision gates rather than as a pile of prompts.
   - Operator takeaway: pending.

3. [W3C — PROV-O](https://www.w3.org/TR/prov-o/)
   - Models provenance with entities, activities, and agents, including derivation, attribution, and responsibility.
   - Possible use: ground the seed/research/intent/brief/draft trail as provenance rather than incidental logging.
   - Operator takeaway: pending.

4. [JSON Schema — structural validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation)
   - Defines machine-checkable constraints on the structure of JSON instances.
   - Possible use: distinguish a conceptual workflow map from a machine-readable run-record contract that can reject missing fields.
   - Operator takeaway: pending.

5. [NIST — AI Risk Management Framework Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
   - Calls for documented purpose, scope, roles, oversight, testing, monitoring, and risk controls across an AI system lifecycle.
   - Possible use: frame human review as a defined ownership and risk decision, not a generic approval step added everywhere.
   - Operator takeaway: pending.

6. [Google Search Central — Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
   - Covers structured data attached to a published article and the validate/deploy/inspect cycle.
   - Possible use: explicitly separate publication metadata/SEO schema from the workflow and provenance schemas used to create the article.
   - Operator takeaway: leverage this source as part of the publication layer, while continuing research beyond it.

7. [Anthropic — Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
   - Treats examples as a reliable way to steer format, tone, and structure, while warning through its relevance/diversity guidance that examples can teach unintended patterns.
   - Possible use: establish curated positive examples as one input to voice calibration rather than relying on adjectives alone.
   - Operator takeaway: pending.

8. [Anthropic — Define success criteria and build evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)
   - Recommends specific, measurable, task-relevant criteria; treats tone and style as one dimension in a multi-dimensional evaluation; and describes iterative testing before shipping.
   - Possible use: turn “sounds like this blog” into a versioned rubric and test set instead of an impression made at the end.
   - Operator takeaway: pending.

9. [GitHub Docs — Using custom workflows with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
   - Separates build and deploy jobs, passes a built artifact between them, associates deployment with an environment, and exposes the deployment URL as output.
   - Possible use: demonstrate that publishing is a distinct, observable stage with an artifact and returned URL rather than another drafting instruction.
   - Operator takeaway: pending.

10. [GitHub Docs — Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
    - Documents branch restrictions, wait timers, required reviewers, environment secrets, and custom protection rules.
    - Possible use: show how automatic and human gates can be selected by risk rather than inserting approval into every run.
    - Operator takeaway: pending.

11. [Nielsen Norman Group — The Four Dimensions of Tone of Voice](https://www.nngroup.com/articles/tone-of-voice-dimensions/)
    - Models tone along formal/casual, serious/funny, respectful/irreverent, and matter-of-fact/enthusiastic spectra; recommends explicit anti-tone words, user testing, and situational variation within a consistent brand personality.
    - Possible use: give readers a concrete starting vocabulary for a voice profile and distinguish stable voice from topic-dependent tone.
    - Operator takeaway: pending.

12. [Wang et al. — LLMs still struggle to imitate the implicit writing styles of everyday authors](https://aclanthology.org/2025.findings-emnlp.532/)
    - Evaluates personal-style imitation across news, email, forums, and blogs. The study reports weaker performance on nuanced, informal blog/forum writing and limited gains from simply adding more demonstrations.
    - Possible use: challenge the assumption that dropping a few past posts into context is enough to preserve a distinctive blog voice.
    - Operator takeaway: pending.

13. [Google Search Central — JavaScript SEO basics](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
   - Explains the crawl → render → index sequence for JavaScript-generated pages, the extra rendering queue, and the need to inspect rendered HTML.
   - Possible use: strengthen the post-deployment gate for client-rendered Markdown blogs: a successful file upload or HTTP response does not by itself verify rendered content and discoverability.
   - Operator takeaway: pending.

14. [AWS — Choice workflow state](https://docs.aws.amazon.com/step-functions/latest/dg/state-choice.html) and [error handling in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
   - Separates work states from conditional transitions and makes the no-match path explicit. Its error model distinguishes bounded retries from catch/fallback transitions.
   - Possible use: give readers a concrete vocabulary for stages, gates, retryable failures, terminal failures, and human escalation without requiring them to adopt AWS.
   - Operator takeaway: pending.

15. [WordPress REST API — Posts](https://developer.wordpress.org/rest-api/reference/posts/)
   - Exposes a platform-specific publication lifecycle through `draft`, `pending`, `future`, `publish`, and `private` states alongside slug, author, date, content, excerpt, and taxonomy fields.
   - Possible use: demonstrate why a portable workflow needs internal editorial states that map onto—rather than duplicate—CMS-specific public states.
   - Operator takeaway: pending.

16. [Mailchimp Content Style Guide — Voice and Tone](https://styleguide.mailchimp.com/voice-and-tone/)
   - Treats voice as the stable personality and tone as something that changes with the reader's situation; it supplements abstract traits with concrete writing rules.
   - Possible use: keep a blog's voice profile stable while allowing per-article tone settings and observable do/don't rules.
   - Operator takeaway: pending.

17. [Mir et al. — Evaluating Style Transfer for Text](https://aclanthology.org/N19-1049/)
   - Evaluates style strength, content preservation, and naturalness separately and reports tradeoffs among them.
   - Possible use: prevent the voice gate from collapsing into one subjective score. A stronger rewrite can sound more stylized while becoming less faithful or less natural.
   - Operator takeaway: pending.

18. [Google Search Central — Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap) and [canonical URL guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
   - Treats sitemaps as discovery hints, recommends canonical URLs, and documents sitemap submission and inspection rather than assuming deployment guarantees discovery.
   - Possible use: add canonical URL, sitemap/feed update, and rendered-page inspection to the live gate.
   - Operator takeaway: pending.

19. [RFC 9110 — HTTP Semantics, Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)
   - Defines idempotence as repeated identical requests having the same intended effect and warns against automatically retrying non-idempotent requests without additional guarantees.
   - Possible use: require rerun-safe publication operations so a timeout cannot create duplicate posts, cards, or notifications.
   - Operator takeaway: pending.

20. [GitHub Docs — Deploying with GitHub Actions](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
   - Documents deployment environments, protection rules, and concurrency controls that can limit production to one deployment and withhold protected actions until gates pass.
   - Possible use: translate the abstract deployment gate into a practical control for the project's GitHub Pages stack.
   - Operator takeaway: pending.

21. [Salemi et al. — ExPerT: Effective and Explainable Evaluation of Personalized Long-Form Text Generation](https://aclanthology.org/2025.findings-acl.900/)
   - Frames personalized long-form evaluation as difficult because the originating user is the reliable judge of their own preferences; evaluates content and writing-style alignment separately and emphasizes explainable evidence.
   - Possible use: keep the author inside the voice-calibration loop and require critiques to point to passages rather than return an unexplained score.
   - Caution: the paper proposes an automated evaluator; it does not prove that the evaluator should replace the author.

22. [Alhafni et al. — Personalized Text Generation with Fine-Grained Linguistic Control](https://aclanthology.org/2024.personalize-1.8/)
   - Notes that much controllable-generation work relies on coarse attributes such as formality, domain, or sentiment and studies finer lexical and syntactic controls.
   - Possible use: explain why a voice profile needs recurring moves, sentence behavior, word choices, and examples—not only labels such as “warm” or “authoritative.”

23. [Shi et al. — Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge](https://arxiv.org/abs/2406.07791)
   - Finds systematic position bias across LLM judges and tasks.
   - Possible use: warn that an AI critic is a fallible instrument. Pairwise voice comparisons should swap order, demand passage-level reasons, and defer disputed preferences to the author.

24. [Mysore et al. — Pearl: Personalizing Large Language Model Writing Assistants with Generation-Calibrated Retrievers](https://aclanthology.org/2024.customnlp4u-1.16/)
   - Treats selection of relevant user-authored documents as part of personalization rather than assuming every historic sample helps every generation.
   - Possible use: select examples by article type and desired behavior instead of feeding the entire archive into every run.

## Current-project inspection

- The site stores articles as Markdown and renders them through a shared client-side `article.html?post=...` viewer.
- The blog hub and homepage links are separate HTML surfaces that currently require explicit updates for standalone posts.
- The public repository exposes GitHub's generated `pages-build-deployment` workflow; recent deployment history confirms that pushes to the publication branch can trigger the Pages build/deploy path.
- The earlier 31 Days experiment automated scheduled visibility in client-side JavaScript after articles had already been generated and committed. That solved release timing, not the entire idea-to-live-link workflow.
- A non-JavaScript page read of the live article route returned the viewer shell without the Markdown body. This does not prove Google fails to index it—Google documents a rendering phase—but it demonstrates why the automation needs both browser-rendered and crawler/search-oriented verification.
- The live article response currently supplies a generic `Article | Josiah Hunter` title and depends on a client-side fetch to obtain the post body. The inspected response did not contain a post-specific canonical URL, social metadata, Article/BlogPosting JSON-LD, or publication dates.
- The repository and common live endpoints currently expose no sitemap or RSS/Atom feed. The common `robots.txt` endpoint also returns 404, which is not itself proof of a crawl problem; the relevant gap is that the workflow does not yet verify or update a chosen discovery surface.
- The project already contains the beginnings of iterative voice infrastructure: a style anchor, reference articles, a critic pass, a final preservation-focused prose pass, and a retrospective stating that the spec was revised repeatedly during the 31 Days experiment.
- The project's voice controls evolved in layers: a default anchor removed an initial blocker, a later article was explicitly logged as receiving a research pass plus voice refinement, and the current work adds a final naturalization gate with a no-drift contract. The history supports teaching voice as a versioned subsystem rather than a finished prompt.
- The default style anchor's illustrative passages contain precise example claims that are not sources for real publication. A robust system must distinguish instructional examples from evidence eligible to enter an article.

## Cross-source synthesis — working hypotheses

### Two linked loops

1. **Editorial loop:** capture seed → establish intent → research/brief → draft → critique → voice revision → evidence/voice regression checks.
2. **Publication loop:** package article and metadata → validate links/schema/build → deploy through a protected environment → verify rendered page, metadata, discoverability, and returned URL.

The handoff should occur only after the editorial candidate is immutable enough that packaging and deployment cannot silently change its meaning or voice.

### A portable gate model

- **Intent gate:** purpose, reader, scope, and owner-controlled position are explicit.
- **Evidence gate:** material claims are supported, qualified, or removed.
- **Voice gate:** the draft satisfies a versioned voice profile and preservation contract across representative test cases; uncertain results escalate for human calibration.
- **Package gate:** slug, metadata, article body, links, navigation/card changes, and structured data agree.
- **Deployment gate:** only the intended artifact and site surfaces can reach production; branch/environment rules enforce the chosen autonomy boundary.
- **Live gate:** the expected URL returns, the article renders, links resolve, metadata is present, crawler-facing output is inspectable, and the verified link is recorded.

### Stages are not gates

The BPMN and state-machine sources support a useful teaching distinction:

- A **stage** performs work and must emit an artifact or an observable state change.
- A **gate** evaluates named conditions and selects the next transition.
- A **retry policy** repeats only failures known to be transient and safe to repeat.
- A **repair loop** returns an inadequate artifact to a specific prior stage with feedback.
- An **escalation** transfers the decision to a named human when attempts are exhausted or judgment is owner-controlled.
- A **terminal state** records either a verified outcome or an explicit failure; it must not leave the run looking merely "in progress."

This turns the workflow from a checklist into an executable contract. Each transition needs an `on_pass`, `on_fail`, maximum-attempt rule, and artifact reference. Side-effecting steps—publishing, adding navigation entries, sending announcements—also need a stable run/article identifier or another idempotency mechanism before automatic retry is safe.

### Internal state versus platform state

The automation should own a small internal lifecycle such as `captured`, `intent_confirmed`, `editorially_ready`, `packaged`, `deployed`, `live_verified`, `failed`, and `needs_human`. An adapter can then map those states to a target stack:

- a Markdown/Git site maps them to files, commits, build artifacts, environments, and URLs
- WordPress maps the terminal portion to post fields and statuses such as `draft`, `pending`, `future`, or `publish`
- another CMS can supply a different adapter without changing evidence or voice gates

The external CMS status is therefore an output of the workflow, not the workflow's source of truth.

### Definition of publication

For this article, the strongest candidate definition is not "the deploy command succeeded." Publication is a bundle of observable outcomes:

1. the intended revision is deployed once
2. the canonical public URL returns successfully
3. a normal browser renders the expected title and body
4. metadata, structured data, canonical URL, and dates agree with the article record
5. internal discovery surfaces such as the blog index and navigation point to it
6. external discovery surfaces such as a sitemap or feed are updated where the stack uses them
7. the run stores the deployed revision, verification evidence, and returned URL

Search indexing is asynchronous and cannot be truthfully guaranteed by the workflow. The automatable promise is that the page is crawlable, represented consistently, submitted through the site's chosen discovery mechanism, and inspectable.

### Voice as an iterative system

The combined evidence suggests that examples are useful but insufficient for nuanced blog voice. This is an inference across the Anthropic guidance, the EMNLP study, the Nielsen Norman framework, and the project's own history.

A stronger loop would version five things together:

- positive examples selected for different article types
- explicit voice dimensions and topic-dependent tone ranges
- anti-patterns and anti-tone words
- a preservation contract preventing fact, meaning, citation, code, and formatting drift
- a small evaluation set comparing drafts before and after each voice-control change

The loop is then exemplar → draft → rubric-based critique → conservative revision → regression check → human calibration when the rubric and the author's judgment disagree.

The voice gate should therefore report at least three results rather than one: **voice fit**, **content preservation**, and **naturalness**. A candidate should fail if any dimension falls below its threshold. That structure protects against two common false successes: a faithful but generic draft, and a highly stylized rewrite that distorts the author's meaning.

The profile itself should be learned iteratively:

1. select a small, diverse set of posts the author genuinely wants to sound like
2. extract tentative traits, dimensions, recurring moves, and anti-patterns
3. generate contrasting samples for several article types
4. have the author rank and annotate them, including why a near miss is wrong
5. revise the profile and save the examples as regression cases
6. repeat until the profile predicts the author's choices on held-out passages

This is "teaching the voice" through evidence and corrections. It is different from asking the model to imitate one post or continuously adding adjectives to a prompt.

### Reconciliation of apparently conflicting voice evidence

Anthropic describes examples as a reliable way to steer format, tone, and structure. Wang et al. find that few-shot examples alone provide limited gains for implicit personal-style imitation, especially in blogs and forums. These findings address different bars:

- examples can make an output more consistent with visible instructions
- that does not mean the output captures the subtle writing identity of a particular person

The Wang study also relies primarily on computational authorship and AI-detection measures and explicitly lacks large-scale human evaluation. It supports the narrow claim that examples alone are insufficient under its test setup. The article's iterative calibration method is a practical inference built from that limitation, Anthropic's evaluator–optimizer pattern, personalized-evaluation research, and this project's own history; it must be labeled as such.

An LLM evaluator can make the loop cheaper, but it cannot own the result. Research on LLM-as-judge position bias reinforces a simple operating rule: require passage-level reasons, reverse the order in pairwise comparisons, and route disagreement to the author.

## Operator direction after first reading pass

- Primary purpose: inform readers how to build their own blog-publication automation.
- Proof style: use this project as the worked example, including the deliberately meta fact that the workflow is producing an article about its own construction.
- Crucial design callouts: stages, gates, and iterative development of a voice unique to the reader's own blog.
- Research status: remain in discovery; the evidence base is not yet sufficient for a candidate intent.

## Operator direction after second research pass

- Present the workflow and schema at the diagram-and-checklist level.
- Keep the explanation human-readable, easy to follow, and deliberately uncomplicated.
- Do not make a copyable YAML/JSON contract or orchestration syntax part of the article's main teaching path.
- Translate the underlying state-machine research into plain-language stages, gates, repair paths, and completion checks.

## Emerging distinctions to test with the operator

- A **workflow definition** describes stages, transitions, gates, retries, and escalation.
- A **run/provenance schema** describes the artifacts, decisions, sources, actors, and status of one article run.
- An **article-content schema** describes what a useful workflow inside the article must teach.
- A **publication schema** describes the finished post's metadata and public representation.

These distinctions are analytical hypotheses. The operator has not confirmed that all four belong in the article.

The second research pass suggests the article can keep the workflow/run schema primary and treat publication metadata as its terminal artifact rather than as a competing definition of “schema.” This remains unconfirmed.

## Provisional minimum schema — research hypothesis

A portable implementation appears to need two versioned documents:

1. **Workflow definition:** stages, stage type, consumed and produced artifacts, executor/owner, gate conditions, `on_pass`, `on_fail`, retry limit, timeout, and escalation target.
2. **Run record:** workflow version, stable run/article ID, raw seed, current state, artifact index, source/provenance references, decision log, voice-profile version, gate results, attempt counts, publication target, deployed revision, canonical URL, and verification timestamps/evidence.

The separation matters. The definition can improve between articles without rewriting the history of older runs, while each run remains auditable against the exact workflow and voice profile that produced it. Publication metadata such as headline, author, dates, image, and canonical URL belongs in the packaged article artifact and is referenced by the run record.

This is not yet the article's promised schema. It is a candidate contract to test with the operator and, later, through an end-to-end trial.

## Unresolved conflicts or cautions

- “Schema” is materially ambiguous in the raw seed.
- The local Brand Pack contains a legacy third-person statement that conflicts with its own second-person guidance and the higher-precedence Style Baseline. If drafting proceeds under the active controls, second-person developer voice wins; the inconsistency remains a workflow-maintenance defect.
- The local runtime specification describes dynamic model discovery and routing as required future behavior, while the installed launcher explicitly does not implement it. Any article must distinguish the working launch mechanism from the intended full system.
- Public prose may describe the design, but it must not expose private local paths, internal gates, run metadata, or unpublished operator notes.

## Decision-forming reading prompt

Second reading response received. The research is now sufficient to propose a candidate intent centered on a simple diagram, practical gates, iterative voice calibration, and verified publication. Brief creation remains blocked until the operator confirms or corrects that intent.
