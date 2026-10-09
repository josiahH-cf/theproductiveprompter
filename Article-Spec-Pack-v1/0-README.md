# Article Workflow

This directory contains the provider-neutral article system for The Productive Prompter.

## Start here

From any shell-capable host:

```text
article-flow
```

This is the complete host-neutral entrypoint. With no arguments, the globally installed command returns the seed question, exact start command, continuation protocol, human-decision boundary, and local-capability requirement as machine-readable JSON. Its Windows and WSL launchers point directly to this one local Git checkout, so there is no copied runtime to update. In a fresh Codex, ChatGPT Work, Claude Code/Cowork, Gemini, or other local-capable session, ask the agent to run `article-flow` and follow the returned protocol. No skill, uploaded prompt, provider-specific adapter, repository working directory, or copied command sequence is required.

The first prompt is intentionally small:

> In one paragraph or less, what feels like it could be a good article? Write it naturally; you do not need to structure or polish it.

The controller preserves that seed verbatim, creates a resumable run, and returns one self-contained task or decision at a time. `article-flow capture "YOUR IDEA"` is the direct capture command. Use `article-flow status RUN_ID`, `article-flow next RUN_ID`, or `article-flow resume RUN_ID` to continue.

## Everyday loop

1. Capture one natural sentence or paragraph; it does not need to be a brief.
2. Let the controller complete research, intent, recipe, drafting, visual planning and rendering, verification, editing, packaging, publication, and exact live checks.
3. Make the one routine human decision at the voice gate: the host shows the three exact passages and native selectable A, B, C options in the console. Free-text feedback can reject the set for regeneration without learning. A plain-text letter prompt is the fallback only when the host has no selection control; a preselected option is never an answer.
4. Selecting a passage automatically continues through editing, verification, build, push, and exact live verification, which returns the `theproductiveprompter.com` article URL. No further routine publication confirmation is needed. `choose-voice` continues by default; use `--no-auto` only for an explicit request to pause after recording the choice.

Ambiguity, exhausted repair windows, missing capability, a publication hold, a merge conflict, or failed live verification still stops explicitly. These are exceptional safety stops, not additional editorial approvals.

Later editorial repairs receive the latest accepted article and preserve its selected voice passage. Visual preparation preserves literal code whitespace and source evidence before facts are locked. An older blocked edit with a proven source/lock conflict can explicitly reopen development; see [editorial recovery](docs/editorial-system.md). Live citation connection failures remain failed checks and receive bounded retries. Once connectivity recovers, `repair RUN_ID G-LIVE-REVISION` can reopen a live-check window when all public revision checks passed and only transient external-link failures remain; it rechecks every public byte and link without republishing or deleting earlier receipts. An exhausted deployment-propagation stop may receive one explicitly authorized check only after the controller observes the exact published bytes. Use `repair RUN_ID G-LIVE-REVISION --finding "ACTUAL AUTHORIZATION AND FINDING"`; the durable allowance cannot be reset by repeating repair. See [settled-deployment recovery](docs/editorial-system.md).

`article-flow list` is the small operational index. It shows the original idea, current state, run directory, and returned live link for every run. The same response identifies the canonical process directory, private captured-material directory, and public `docs/` directory. Windows and WSL keep separate installation and health records but use one private captured-material directory, so either command sees and resumes the same runs. A stopped session is resumed with `article-flow resume RUN_ID`; the idea does not need to be entered again.

## Automatic model-release articles

Run `article-flow model-release update --json` to discover current Codex models and the documented Claude CLI catalog, publish and verify a researched article, then append missing frozen-challenge trials and republish the model cards and linked run pages. Existing responses and evidence are immutable. Repeat the same command after a release; completed trials are skipped. Native thinking levels and Codex verbosity are varied one factor at a time by default; `--matrix factorial` requests their full cross-product where supported.

