# Article Flow Trial Feedback Packet

Trial: second full Article Flow cycle ("concrete goals" essay), 2026-08-18 → 2026-08-19 (UTC).
Prepared for: a second-round implementation model with no access to the originating conversation.
Evidence tags: `OBSERVED` (artifacts/receipts/repo/live site), `OPERATOR-CONFIRMED` (explicit operator statement), `INFERENCE` (reasoned, with confidence + falsifier), `NOT OBSERVED`.

How to use this packet: Section F contains the defect inventory (stable IDs), Section J the ordered change set with acceptance criteria, Section K the regression tests. Sections A–E, G–I are the evidence base. Nothing here is implemented; the operator decides what to accept.

---

## A. Run identity

| Field | Value | Tag |
|---|---|---|
| Publication run ID | `AF-20260818T204536Z-the-idea-behind-setting-a-very-concrete-goal-for-3ecf6fc6` (run 3 of 3) | OBSERVED |
| Predecessor runs | `AF-20260818T181926Z-…-9692be95` (run 1: authoring + all human review; final state BLOCKED at CLAIM_VERIFICATION) · `AF-20260818T204320Z-…-8909deda` (run 2: TERMINAL at PUBLISH_APPROVAL, superseded for a metadata defect) | OBSERVED |
| Raw seed (verbatim, 233 bytes, sha256 `6c74125b90c1e419af63263ef78caf268e5f26ab6ca9350237f5c48df17809a7`, byte-identical in all three runs) | `the idea behind setting a very concrete goal for AI machines - what this entails - what is good and bad output. Include falsification evidence from real tests that we perform here and the output into the article as dropdowns as well.` | OBSERVED |
| Title / slug | "The Machine Did Exactly What You Asked" / `the-machine-did-exactly-what-you-asked` | OBSERVED |
| Live URL | https://theproductiveprompter.com/docs/the-machine-did-exactly-what-you-asked.html | OBSERVED (HTTP 200, content verified 2026-08-19 ~08:36Z) |
| Package revision | `ca87bd733a1ac0dc069ad605573a8de2270a6e54963c0e804c7f97cc4e6fb369` | OBSERVED |
| Embedded article revision (sha256 of article.md, embedded as `<meta name="article-flow-revision">`) | `0a597798c121aaffcbdba6d652acfcc15f0919212168dfec53e953b838614adc` — matches recomputed hash | OBSERVED |
| Published commit | `5bf45d373b13aa9912adea20ed1e22bc3c478655` on `main` (author: operator, 2026-08-19T03:27:36-05:00), pushed from the operator's machine. Content byte-identical (git blob comparison, all 7 files) to the controller's unpushed publication commit `6717997` built in the cloud sandbox. | OBSERVED |
| Converter-fix commit (content) | Included in `5bf45d3` (originally authored as `421efdc` in the sandbox clone): `Article-Spec-Pack-v1/scripts/article_flow.py` + rebuilt `manifest.json` | OBSERVED |
| Controller / workflow versions | Runs 2–3: pack **2.0.8** (repo HEAD), workflow 2.0.0. Run 1: detached installed pack **2.0.6**, workflow 2.0.0. Operator's device install pins 2.0.6 (`current.json`: controller 2.0.6, host native-windows, launcher `article-flow.cmd`). | OBSERVED |
| Entry environment | Anthropic Cowork cloud sandbox (Linux container). The `$start-article` adapter (SKILL.md) was discovered on the operator's Windows machine at `~/.agents/skills/start-article/` and its instructions followed, but the controller itself was **manually staged** into the sandbox (tar over the device bridge) because the sandbox is not an installed host. | OBSERVED |
| Models/providers by stage | Every model stage in every run: provider `active-host`, model `active-capable-host` (the session's hosting model). No external provider configured or used. | OBSERVED |
| Routing basis | Active-host fallback, correctly self-reported by the controller at every stage: "evaluation registry is uncalibrated; use the active capable host without claiming it is best". No calibrated evidence existed or was claimed. | OBSERVED |
| Start / package / approval / publish-commit / deploy / live-verify times (UTC) | Run 1 start 2026-08-18T18:19:26Z · run 3 package 20:45:53Z · publish approval 20:46:21Z (`AP-1259ba11d24dd6adcfd11423`, expired 21:16:21Z unused) · sandbox publish commit 20:46:27Z (push denied) · operator push 2026-08-19T08:27:36Z · live verification 2026-08-19T08:35–08:38Z | OBSERVED |
| Elapsed | Seed → approved package: **2h 27m**. Seed → live: **~14h 16m**, dominated by a credential dead-end (F/AF-FEEDBACK-001) and operator availability, not by authoring. | OBSERVED |
| Operator attention | Not precisely recoverable as minutes. Interaction count OBSERVED: 11 structured decision dialogs (setup ×1 with 3 questions, intent, recipe, voice, sources, editorial, push-path ×2, plus 5 audit questions at the end counted separately) and ~7 free-text instructions/interrupts including three repetitions of the publish instruction and multiple "continue" nudges. | OBSERVED |

---

## B. Outcome

- **Overall result: `PARTIAL`.**
- **One-sentence reason:** The canonical pipeline produced a gate-passed, operator-reviewed article and a content-exact live publication on every distribution surface, but it could not complete autonomously — publication required an out-of-band operator push, one verification stage deadlocked and forced a fresh run, and the operator reports the result only partially preserves intent and voice.
- **What was actually proven** (OBSERVED unless noted):
  - A raw seed entered the canonical state machine and exited as a live article at the returned canonical URL, with blog, homepage, feed, and sitemap all updated by controller-built files.
  - The deployed content is exactly the packaged revision: all 7 deployed blobs are git-identical to package `ca87bd73…`, and the live page embeds the article-content hash `0a597798…`.
  - Code-owned gates did real work: they rejected malformed artifacts (schema violations), unverifiable sources, a locked-field change, and a variation-budget violation — five genuine REPAIR outcomes are on receipt.
  - First-party falsification experiments were pre-registered with refutation conditions before execution, executed in-sandbox, and carried verbatim into the article as evidence dropdowns.
- **What was not proven:**
  - Autonomous end-to-end publication (push required operator credentials; controller never reached LIVE_VERIFICATION; no publish/verify receipts exist in any run).
  - Voice/intent fidelity to the operator's satisfaction (OPERATOR-CONFIRMED: "Neither fully" — see C).
  - Repeatability: this is one article, one topic, one model family, one (unplanned) host environment. Run 1's deadlock shows the process does not yet survive its own repair paths on a single-route host.
  - Cross-environment invocation as designed (adapter → installed controller): the controller ran via manual staging, not via any installed host.
  - Update propagation (the 2.0.6 installs remain un-upgraded; the converter fix exists only at repo HEAD).
- **Evidence strength:** Strong for mechanical claims (hash-chained event logs, 63 gate receipts across 3 runs, git blob identity, live fetches). Weak-to-absent for: operator attention time, LIVE_VERIFICATION behavior, any generalization beyond n=1. Important gap: run 1's device-side archive is one rewind behind (its final receipts exist only in the synced tarball and sandbox copy).

---

## C. Operator-confirmed experience

All items below are OPERATOR-CONFIRMED (structured answers 2026-08-19, or quoted mid-run statements). The five audit questions were answered via option selection; quotations are exact.

- **Friction (Q1, multi-select — all three offered frictions selected):** "Repeated gate confirmations", "Publish/push dead end", "Verification/repair detours", plus verbatim free text: **"it felt like there was token max limits or something because I had to 'continue' several times just to keep going"**.
- **Least trust (Q2, all three selected):** "The publish failures", "The verification deadlock", "Gate carry-forwards" (prior approvals re-recorded in reruns on the operator's behalf).
- **Intent and voice (Q3):** **"Neither fully"** — the offered meaning was "meaningful gaps in both intent and voice." Note the tension with the mid-run record: at the editorial gate the operator said the package "generally is ready" pending two named repairs (clichés; rendering). Both statements are recorded as given; do not reconcile them into a stronger claim either way.
- **Attention value (Q4):** Valuable: "voice pick" (the A/B/C passage comparison). Avoidable: "sources-gate ask" (the qualify/omit decision for URL re-verification) and "repeated confirms". The editorial proofread was *not* marked valuable (absence of selection; do not over-read).
- **Reuse (Q5):** **"Yes, after fixes"** — would use the flow again once this run's friction is addressed.
- **Mid-run statements (verbatim):** seed as in §A; at editorial gate: *"The package generally is ready - however - fix the cliche's as a final gate as well as ensure the formatting would render correctly"*; publish instruction (three times, near-verbatim repeats): *"Ensure to commit - push - merge - and publish all in one fell swoop as well, as a starting place"*; skill location: *"it's on my computer - look in .agents or in another place if needed"*; test constraint: *"only sandbox tests - nothing real"*; length: short essay; experiments: both families.
- **What felt easy:** NOT OBSERVED (not explicitly stated by the operator).

---

## D. Stage-by-stage timeline

Times UTC 2026-08-18 unless dated. "Hidden manual work" = actions performed by the hosting model outside any task packet, dependent on conversation context.

| Stage | Expected behavior | Actual behavior | Model or human action | Retry/repair | Time or delay | Evidence |
|---|---|---|---|---|---|---|
| Adapter discovery + host setup | `$start-article` invokes installed controller | Skill found on operator device; controller pack tar-staged into cloud sandbox; launcher hand-written (`ARTICLE_FLOW_HOME`, later `ARTICLE_FLOW_REPO_ROOT`, CA bundle) | Model (hidden manual work — no packet covers "host bootstrap") | — | ~18:10–18:19 | Device grants; `~/.local/bin/article-flow` in sandbox |
| Doctor + start (run 1) | Green authoring scope; seed preserved | Doctor authoring OK (adapter/release scopes failed as expected off-host); seed stored byte-exact | Model | — | 18:19:26 | `g-seed-preserved-1` PASS; seed sha `6c74125b…` |
| RESEARCH_PLAN | Plan with intent-changing unknowns | PASS first try | Model | — | 18:20:43 | `g-research-plan-2` |
| Experiments (inside RESEARCH) | (No packet defines experiments; seed demanded them) | Pre-registration with refutation conditions written *before* runs; E1 optimizer, E2 metric-only live agent, E3 vague/concrete/trapped arms; scored against pre-registered rubric | Model (design + execution); 4 subagents (same model family) | — | 18:23–18:29 | `artifacts/experiments/` (preregistration.md, preregistered_at.txt 18:23:29Z, scoring.md) |
| RESEARCH → ledger | Claim ledger, no memory citations | PASS; 10 claims, 4 external sources fetched via platform tool | Model | — | 18:29:20 | `g-evidence-coverage-3` |
| INTENT_REVIEW | Operator confirms intent | Candidate written; operator confirmed | Human (real decision) | — | escalate 18:30 → PASS 19:06:48 (36 min operator latency) | `g-intent-fidelity-4/5` |
| ARTICLE_RECIPE | Operator confirms form | First submit REPAIR (schema: extra `summary.note`; variation budget "vary two or three macro dimensions"); fixed; operator confirmed | Model repair + human decision | 1 REPAIR (real catch) | 19:07:53 → 19:20:41 | `g-recipe-fit-6/7/8` |
| BRIEF | Code-gated alignment | PASS | Model | — | 19:21:20 | `g-brief-alignment-9` |
| VOICE_PROBE | 2–3 passages, reversed orders, operator picks | 3 candidates; operator picked A ("first-person, dry"); selection recorded with `--selection` | Human (real decision; operator later rated this the valuable intervention) | — | 19:22 → 19:27:13 | `g-voice-probe-10/11`; approved probe has `operator_selection` A |
| DRAFT | Article per recipe | PASS; body 1,200 words trimmed to 1,181 pre-submit (self-imposed margin) | Model | — | 19:29:39 | `g-draft-coverage-12` |
| CLAIM_VERIFICATION (run 1) | Independent recheck incl. URL resolution | 2× REPAIR: `source_resolution` HTTP 0 for all 3 medium-risk URLs — sandbox has no raw egress; controller's `urllib` fetch cannot succeed there by design. Operator chose "qualify"; fetch records stored as run-local evidence artifacts; PASS | Model + human decision (operator later rated this ask avoidable) | 2 REPAIR → route budget consumed (see below) | 19:30:51, 19:32:28 → PASS 19:44:44 | `g-claims-verified-13/14/15`; `artifacts/research-notes/` |
| EDIT / naturalization | Conservative edit, locked fields | 1 REPAIR: locked `markdown_links` — qualification rewording had changed link anchor text; restored exact locked strings while keeping hedged framing; PASS | Model | 1 REPAIR (real catch, but see AF-FEEDBACK-011 conflict) | 19:45:53 → 19:46:31 | `g-naturalization-16/17` |
| POST_EDIT_CLAIM_VERIFICATION | Re-extract + drift check | PASS (with one required wording fix recorded and applied: "within twenty-five words") | Model | — | 19:47:24 | `g-post-edit-claims-18` |
| EDITORIAL_QA | Operator proofreads exact revision | ESCALATE → operator: "generally ready" + 2 repairs (clichés; rendering). REPAIR recorded | Human (real decision) | REPAIR (by design) | 19:48:19 → 19:59:15 | `g-editorial-qa-19/20` |
| Repair cycle (run 1) | Bounded repair | repair_state=DRAFT rewound the run; cliché edits applied; **renderer investigation found the site converter escapes `<details>` → operator's concern confirmed as real defect**; converter patched in repo pack 2.0.8 + manifest rebuilt via `manifest build --from-index`; re-walk hit: `SameFileError` crash at recipe re-gate (worked around with `--artifact`), then CLAIM_VERIFICATION **deadlock**: route exclusion (2 prior failures ≥ threshold) + hard gate refuses manual PASS/TERMINAL + repair_state=RESEARCH replays human gates. Run 1 abandoned BLOCKED. | Model (heavy hidden manual work) + human gate re-passes recorded as carried approvals | Multiple; ends in dead end | 20:02–20:43 | receipts 21–27; escalation event; fix commit 421efdc 20:41:41 |
| Fresh run 2 (pack 2.0.8) | n/a (recovery strategy) | Full state walk with carried artifacts (run_ids rewritten; experiments copied); all stages PASS; **packaged, then killed**: `meta description` still contained pre-repair cliché ("not a magic spell") — brief description is outside every editorial/naturalization gate | Model; TERMINAL recorded at publish-approval gate | 2.0.8 requires `next` dispatch before submit (behavior skew vs 2.0.6, discovered by error) | 20:43:20 → TERMINAL 20:45:35 | run 2 receipts; `g-publish-approval-18` TERMINAL |
| Fresh run 3 | n/a (recovery) | Same walk with corrected brief description; package `ca87bd73…`; all surfaces verified in-build (4 details render, 0 escaped, no cliché on any surface) | Model | — | 20:45:36 → 20:45:53 | run 3 receipts 1–17 |
| PUBLISH_APPROVAL | Operator approves exact target+revision | Plan created; approval recorded citing operator's explicit thrice-given publish instruction | Human-class receipt (recorded via CLI by model citing instruction — see AF-FEEDBACK-005) | — | 20:46:13 → 20:46:21 | `AP-1259ba11d24dd6adcfd11423`; `g-publish-approval-18` PASS |
| PUBLISH | Commit + push + receipt | **Commit created (6717997), push denied** — git proxy: repo "not in this session's authorized repository set"; **no event or receipt recorded for the attempt**; retry blocked by controller's own HEAD-drift guard | Model | Dead end | 20:46:27; polled ~40 min total across the evening | proxy 403 output; events end at seq 99 (20:46:21) |
| Publish unblock attempts | (none defined by workflow) | Session-grant path: **does not exist in Cowork UI — known open bug** (anthropics/claude-code#76248). Device VM: no network by design. Terminal via computer-use: click-only tier, typing prohibited. Browser file-upload to GitHub: denied by platform safety classifier. Files written to operator's local repo + exact 3-line command block delivered | Model (all hidden manual work) + operator decision dialogs ×2 | 4 distinct dead ends | 2026-08-18 21:00 → 2026-08-19 01:15 | proxy messages; computer_resolve_access `restrictedTierNote`; classifier denial; bug 76248 |
| Deployment | Controller pushes | **Operator pushed from own machine**: commit `5bf45d3` 2026-08-19T08:27:36Z, content byte-identical to controller's package commit | Human (out-of-band) | — | ~7h later (operator availability) | `git ls-remote`; blob-identity check on all 7 files |
| LIVE_VERIFICATION | Controller verifies exact revision | **Never ran in-controller** (run 3 still at PUBLISH; no publish receipt to advance on). Equivalent verification performed out-of-band: live page + blog + homepage + feed + sitemap fetched; embedded revision meta `0a597798…` == sha256(article.md); repo blobs == package | Model (out-of-band, sanctioned fetch tool) | — | 2026-08-19 08:35–08:38Z | live fetch results; hash match |

---

## E. What worked and should be preserved

1. **Seed preservation by value.** Byte-identical seed (sha `6c74125b…`) across three runs; `G-SEED-PRESERVED` receipt at each start. Why it matters: the end state depends on raw-idea fidelity. Evidence: §A. Appears general (mechanism is content-addressed, not article-specific).
2. **Code gates that reject real defects.** Five genuine REPAIR outcomes: recipe schema + variation-budget lint; 2× source-resolution failures; locked-field violation on link anchors. Each pointed at a concrete, fixable artifact defect and each fix passed on resubmit. Evidence: receipts `g-recipe-fit-6`, `g-claims-verified-13/14`, `g-naturalization-16`. General by design; this trial exercised them for real.
3. **Voice probe with forced comparison orders.** The one intervention the operator explicitly rated valuable (Q4). The controller's `order_reversal` check and required `--selection`/`--feedback` made the decision cheap and recorded. Evidence: voice-probe submission + `g-voice-probe-11`. General.
4. **Pre-registered falsification experiments as first-party evidence.** Refutation conditions written before execution (timestamped 18:23:29Z), one claim genuinely refuted (E2), scores fixed by a rubric authored before arms ran, all verbatim in run artifacts and in the published dropdowns. Why it matters: the seed demanded falsification, and pre-registration is what made the "one test failed" narrative honest. Evidence: `artifacts/experiments/`. **Supported by this trial only** — no packet/schema mandates pre-registration; it was improvised (see F/AF-FEEDBACK-015 adjacent).
5. **Claim ledger `allowed_wording` as a drafting contract.** The qualify decision translated mechanically into hedged reported-speech phrasing, and the post-edit ledger caught a precision drift ("under" vs "within twenty-five words"). Evidence: verified ledger CL-06 note; post-edit receipts. General.
6. **Hash-chained event log + content-addressed revisioning.** `event_hash`/`previous_event_hash` chain; package revision + embedded article hash allowed *exact-revision* deployment proof even though deployment happened out-of-band. Evidence: §A hash match. General — this is the property that rescued auditability when the happy path broke.
7. **Deterministic multi-surface packaging.** One package call produced article page (correct head: title, description, canonical, OG, JSON-LD, revision meta, read time), blog card, homepage card, feed and sitemap entries — all verified live with zero manual surface edits. Evidence: §I. General.
8. **Manifest/protected-paths integrity flow.** The converter patch was impossible to sneak in: integrity failed until `manifest build --from-index` was run over reviewed, staged changes. Evidence: `2.0.6 manifest check` hash-mismatch output; repo commit 421efdc includes rebuilt manifest. General.
9. **HEAD-drift guard on publish (concept).** It correctly detected that the repository state no longer matched the plan. Its *interaction* with the failed push is a defect (F-002), but the guard itself protected against publishing unplanned state. Preserve the check; fix the recovery.

---

## F. Problems and friction

> Deduplicated by root cause. "Systemic" = will recur on other articles/hosts; "article-specific" = tied to this topic/content.

### AF-FEEDBACK-001 — Publication assumes the active host holds push credentials
- **P1** · reliability/portability · Stage: PUBLISH
- Symptom: `publish --execute --commit --push` failed: git proxy refused credential injection ("not in this session's authorized repository set"); the advertised remedy (add repo to session sources) **does not exist in the Cowork UI** — documented open platform bug (anthropics/claude-code#76248). Seed→live time inflated from ~2.5h to ~14h; operator ultimately pushed by hand.
- Evidence: proxy 403 output (~12 attempts over 12h); bug report content; operator commit `5bf45d3`.
- Expected: publication completes, or the workflow degrades gracefully at a defined escalation.
- Actual: mid-stage failure with no controller-recorded trace, followed by ad-hoc improvisation.
- Operator impact: highest-friction item; selected both "publish/push dead end" (Q1) and "the publish failures" (Q2).
- Repro: run publish from any host whose git egress lacks write credentials for the publication repo.
- Root-cause hypothesis (confidence high): PUBLISH is specified as an in-process side effect with no capability preflight and no credential-handoff escalation path. Disproved if: a controller mode already exists that detects push incapacity pre-commit and emits an operator handoff artifact (none found in 2.0.6/2.0.8 source).
- Systemic. **Smallest general correction:** at PUBLISH_APPROVAL entry, preflight `git push --dry-run`; on failure, emit a first-class **publication-handoff artifact** (exact file list, commit message, commands, expected post-push state) and a new state `AWAITING_OPERATOR_DEPLOY` that accepts a post-hoc deployment proof (remote revision/content hash) to resume into LIVE_VERIFICATION.
- Files: `article_flow.py` (publish plan/execute, workflow.json states), `workflow/workflow.json`.
- Regression test: K-1. Operator decision: yes (new state + handoff semantics).

### AF-FEEDBACK-002 — `publish --execute` is non-atomic and non-resumable
- **P1** · integrity/traceability · Stage: PUBLISH
- Symptom: the failed execute **created commit `6717997` but wrote no event and no receipt** (event log ends 20:46:21Z; commit timestamp 20:46:27Z); the retry then failed the controller's own HEAD-drift guard because HEAD now pointed at the very commit the controller had created (`planned 421efdc / actual 6717997`).
- Evidence: events.jsonl seq 99 final; second-execute error JSON; git log.
- Expected: side effects recorded before/after; failure leaves a resumable, self-recognizing state.
- Actual: untracked side effect + self-inflicted deadlock.
- Operator impact: silent dead end requiring conversation-context forensics.
- Repro: make `git push` fail after commit succeeds in `publish --execute`.
- Root cause (confidence high): execute sequences commit→push→receipt with no write-ahead event and a drift guard comparing commit IDs rather than tree content. Disproved if: an event for the publish attempt exists somewhere else (none found).
- Systemic. **Smallest correction:** write a `PUBLISH_ATTEMPT` event before side effects; on push failure record `PUBLISH_INCOMPLETE` with the created commit id; drift guard should accept HEAD if `git rev-parse HEAD^{tree}` matches the planned tree or HEAD's parent is the planned HEAD and the commit message embeds the plan's package revision.
- Files: `article_flow.py` (`command_publish` execute path). Regression: K-2. Operator decision: no.

### AF-FEEDBACK-003 — Verification-independence rule deadlocks single-route hosts
- **P1** · availability/repair design · Stage: CLAIM_VERIFICATION
- Symptom: two REPAIR outcomes (caused by F-004, an environmental issue) permanently excluded the only route (`failures ≥ max_attempts-1`); hard gate `G-CLAIMS-VERIFIED` refuses operator PASS **and** operator TERMINAL ("code-owned and cannot be manually passed"); declared repair_state=RESEARCH forces replay of three already-passed human gates; escalation text offers "operator-approved exception" but no such mechanism exists. Run 1 is permanently BLOCKED; recovery required starting a fresh run and hand-carrying artifacts.
- Evidence: run 1 `route_failures {CLAIM_VERIFICATION: 2}`, status BLOCKED; gate refusal message; receipts 22–27 (rewind); run 1 unfinishable even for archival closure.
- Operator impact: "verification deadlock" selected as a least-trust moment (Q2); "repeated confirms" as avoidable friction (Q4).
- Repro: any host with exactly one configured route + two rejected verification submissions (for any reason), then attempt to proceed.
- Root cause (confidence high): route-exclusion policy presumes ≥2 routes; failure counters never decay (not even on subsequent PASS — receipt 15 passed and the counter still read 2); no single-route degradation policy; hard-gate override surface is all-or-nothing. Disproved if: a providers.json with a second working route was reasonably available in the intended environments (operator decision needed on what "intended environments" guarantee).
- Systemic. **Smallest correction:** (a) clear/decay a route's failure count when the same stage later passes; (b) if after exclusion zero routes remain, degrade to "same-route re-verification with independence-waiver disclosure recorded in the receipt" instead of BLOCKED; (c) allow operator TERMINAL on any run regardless of gate class (closing a run is not passing a gate).
- Files: `article_flow.py` (route_candidates caller ~line 1053; command_gate outcome policy). Regression: K-3. Operator decision: yes for (b) waiver semantics.

### AF-FEEDBACK-004 — Source re-verification cannot run on sanctioned-fetch-only hosts
- **P1** · portability/evidence policy · Stage: CLAIM_VERIFICATION / POST_EDIT / (future) LIVE_VERIFICATION
- Symptom: controller `urllib` fetch returned HTTP 0 for every external URL (sandbox reserves raw egress; only the platform's fetch tools may retrieve web content). Three verified-by-platform-fetch claims were forced into `qualify` with hedged wording, and the operator was interrupted for a decision the environment forced (rated avoidable, Q4).
- Evidence: `g-claims-verified-13/14` findings ("HTTP 0"); research-notes artifacts recording the successful platform fetches with quotes and timestamps.
- Root cause (confidence high): single hard-coded fetch implementation; status 0 (cannot attempt) conflated with resolution failure (404/410). Disproved if: the intended production hosts always permit raw egress — then this is Cowork-specific and drops to P2.
- Systemic (also affects verify-live). **Smallest correction:** pluggable fetch adapter: controller accepts host-mediated fetch evidence (URL, timestamp, method, excerpt hash) recorded as a distinct verification method in the ledger; treat transport-impossible (0) as "defer to adapter or record environment limitation," never as source failure.
- Files: `article_flow.py` (`fetch_url` call sites 1465, verify-live), claim-ledger schema (verification_method field). Regression: K-4. Operator decision: yes (evidence-policy change).

### AF-FEEDBACK-005 — Human-gate receipts cannot prove a human acted
- **P1** · governance/trust · Stage: all review gates + publish approval
- Symptom: `gate` CLI records `{"type":"human","identity":"operator"}` for whoever invokes it. In runs 2–3 (and the run 1 rewind) the hosting model re-recorded prior operator approvals, citing the operator's explicit instructions in `--feedback`; the event log marks these `actor: operator/human` indistinguishably from keyboard-typed decisions. The operator listed "gate carry-forwards" among least-trust moments (Q2).
- Evidence: run 3 events 95–99 (`actor: operator` on approval recorded via model-issued CLI); receipts' feedback text is the only disambiguator.
- Root cause (confidence high): identity is asserted by the caller, not attested. Disproved if: receipts contain a channel/attestation field I missed (none in schema).
- Systemic. **Smallest correction:** add `invocation_channel` (typed-by-operator vs agent-on-instruction) + optional operator nonce for human-class gates; add a first-class **carried-approval receipt** type that must reference the original receipt id + artifact hash equality proof — making legitimate carry-forwards auditable instead of impersonation-shaped.
- Files: gate-receipt schema, `command_gate`. Regression: K-5. Operator decision: yes (attestation UX).

### AF-FEEDBACK-006 — Public metadata bypasses every prose gate
- **P1** · quality/gate coverage · Stage: BRIEF → PACKAGE
- Symptom: the operator-ordered cliché pass was applied to the article, but `brief.description` ("…not a magic spell…") flowed unexamined into the page meta description, OG description, blog/homepage cards, and feed — caught only by ad-hoc inspection after run 2 was fully packaged; correcting one sentence required terminating run 2 and re-walking a third run end-to-end (~2 min mechanical, but 18 more receipts and two more carried human gates).
- Evidence: run 2 package metadata description vs run 3; `g-publish-approval-18` TERMINAL (run 2) with recorded reason.
- Root cause (confidence high): naturalization and editorial gates take the *article* as their input surface; brief fields are upstream-locked and no amend path exists short of a rewind through human gates. Disproved if: a brief-amendment command exists (none found).
- Systemic. **Smallest correction:** (a) extend the naturalization/cliché lint to all publish-surface strings (title, description, dek, card summary, feed text) as part of G-PACKAGE-INTEGRITY; (b) add a bounded `amend --field brief.description` repair that re-runs only the gates whose inputs changed (publish surfaces), leaving intact approvals referenced by hash.
- Files: `article_flow.py` (package_metadata, naturalization applier), workflow.json. Regression: K-6. Operator decision: (b) yes.

### AF-FEEDBACK-007 — Repair states are coarse rewinds that replay settled human decisions
- **P2** · friction · Stage: repair transitions (EDITORIAL_QA→DRAFT, CLAIM_VERIFICATION→RESEARCH)
- Symptom: a two-item editorial repair rewound to DRAFT and re-ran claim verification + naturalization + post-edit + QA; the claims repair path points at RESEARCH, upstream of three human gates. Combined with F-003 this turned a wording fix into a fresh-run strategy. Operator: "repeated confirms" avoidable (Q4, Q1).
- Root cause (confidence medium-high): repair_state is a single static pointer per state; no dependency tracking between changed artifacts and gates. Disproved if: receipts show rewound stages doing different work on unchanged inputs (they did not — diffs were prose-only).
- Systemic. **Smallest correction:** repairs re-open only stages whose *input hashes changed*; unchanged human-gated artifacts auto-carry via the F-005 carried-approval receipt.
- Files: workflow.json repair_state semantics; transition logic. Regression: K-7. Operator decision: yes (semantics).

### AF-FEEDBACK-008 — `SameFileError` crash when re-approving an unchanged review artifact
- **P2** · bug · Stage: any review gate after rewind
- Symptom: `shutil.copy2(candidate, approved)` raised `SameFileError` (traceback to `article_flow.py:1868`) because after a rewind the latest artifact of the review type *is* the approved copy. Worked around with undocumented `--artifact` pointing at the original candidate.
- Root cause (confidence high): artifact index lookup returns approved copies; copy not guarded. Systemic.
- **Correction:** skip copy when `candidate.samefile(approved)`; prefer non-approved candidates in `artifact_path` for review types. Files: `command_gate`. Regression: K-8. Operator decision: no.

### AF-FEEDBACK-009 — Version skew between installed pack (2.0.6) and repo pack (2.0.8) is unmanaged
- **P2** · operability · Stage: host bootstrap, everything after
- Symptoms observed: (a) 2.0.8 rejects submissions without a prior `next` dispatch ("No dispatched task packet exists") — silent behavioral change vs 2.0.6 discovered by error; (b) 2.0.6's protected-paths demand `repo:.github/copilot-instructions.md`, deleted at repo HEAD, making 2.0.6's manifest un-rebuildable against the current repo and its `release_ready` scope permanently red; (c) the device adapter pins 2.0.6 while all publication tooling ran at 2.0.8; (d) the converter fix exists at HEAD but no installed host has it.
- Evidence: submit error string; `manifest build` failure "Protected file is missing from index: .gitattributes"/copilot-instructions missing_file finding; `current.json` (2.0.6) vs repo `CONTROLLER_VERSION = "2.0.8"`.
- Root cause (confidence high): no release/upgrade discipline between repo HEAD and installed releases. Systemic.
- **Correction:** cut release 2.0.9 (or 2.0.8 release artifacts) containing the converter fix; `article-flow install` upgrade run on the Windows host; controller version-compatibility check at run load (warn when run created by other minor version). Regression: K-9. Operator decision: yes (when to upgrade installs).

### AF-FEEDBACK-010 — Site converter escaped the article's evidence dropdowns *(fixed this trial; keep the fix, add tests)*
- **P2** (was P1 pre-fix) · rendering · Stage: PACKAGE
- Symptom: `markdown_to_html` HTML-escaped every raw HTML line; the seed-required `<details>` dropdowns would have rendered as literal `<details>` text on the live site (8 visible junk lines). Found by simulating the package converter during the operator's "ensure formatting renders" repair; **fix shipped**: narrow allowlist (bare `<details>`, `</details>`, single-line `<summary>` with inline-rendered content; adversarial probe confirms `<script>`/attributed tags still escape). Live page verified: 4 working dropdowns, zero escaped wrappers.
- Evidence: pre-fix simulation (4×`&lt;details&gt;` + 4×`&lt;summary&gt;`); commit `421efdc` (now in `5bf45d3`); live fetch.
- Residual root cause (confidence high): converter has **zero unit tests** (test suite has no `markdown_to_html` coverage — grep verified), so regressions are invisible.
- **Correction:** converter unit tests incl. allowlist, adversarial raw-HTML, tables (unsupported — document), entities. Regression: K-10. Operator decision: no.

### AF-FEEDBACK-011 — Locked-fields freeze link anchor text that claim qualification must change
- **P2** · design tension · Stage: EDIT
- Symptom: qualification (from the sources decision) required reported-speech rewording, but locked `markdown_links` include anchor text; the naturalization gate rejected the reworded links and the resolution was hand-crafting hedges *around* the exact original anchor strings.
- Evidence: `g-naturalization-16` finding "Naturalization changed locked markdown_links"; final article's contorted-but-compliant phrasing.
- Root cause (confidence medium): locks are computed from the draft before qualification outcomes and key on full link strings. Disproved if: locks are meant to be regenerated after CLAIM_VERIFICATION (no such step exists).
- Systemic. **Correction:** lock URLs (and quoted strings) but not anchor text; or regenerate locks from the post-verification draft with ledger dispositions applied. Regression: K-11. Operator decision: no.

### AF-FEEDBACK-012 — Session/harness pauses required repeated operator "continue" nudges
- **P3** · environment hypothesis · Stage: throughout
- Symptom (OPERATOR-CONFIRMED, verbatim): "it felt like there was token max limits or something because I had to 'continue' several times just to keep going." OBSERVED: multiple turn interruptions and resumes in the hosting environment; none originate in the controller.
- Root cause hypothesis (confidence medium): hosting-harness turn boundaries/interrupts, not Article Flow. Disproved if: the same pauses occur when driven by a thin non-interactive host loop.
- Systemic to *this host class*. **Correction candidates need another trial:** batch controller stages between human gates into single host turns; or run authoring stages through a non-interactive runner. Operator decision: yes (which environments are "the agreed environments").

### AF-FEEDBACK-013 — Controller/git operations unsafe on Cowork-mounted device folders
- **P2** · environment safety · Stage: host bootstrap/publication on device mounts
- Symptom: any git command in the mounted repo leaves an undeletable `.git/index.lock` ("Operation not permitted" on unlink; deletes are blocked on the mount). Two stale locks quarantined to `_to_delete/`; tar-into-self also occurred once. Would have corrupted an operator's ability to use git locally if unnoticed.
- Evidence: device_bash outputs; `_to_delete/git-index.lock{,2}`.
- Root cause (confidence high): mount forbids unlink; git requires it. Systemic for this host class. **Correction:** controller preflight: refuse repo roots on no-unlink filesystems with a clear message; host guidance: stage to a writable clone instead. Regression: K-12. Operator decision: no.

### AF-FEEDBACK-014 — Gates passed, operator still reports intent/voice gaps
- **P3** · quality hypothesis · Stage: VOICE_PROBE/EDITORIAL_QA vs outcome
- Symptom: all voice/editorial gates passed with a real proofread and named repairs applied, yet the post-publication answer is "Neither fully" (Q3: meaningful gaps in both intent and voice). No specific gap was named; the mid-run record contains no rejected passage other than the two repairs.
- Root cause hypothesis (confidence low-medium): one 3-candidate probe on a single passage + one proofread under-samples voice; the voice profile is explicitly `provisional` with a required held-out test (`held-out-different-form-001`, status `not_run`). Alternative hypothesis: dissatisfaction attaches to the *process outcome* (deadlocks, delay) and colors the retrospective judgment. Disproved by: operator marking up the live article's specific off-voice/off-intent passages.
- **Correction needs operator input first:** collect passage-level annotations; run the profile's own held-out calibration before the next article. Operator decision: yes.

### AF-FEEDBACK-015 — Evidence carry between runs is manual and unspecified
- **P2** · repair design · Stage: recovery/fresh runs
- Symptom: fresh runs required hand-copying `artifacts/experiments/` + `research-notes/` and rewriting `run_id` in nine artifacts; ledger local-id evidence would dangle otherwise. Nothing in the controller supports run supersession.
- Evidence: runs 2–3 artifact trees (copies); submissions with rewritten run_ids.
- Systemic. **Correction:** `article-flow start --supersede OLD_RUN` carrying artifacts + recording lineage (pairs with F-003/F-007; a working single-run repair path shrinks this need).
- Regression: K-13. Operator decision: no.

### AF-FEEDBACK-016 — LIVE_VERIFICATION never exercised; controller cannot accept out-of-band deployment
- **P2** · gap · Stage: LIVE_VERIFICATION
- Symptom: run 3 is frozen at PUBLISH despite the site being verifiably live with exactly the packaged revision; there is no way to feed the controller the deployment proof (remote commit, blob identity, live fetch evidence) to let it complete its own final gate and mark COMPLETE.
- Evidence: run 3 `state: PUBLISH`; live verification performed only out-of-band (§I).
- Root cause: same family as F-001/F-002 (publication modeled as in-process only). **Correction:** `article-flow deployment attest RUN --remote-rev SHA` verifying tree/blob identity + then permitting verify-live; verify-live's fetch needs the F-004 adapter. Regression: K-14. Operator decision: yes (attestation acceptable as deployment proof?).

---

## G. Intent and article-quality assessment

| Dimension | Mechanical evidence | Editorial judgment |
|---|---|---|
| Seed preservation | OBSERVED PASS — byte-identical seed in all runs; every seed component traceable in the live article (concrete-goal thesis; entails; good/bad output; falsification tests; dropdowns). | The seed's odd grammar was preserved, not "fixed" — correct behavior. |
| Intent fidelity | OBSERVED: intent candidate explicitly separated `explicit_seed_content` from `assumptions` and `remaining_unknowns`; operator confirmed it at a real gate. | OPERATOR-CONFIRMED tension: post-hoc "Neither fully" (Q3) vs mid-run confirmation and "generally ready." Unresolved; needs passage-level feedback (F-014). Do not score this PASS. |
| Research fitness | OBSERVED: 4 external sources, all primary/vendor or provenance-reference, fetched live; freshness horizons recorded; first-party experiments designed to the seed's falsification demand; no memory citations (gate-enforced). | Depth matched a short essay; the Goodhart-misattribution trap was explicitly managed. Adapted to subject risk, INFERENCE (high confidence): yes — the highest-risk claims got the most machinery. |
| Evidence & citation integrity | OBSERVED: ledger of 13 claims with locators/excerpts; source-resolution enforcement fired; post-draft and post-edit rechecks produced receipts; one wording-precision defect caught and fixed via ledger (`within` vs `under`). Qualification of 3 claims is environment-forced (F-004), disclosed in run artifacts. | Hedged wording on the live page is accurate but slightly stilted where locked anchors constrained it (F-011). |
| Structure / reader-job fit | OBSERVED: recipe (argument, failure-first open, decision-rule end) demonstrably realized in the live article; 3 outline candidates recorded with rejection reasons. | Structure serves the reader job; the E2 refutation as the turn is the piece's best structural decision. |
| Voice fit | OBSERVED: operator chose A from 3 candidates in randomized orders; A's register is maintained (first-person experiments, second-person advice). | OPERATOR-CONFIRMED gap post-hoc (Q3). Voice profile remains `provisional`; its own required held-out test has never run. |
| Length fit | OBSERVED: 1,177 body words vs approved 800–1,200 band (count method recorded: dropdown contents/dek/footer excluded). First draft landed at exactly 1,200 — the band's edge — and was trimmed voluntarily. | Band edge suggests the target exerted pressure; content did not feel padded (INFERENCE, medium). |
| Naturalness / cliché removal | OBSERVED: naturalization directive applied; operator-ordered second pass removed 5 further items (dek formula, 2 idiom headers, "writes itself", "without friction"); metadata cliché caught late (F-006); live surfaces contain zero inventory phrases (grep of built files). | The second human pass caught what the directive-driven pass had judged acceptable — the inventory is a floor, not a ceiling. |
| Meaning preservation in editing | OBSERVED: locked-fields enforcement fired once (and blocked an over-edit); post-edit ledger 13/13 claims re-verified, `post_edit_drift: none`; numbers/quotes/links byte-checked. | No meaning drift found; the one required change tightened precision. |
| Usefulness of final article | NOT OBSERVED (no reader data, no operator statement on usefulness). | — |

---

## H. Control integrity

- **State machine / resume:** Linear machine executed as declared; every transition event-logged with hash chaining. Resume-after-interruption worked *within* a run. **However:** run 1 is unfinishable (F-003), run 3 cannot reach COMPLETE (F-016), and 2.0.8 requires undocumented `next`-before-submit (F-009a). A fresh model could replay runs 2–3 from artifacts alone; it could **not** reconstruct *why* without the receipts' feedback texts (which do carry the reasons — the carried-approval texts cite original receipt IDs and operator instructions).
- **Task-packet self-containment:** Packets carried objective, inputs+hashes, allowed tools, side-effect policy, constraints, stop conditions, escalation question — genuinely sufficient for the authoring stages. **Not covered by any packet:** host bootstrap, experiment methodology, publication credential handling, recovery strategy — all came from conversation context (OBSERVED; this is the main hidden-context dependence).
- **Gate execution:** Genuinely executed, not claimed: 63 receipts across 3 runs; 5 REPAIR outcomes with concrete findings; 2 operator ESCALATE→decision cycles; schema validation rejected real submissions. One gate *crashed* (F-008). Gate coverage gap: publish-surface metadata (F-006).
- **Repair behavior:** Bounded and traceable per attempt (`max_attempts`, declared repair states, receipts), but repair *targets* are coarse (F-007) and one repair chain terminates in an unrecoverable state (F-003).
- **Approval boundaries:** Publication side effects were correctly withheld until `G-PUBLISH-APPROVAL` (plan → approval `AP-1259ba11…` with 30-min TTL → execute). The TTL expired unused during the credential dead-end; no side effect occurred outside approval. The *deployment* ultimately occurred outside the controller entirely (operator push) — sanctioned by the operator's explicit instruction, but invisible to the controller (F-016).
- **Model routing:** Correctly reported active-host fallback everywhere; no false claims of calibrated selection. The verification-independence variant of routing is what deadlocked (F-003).
- **Credential/privacy handling:** No credentials were read, stored, or exposed by the controller or host; push authority was never impersonated — when credentials were absent, the flow stopped (correct) and the operator deployed with their own (F-001 is about *experience*, not a safety breach). Screenshot of the operator's GitHub session was taken during the browser attempt (avatar visible, no secrets); the browser file-upload path was refused by the platform classifier and abandoned.
- **Event/artifact traceability:** Strong: hash-chained events, artifact index with producer routes, receipts embedding input hashes, package embedding content hash. Gap: the failed publish attempt wrote nothing (F-002), and run 1's device-side archive copy is one rewind stale (its complete state exists in the sandbox and in the synced tarball).
- **Self-certification / hidden context:** The editorial-QA *submission* is authored by the same model that wrote the article (marked `calibration_status: uncalibrated-advisory` — honest), and the carried human-gate receipts were CLI-recorded by the model citing operator instructions (F-005). Both are disclosed in artifacts; neither is independently attested.

---

## I. Publication and distribution proof

Verified 2026-08-19 ~08:32–08:38Z unless noted.

| Check | Status | Evidence |
|---|---|---|
| Package created | PASS | `package/package.json` revision `ca87bd73…`, 20:45:53Z; `G-PACKAGE-INTEGRITY` PASS |
| Publication approved | PASS | `AP-1259ba11d24dd6adcfd11423` (APPROVED 20:46:21Z, TTL 21:16:21Z) + `g-publish-approval-18` PASS. Note: deployment happened after expiry, out-of-band. |
| Repository updated | PASS | `origin/main` = `5bf45d37…`, message "Publish AF-20260818T204536Z … (ca87bd733a1a) + converter details-passthrough fix" |
| Deployment completed | PASS (out-of-band) | Operator push 2026-08-19T08:27:36Z; **not** via controller (`publish` receipt absent) |
| Exact live revision verified | PASS | All 7 deployed blobs git-identical to controller package commit; live page embeds `article-flow-revision` = sha256(article.md) = `0a597798…` (recomputed match). Beyond HTTP 200. |
| Article accessible | PASS | Live fetch: title, dek, byline "By Josiah Hunter•August 18, 2026•8 min read" |
| Canonical URL correct | PASS | `rel=canonical` → `https://theproductiveprompter.com/docs/the-machine-did-exactly-what-you-asked.html`, matches target config pattern and returned link |
| Blog surface updated | PASS | Live blog.html: featured/latest card, corrected description, prior article second |
| Homepage updated | PASS | Live index.html latest-card with title/description/read-time |
| Feed updated | PASS | feed.xml newest entry, correct link + date |
| Sitemap updated | PASS | sitemap.xml contains canonical URL, lastmod 2026-08-18 |
| Returned link correct | PASS | Link returned to operator == canonical URL == live 200 |
| Dropdowns render on live site | PASS | 4 details sections with correct summaries; no literal `<details>` text (the trial's converter fix, verified in production) |
| Indexing | NOT OBSERVED | No search-index claims made or checked; sitemap/feed presence only |
| Cross-environment invocation demonstrated | NOT OBSERVED (as designed) | Adapter discovered on device and honored, but controller ran via manual staging in the sandbox, not from an installed host ($start-article on Codex/Gemini hosts untested this trial) |
| Installation/update propagation demonstrated | FAIL | Device install remains 2.0.6 without the converter fix; no install/upgrade was run; fix exists only at repo HEAD |
| Controller LIVE_VERIFICATION state | NOT OBSERVED | Run 3 frozen at PUBLISH (F-016); verification above performed out-of-band with sanctioned fetch tools |

---

## J. Recommended second-round change set

*Criteria for the implementing model. Recommendations only — the operator decides. Ordered by dependency, then cheapest path to the end state ("raw idea → published link with intervention only at defined escalations").*

### J.1 Required v1 repairs

| Order | Issue IDs | Proposed change | Why this is the root-level fix | Acceptance evidence | Risk | Operator decision needed |
|---|---|---|---|---|---|---|
| 1 | 001, 002, 016 | Publication capability preflight + write-ahead publish events + `AWAITING_OPERATOR_DEPLOY` state with `deployment attest` (tree/blob + revision-meta proof) resuming into LIVE_VERIFICATION | This trial's entire 12-hour tail was publication modeled as "the host can always push"; attestation turns the unavoidable credential boundary into a defined escalation instead of a dead end | K-1, K-2, K-14 pass; a no-credential host run ends with a handoff artifact and, after operator push + attest, a COMPLETE run with publish/verify receipts | Medium (new state) | Yes — approve the new state + attestation semantics |
| 2 | 003 | Single-route degradation: failure-count decay on later PASS; independence-waiver re-verification when zero routes remain; operator TERMINAL allowed on any run | The deadlock is structural on every single-model host; waiver-with-disclosure preserves the independence *record* without pretending a second model exists | K-3 passes; a run with 2 prior verification REPAIRs on one route completes without a fresh run | Low | Yes — waiver policy |
| 3 | 004 | Pluggable fetch adapter + transport-impossible status class; ledger records verification method | Source and live verification both die on sanctioned-fetch hosts; adapters make evidence portable across the agreed environments | K-4; claims verified via adapter carry method metadata instead of forced qualification | Medium (evidence policy) | Yes — accept host-mediated fetch as evidence |
| 4 | 005, 007 | Carried-approval receipt class (references original receipt id + artifact-hash equality) + hash-based repair scoping that auto-carries unchanged human gates | Removes both the impersonation-shaped records and the repeated-confirmation friction with one mechanism | K-5, K-7; a rewind on unchanged artifacts produces zero new human prompts and receipts marked `carried` | Medium | Yes — attestation UX |
| 5 | 006 | Publish-surface lint (title/description/dek/cards/feed) in G-PACKAGE-INTEGRITY + bounded `amend` for brief display fields | The only quality escape this trial reached a package twice; the fix is coverage plus a targeted amend instead of full reruns | K-6; run 2's exact defect is caught at package time and fixable without a new run | Low | Yes — amend semantics |
| 6 | 008 | SameFileError guard in gate approval copy | One-line crash fix observed with traceback | K-8 | None | No |

### J.2 Strong improvements supported by this run

| Order | Issue IDs | Proposed change | Why | Acceptance evidence | Risk | Operator decision |
|---|---|---|---|---|---|---|
| 7 | 009 | Cut a release containing the converter fix; run install upgrade on the Windows host; add run/controller version-compat warning; document 2.0.8's dispatch-before-submit (or auto-dispatch) | Every future trial otherwise re-hits skew surprises; propagation is itself an end-state litmus | Device `article-flow --version` ≥ fixed release; K-9 | Low | Yes — upgrade timing |
| 8 | 010 | Converter unit tests (allowlist, adversarial, unsupported constructs documented) | The fix that saved this article's core feature has zero test coverage | K-10 | None | No |
| 9 | 011 | Lock URLs/quotes, not anchor text (or regenerate locks post-verification) | Removes the observed qualification-vs-lock contention | K-11 | Low | No |
| 10 | 013 | No-unlink filesystem preflight for repo roots | Prevents silent git corruption on Cowork-style mounts | K-12 | None | No |
| 11 | 015 | `start --supersede` artifact carry with lineage | Makes the recovery path that saved this trial a supported operation (need shrinks if #2/#4 land) | K-13 | Low | No |

### J.3 Ideas that need another trial before adoption

- **012:** batch stages between human gates into single host turns / non-interactive runner — test in an agreed environment before building.
- **014:** voice held-out calibration (`held-out-different-form-001`) + passage-level operator annotation flow — requires operator input first.
- **Experiment pre-registration as a schema-backed stage** (generalizing this trial's improvised discipline) — only if future seeds keep demanding first-party evidence.
- **Second verification route via subagents** (different model tier as verification provider) — only meaningful once routing can register it honestly.

### J.4 Things that should remain unchanged

Everything in §E: seed-by-value preservation; code-gate strictness (including the locked-field and variation-budget lints that *fired usefully* this trial); voice-probe comparison mechanics; claim-ledger `allowed_wording` contracts; hash-chained events; content-addressed packaging + embedded revision meta; multi-surface deterministic packaging; manifest/protected-paths integrity flow; approval-before-side-effect ordering; the HEAD-drift guard's *existence* (only its recovery changes, per F-002).

---

## K. Regression plan

| # | Test name | Fixture/input | Failure it must reproduce | Expected post-fix behavior | Host/env | Deterministic? |
|---|---|---|---|---|---|---|
| K-1 | publish_preflight_no_credentials | Repo with unpushable remote (mock 403 on push) | Mid-execute failure with no trace (F-001/002) | Preflight fails → handoff artifact + `AWAITING_OPERATOR_DEPLOY`; no commit created | Any | Yes |
| K-2 | publish_execute_push_fails_after_commit | Force push failure post-commit | Orphan commit, no event, drift-guard self-block | `PUBLISH_ATTEMPT`/`PUBLISH_INCOMPLETE` events; retry recognizes own commit by tree/plan-revision | Any | Yes |
| K-3 | single_route_verification_recovery | One provider; 2 forced verification REPAIRs; then valid submission | Route excluded → BLOCKED → only exit is fresh run (F-003) | Waiver re-verification passes with disclosure receipt; operator TERMINAL also accepted | Any | Yes |
| K-4 | fetch_adapter_sanctioned_host | fetch_url stub returning 0; adapter supplying evidence | 3 claims forced to qualify (F-004) | Claims verified via adapter with method recorded; no operator interrupt | Sandbox-like | Yes |
| K-5 | carried_approval_receipt | Rerun with byte-identical gated artifact | Human-typed and agent-recorded approvals indistinguishable (F-005) | Receipt class `carried`, referencing original id + hash proof; channel recorded | Any | Yes |
| K-6 | publish_surface_cliche_lint | Brief description containing an inventory phrase | Run 2's metadata escape (F-006) | G-PACKAGE-INTEGRITY REPAIR naming the surface string; `amend` fixes without rewind | Any | Yes |
| K-7 | hash_scoped_repair | Editorial repair touching prose only | Full rewind replays human gates (F-007) | Only changed-input stages reopen; zero new human prompts | Any | Yes |
| K-8 | regate_unchanged_review_artifact | Rewind → gate PASS same artifact | `shutil.SameFileError` crash (F-008) | Gate passes; approved copy skipped/no-op | Any | Yes |
| K-9 | version_skew_guard | Run created by 2.0.6 opened by 2.0.8 | Silent dispatch-requirement change (F-009) | Explicit compat warning; submit auto-dispatches or errors with instruction | Any | Yes |
| K-10 | converter_allowlist_and_escapes | MD with details/summary, `<script>`, `<details onclick=…>`, table, entity | Pre-fix escaping of dropdowns (F-010) | Bare wrappers pass; everything else escaped; documented unsupported constructs stable | Any | Yes |
| K-11 | qualified_anchor_rewording | Ledger qualifying a linked claim; EDIT rewords anchor | Locked-field REPAIR against required rewording (F-011) | URL lock holds; anchor text change allowed | Any | Yes |
| K-12 | repo_on_no_unlink_mount | Repo root on unlink-denying FS | Stale `.git/index.lock` accumulation (F-013) | Controller refuses with actionable message before any git op | Cowork VM | Yes |
| K-13 | supersede_carries_evidence | `start --supersede` from run with experiments | Dangling ledger local-ids in fresh run (F-015) | Artifacts carried; lineage event recorded; ledger ids resolve | Any | Yes |
| K-14 | deployment_attest_out_of_band | Operator-pushed commit content-identical to package | Run frozen at PUBLISH forever (F-016) | Attest verifies tree/blob + revision meta → LIVE_VERIFICATION → COMPLETE | Any | Yes |
| K-15 | voice_held_out (adoption-gated) | Selected register applied to different-form passage, both orders | Not run this trial (F-014) | Profile's own `held-out-different-form-001` executes and records outcome | Any | No — operator judgment |

---

## L. Candidate project evidence (litmus support — not answers)

1. **"Raw idea → published article in my voice, my gates, link returned, intervention only at defined escalations — did one standalone cycle prove it?"**
   - Supporting: seed→live chain complete with byte-exact seed and content-exact deployment (§A, §I); all defined gates executed with receipts; link returned and correct.
   - Missing: publication required *undefined* escalations (credential dead-end, deadlock recovery, out-of-band push); controller never recorded publish/verify; operator post-hoc voice/intent verdict "Neither fully"; n=1.
   - Operator confirmation still required: whether the interventions that occurred count as "defined escalations" under their standard, and the voice verdict's specifics.
2. **"Same canonical process invoked from the agreed environments; one update propagating to every installation; every ingestion route publishing into canonical `docs/` and returning the live link?"**
   - Supporting: canonical `docs/{slug}.html` path + link return verified live; the adapter's instructions were honored from a non-installed environment; one converter fix now sits at repo HEAD ready to propagate.
   - Missing: no invocation from an installed host (Codex/Gemini/Windows); propagation not demonstrated (2.0.6 installs un-upgraded); only one ingestion route exercised.
   - Operator confirmation required: which environments are "agreed."
3. **"Is the scope of 'my journey' identified — what gets captured and what doesn't?"**
   - Supporting: this trial captured process-evidence exhaustively (runs, receipts, experiments) — an existence proof of *one* capture class.
   - Missing: nothing in the run defines journey scope; NOT OBSERVED anywhere in artifacts.
   - Operator confirmation required: entirely.
4. **"Is capture low-friction enough to log in the moment; is it clear when/how?"**
   - Supporting: the seed entered as one verbatim sentence pair — capture-at-idea worked once.
   - Missing: everything after seed capture was high-friction this trial (operator Q1/Q2 selections); no in-the-moment capture mechanism was exercised.
   - Operator confirmation required: their actual capture habits.
5. **"Where do process and captured material live for ready access?"**
   - Supporting: canonical locations exist and were used — repo (`Article-Spec-Pack-v1`, `docs/`), runtime home (`~/.article-flow/runs/` synced to the operator's machine), live site.
   - Missing: run 1's device copy is one rewind stale; the sandbox copies die with the session; no single index of "where things are" exists for the operator.
   - Operator confirmation required: whether current locations meet "readily accessible."

---

## M. Open questions (answers change the second-round implementation)

1. **Which environments are the "agreed project/AI environments"?** Determines whether F-001/F-004 adapters target Cowork sandboxes at all, or only Windows/WSL + Codex/Gemini hosts where raw egress and credentials exist — this reorders J.1 items 1 and 3. (Adapter registry names Codex and Gemini; this trial ran in neither.)
2. **What specifically is off in intent and voice ("Neither fully")?** Passage-level annotations decide whether F-014's fix is calibration (probe/profile work), gating (a second human read at DRAFT), or nothing (verdict driven by process frustration). Without this, second-round voice work is guesswork.
3. **Is agent-recorded approval on explicit operator instruction acceptable if attested as such (carried-approval class), or must human-class gates always be operator-typed?** Decides F-005's mechanism and how much autonomy the end state can actually have.
4. **Should deployment attestation (out-of-band push + content proof) count as publication for COMPLETE, or is controller-executed push mandatory?** Decides F-016/K-14 and the shape of J.1 item 1.
5. **Does the platform bug (claude-code#76248) get fixed on a relevant timeline?** If session repo grants become possible in Cowork, F-001's handoff path becomes a fallback rather than the primary sandbox flow.

---

## N. Evidence appendix

**Run directories** (present in the cloud workspace at `/root/work/article-flow/runs/` and synced to the operator's machine at `~/.article-flow/runs/`; run 1's device copy is one rewind stale — complete archives also in `~/.article-flow/_to_delete/_claude_runs_sync2.tgz`):
- Run 1 `AF-20260818T181926Z-…-9692be95` — 27 receipts; experiments under `artifacts/experiments/` (preregistration.md, preregistered_at.txt = 2026-08-18T18:23:29Z, scoring.md, e1-optimizer/, e2-agent-metric/, e3-{vague,concrete,trapped}/); fetch records under `artifacts/research-notes/`; `artifacts/site-converter-finding.md`.
- Run 2 `AF-20260818T204320Z-…-8909deda` — 18 receipts; TERMINAL; `g-publish-approval-18` carries the supersession reason (metadata cliché).
- Run 3 `AF-20260818T204536Z-…-3ecf6fc6` — 18 receipts; `package/` (package.json, site/, public/article.md, metadata.json); `publication/plan.json`; `approvals/AP-1259ba11d24dd6adcfd11423.json`; state PUBLISH.

**Key receipts/events:** run 1: `g-intent-fidelity-5` (19:06:48Z), `g-recipe-fit-8`, `g-voice-probe-11` (selection A), `g-claims-verified-13/14` (findings: "Source URL did not resolve during independent verification (HTTP 0)"), `g-editorial-qa-20` REPAIR (operator: clichés + rendering), rewind receipts 21–27. Run 3: events seq 94–99 (plan→approval→PUBLISH transition; log ends before the failed push — the F-002 evidence *is the absence*).

**Commits / revisions:**
- Live: `5bf45d373b13aa9912adea20ed1e22bc3c478655` (operator push, 2026-08-19T08:27:36Z).
- Sandbox-built equivalents: `421efdc` (converter fix), `6717997` (controller publish commit, unpushed; all 7 blobs verified identical to `5bf45d3`).
- Pre-trial main: `525e40d1185ade88a5249f70f9fc4e06c015c8e0`.
- Package revision: `ca87bd733a1ac0dc069ad605573a8de2270a6e54963c0e804c7f97cc4e6fb369`; article revision meta: `0a597798c121aaffcbdba6d652acfcc15f0919212168dfec53e953b838614adc`; seed sha256: `6c74125b90c1e419af63263ef78caf268e5f26ab6ca9350237f5c48df17809a7`.

**Live URLs (all fetched 200 with expected content 2026-08-19 ~08:35–08:38Z):** article `…/docs/the-machine-did-exactly-what-you-asked.html`; blog `…/docs/blog.html`; homepage `https://theproductiveprompter.com/`; `…/feed.xml`; `…/sitemap.xml`. Earlier negative control: article URL fetched 404 at ~2026-08-19T00:45Z (pre-deployment).

**Failure excerpts (verbatim):**
- Git proxy: `access denied by the git proxy: josiahH-cf/theproductiveprompter is not in this session's authorized repository set, so the proxy will not inject a credential for it.`
- Drift guard: `Repository HEAD changed after publication planning; create and approve a new plan {"planned":"421efdc…","actual":"6717997…"}`
- Hard gate: `Hard gate G-CLAIMS-VERIFIED is code-owned and cannot be manually passed`
- Crash: `shutil.SameFileError: …approved-article-recipe.json and …approved-article-recipe.json are the same file` (article_flow.py:1868, 2.0.6)
- 2.0.8 skew: `No dispatched task packet exists for RESEARCH_PLAN`
- Pre-fix converter output: 4× `&lt;details&gt;` + 4× `&lt;summary&gt;` visible-text wrappers (post-fix: 0; live page renders 4 native dropdowns).
- Platform bug reference: anthropics/claude-code issue #76248 (Cowork sessions: no UI to add a repo to the session's authorized set; no `add_repo` tool in sandbox).

**Environment notes:** Cowork device bridge forbids unlink on mounts (stale `.git/index.lock` quarantined at the operator's repo `_to_delete/`); computer-use grants terminals click-only; browser file-upload to GitHub was refused by the platform safety classifier; sandbox raw egress reserved to platform fetch tools (controller `urllib` → HTTP 0). Cleanup pending operator deletion: `_to_delete/` folders in `~/.article-flow/` and the repo.

*End of packet.*