The author authorized automatic reuse of the approved voice for this campaign. This exception pins the approved profile and records its authorization without inventing a new voice preference. Ordinary articles retain their voice choice. `model-release check`, `preview`, and `status` do not generate responses or publish. A saved publication failure resumes the same revision before new discovery or generation.

## Authority

The machine-readable authority is [`workflow/workflow.json`](workflow/workflow.json). Conflicts resolve in this order:

```text
run overrides > approved article recipe > workflow schema > house policy > examples
```

The generated human view is [`1-Master/Article-Workflow-v2.md`](1-Master/Article-Workflow-v2.md). Older prose specifications remain available as historical or editorial reference, but they do not override the workflow, an approved article recipe, or the house policy.

Diagrams are included if and when useful. Keep `components.diagram` at `auto` unless the operator gives an explicit article-specific requirement. Continuous prose does not rule out diagrams: visuals can follow a unique paragraph as well as a section heading. A justified empty plan produces a hash-bound empty manifest; required visuals must still be present, accessible, and verified. Before visual rendering, `article-flow amend RUN_ID --diagrams auto --reason "Include diagrams when useful"` records a recipe amendment without replacing the seed or prose.

This distinction is deliberate. Narrative person, article length, opening, ending, summary, components, citation mode, and shape belong to the article recipe. There is no universal skeleton, workflow count, grammatical person, word band, citation style, or closing formula.

## What code owns

`scripts/article_flow.py` owns:

- run identity, locking, state transitions, retries, and the append-only audit chain;
- integrity checks and a SHA-256 release manifest;
- complete provider-neutral task packets;
- hard gates, artifact hashes, claim/evidence checks, and locked-field preservation;
- controller-selected voice anchors and candidate IDs, hashes, bindings, and comparison order;
- deterministic accessible SVG rendering from a bounded visual plan;
- package generation, a publication dry run, scoped approval, exact deployment, and live-revision verification;
- credential preflight, one explicit publication handoff when the active host cannot push, and remote-branch attestation before live verification;
- global Windows/WSL command installation and drift checks;
- evaluation-backed routing when calibrated results exist, with an honest active-host fallback while they do not.

Models work only inside the task packet they receive. They do not advance their own state, certify deterministic checks, choose publication targets, or infer operator-owned decisions.

## Public and private artifacts

The canonical private article is `article.md`. The website publication target renders it to `docs/{slug}.html`, copies hash-bound article visuals, updates the home page, article index, feed, and sitemap, and verifies every expected live byte. Internal task packets, receipts, claim ledgers, and run events remain private.

`package`, `publish --plan`, scoped approval, `publish --execute`, and `verify-live` are separate operations. The brief gate applies the deterministic character and formulaic-phrase checks to the public title and description when they are first written, so display-text problems are normally repaired inside the brief's own bounded window. If one still needs correction later, `amend` changes the public title or description from `EDIT` onward without replaying research or drafting: before packaging it leaves the run where it is, so the gate that asked for the change still runs, and from `PUBLISH_APPROVAL` it returns to `PACKAGE` to rebuild. A bounded article amendment can repair naturalization without replaying research; a changed article must repeat post-edit claim verification and editorial QA before the controller permits another package. If the active host cannot publish, the controller returns one `human_action`; `deployment-attest` accepts the handoff only when the named commit is the current publication-branch head and every planned public file matches. An expired approval is never reused silently: `next` asks the operator whether to run `publish --renew-approval`, and renewal succeeds only when the target, package revision, and hashed plan are unchanged. Smoke and conformance tests cannot publish.

An explicitly delegated revision can use `--unattended-editorial --authorization "ACTUAL AUTHOR INSTRUCTION"`; it records no new human voice preference. Use `article-flow revise COMPLETED_RUN --request-file CORRECTION.md` to replace an existing article at the same URL. Controller 3.2.1 verifies current Git/worktree/live bytes before creation and preserves the exact public first-publication timestamp even when an old package stored only a date. Add `--expected-source-sha256 HASH` to pin a reviewed baseline. For a published page without a usable completed run, use `article-flow revise --published-slug SLUG --expected-source-sha256 HASH --request-file CORRECTION.md`; no historical run is resumed or marked complete. Both paths keep a source snapshot and provenance, preserve exact block quotations, explicitly attributed inline quotations and code, keep card position and give the page a genuine new modified date. The current policy permits banned punctuation only inside unchanged controller-bound verbatim evidence, never arbitrary quotation/code labels or editable summaries. Live deployment propagation is retried on a short bounded schedule; a permanent markup or content failure blocks immediately. See [editorial source and collection contracts](docs/editorial-system.md#verified-published-sources-and-collection-revisions).

## Health commands

```text
article-flow doctor --scope launcher
article-flow doctor --scope authoring
article-flow doctor --scope release
article-flow manifest check --against-worktree
article-flow conformance
```

Launcher health proves only that the command, canonical process root, and shared captured-material root resolve. Authoring health also requires specification integrity and an eligible execution route. Release health additionally requires a clean approved commit, current global commands, the active native host's passing conformance receipt, and publication prerequisites. Run release health from both WSL and native Windows to prove both installations; neither host fabricates the other host's health record.

## Voice and evidence

### What improves between articles

Naturalization applies `10-Final-Prose-Naturalization/Final-Prose-Naturalization-Directive.md` before publication. Current editorial QA receives that directive and the compact run-pinned voice projection, and must ground language, rhetoric, structure, and preservation checks in exact excerpts. Full profile history is historical evidence rather than additional prose instructions. A clean phrase scan is insufficient. A same-model review is recorded as an independence waiver, not an independent judgment.

Explicit voice selections store the preferred paragraph, its alternatives, and their declared dimensions in shared runtime history. Guidance distinguishes selected, shared, and distinctive labels; model-generated labels do not establish the author's reason. `article-flow voice refine COMPLETED_RUN` clarifies older active guidance from its original hash-bound probe without inventing another choice, changing old evidence, or reactivating retired guidance. Future runs snapshot the current profile. Author feedback and held-out comparisons are still needed to establish improvement.

`article-flow models history` includes a descriptive comparison summary. Fallback and mixed-model runs are separated from clean completed assignments; unrated articles remain unrated. Voice choices compare one model's paragraphs, not models. Use matched held-out briefs and the same voice profile, blind and reverse candidate order, measure preservation and naturalness, and record author judgments alongside repairs, time, and tokens. Only human-calibrated stage evaluations may inform promoted routing. Writing rotation remains an exploration policy; promoted evidence helps select eligible fallbacks.

Visual planning compares the proposed layout with an alternative and omission. A sequential loop, parallel review, branch, and trend convey different relationships. `parallel_review` represents shared context, two isolated reviews, reconciliation, implementation, actual-diff audit on the main path, deferral on a side branch, and a retained result. Renderers reject unsupported label counts and text that cannot fit; they cannot silently drop steps or add a generic telemetry caption. Source and capacity checks do not prove visual quality. Editorial QA receives the hash-bound visual plan, manifest and actual rendered SVG inputs, including arrow paths and label positions. Compare their relationships with the article rather than trusting captions. At `EDITORIAL_QA`, `PACKAGE` or `PUBLISH_APPROVAL`, a current editorial run can use `amend RUN_ID --diagrams auto|off --reason "SPECIFIC FINDING"` to reopen `VISUAL_PLAN`. The controller records and supplies that reason, preserves current prose, and renews rendering, claims, editing, display review, QA and packaging before publication. Published articles require a new revision. Capacity and hash checks do not establish truthful relationships or browser appearance. Inspect the rendered diagram at article and narrow-screen widths during the host's visual review; state when only source markup was inspected. A diagram cannot be called optimal from one unchecked template.

The active guide remains provisional: it is grounded in the author's confirmed self-written capstone, with exact evidence, scopes and limitations. [Editorial system](docs/editorial-system.md) describes compact context, development review, description ownership, bounded AI collaboration, learning, maintenance and testing. Ordinary passage choices apply locally and produce pending learning proposals; published-article feedback never automatically clears other guidance or activates a global rule. Human resemblance judgments remain pending until actually supplied. House character and phrase checks are separate mechanical safeguards, not voice scores. See [outside-model handoff](docs/editorial-handoff.md) for drafting and editing.

Every material factual claim must be traceable and fresh enough for its use. Model memory is not a citation source. The final naturalization pass is conservative and fact-locked; a changed number, date, name, citation, URL, code token, quotation, or qualified claim reopens verification.

## Capability boundary

A model can participate when its host can execute the local `article-flow` command, call the optional local MCP tool, or when the controller can invoke it through a configured provider adapter. A remote chat page with no access to this machine cannot invoke the global local command; that is an explicit capability boundary, not a reason to copy the workflow into the remote product.

See `article-flow --help` for the complete command surface.

Contextual review findings follow the field that owns the exact excerpt: manifest captions, alt text and visual titles reopen visual planning; public display fields reopen display review; body prose uses a unique paragraph locator. Older malformed findings can receive an appended locator/owner normalization only from their intact original gate receipt, task packet and source artifacts. The original finding, ER identifier and evidence remain immutable; normalization alone does not resolve the defect. A current field-specific excerpt or explicit visual omission must still resolve it. Historical sources are recovered from verified artifact events after the current index changes. An article-frontmatter finding must be corrected in that current field and agree with the authoritative brief; an already-correct brief alone cannot clear it. Renewed QA reads one current article, claims, display and visual snapshot. Missing, changed or ambiguous original evidence stays unresolved. Pending older QA packets without bound visual inputs are retired and reissued without changing their bytes; committed gate evidence remains authoritative.

Whole-article length validation scopes each author bound to its subject. A referenced challenge's story or notice limit, and a caption, description or summary limit, does not cap the article. Unqualified direct article limits still bind; quoted/code examples remain source data. For a same-URL revision with a controller-owned model-experiment results panel, preserve its exact source-bound markup and both ownership markers once. Publication renders only that narrowly allowlisted block; arbitrary raw HTML remains escaped. Missing, changed or duplicate panels fail preservation rather than relying on a later results updater. No experiment is executed by this rendering repair.

The current article/draft and current visual manifest own later revision work. Historical source articles remain evidence and cannot restore accepted-away prose or omitted diagrams. EDIT, editorial QA and publication reject displayed controller-owned article SVGs that are absent from the current manifest, including an empty manifest. Literal code examples remain examples. A visual omission must survive the finished body and rendered page, not only the plan.

If a late review finds missing reasoning or a whole-development defect after claims were locked, use `amend RUN_ID --reopen-development --reason "SPECIFIC FINDING"` from EDITORIAL_QA, PACKAGE or PUBLISH_APPROVAL in an editorial run. The controller preserves the current article and historical receipts, binds the reason into a fresh DRAFT task, and renews normal development, visual, claim, edit and QA verification. It grants no new author perspective, voice preference, publication approval or experiment authority. Published articles require a new revision; do not weaken naturalization locks to perform content development.

After a late amendment and renewed packaging, publication planning binds the current package, repository revision, target and frozen style policy again. `next` returns the planning command for stale scope; `advance` refreshes it before honoring a hold or issuing automatic policy approval. A direct approval cannot reuse an older package's plan. An expired approval may retry only its own exact partially committed scope; if the repository moved before publication began, renewal returns to fresh planning and approval. The existing author decision and publication policy still govern continuation; refreshed scope does not create a human voice judgment.

Same-URL publication recognizes older unmarked article cards by one canonical title link, using the actual page URL, document base and canonical origin. Inert markup cannot establish ownership. It rejects missing, duplicated or conflicting ownership. The controller updates only the title, summary, date and reading time on populated cards, adds the missing identifier, and preserves thumbnails, categories, card classes, featured state and position. Later revisions retain those details. This compatibility path creates no new article or author preference.
