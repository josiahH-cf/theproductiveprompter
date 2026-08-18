# First-Trial Notes

## Runtime and initiation

- Date: 2026-08-18
- Host: Codex desktop Work session.
- Exact model/provider/version exposed to the workflow: unavailable.
- Dynamic per-task model discovery, ranking, fallback, and evidence logging: not implemented; the active session is the temporary execution host.
- `article-flow doctor`: passed.
- Repository branch at start: `main`.
- Pre-existing changed files reported before the run: 20.
- Active run folder: `Article-Spec-Pack-v1/5-Active-Briefs/Article-20260818-starting-an-article-workflow-schema/`.

## Friction observed

- `$start-article` was not advertised in the session's available-skills catalog, although the local skill existed and was discoverable on disk. This added a manual discovery step.
- The launcher and repository entrypoint resolved successfully once found.
- The mandatory control read is substantial before the first visible intent question.
- “Workflow and schema” expands into several plausible schema layers; the process correctly prevented a premature brief, but the terminology may need a faster disambiguation pattern.
- The Brand Pack retains a third-person statement that conflicts with the higher-precedence second-person Style Baseline.

## Work completed so far

- Preserved the operator's raw seed verbatim.
- Loaded all controls required by the canonical entrypoint.
- Reviewed the active Personal Growth project, its litmus tests and decision history, the thin launcher implementation, workflow map, workflow-content schema, packaging metadata, and publication handoff.
- Began external research using primary or authoritative sources on LLM workflow design, process modeling, provenance, structural validation, risk-based oversight, and published Article structured data.
- Separated explicit seed content from system assumptions in `intent.md`.
- Inspected the site's actual Markdown viewer, blog surfaces, scheduled-release JavaScript, GitHub Pages workflow history, and live rendering behavior.
- Extended research into prompt examples, multidimensional evaluations, tone testing, personal-style imitation limits, deployment environments, and JavaScript search rendering.
- Added state-machine and error-handling research to distinguish work stages, decision gates, bounded retries, repair loops, escalation, and terminal states.
- Compared the internal lifecycle with WordPress post states to test stack portability rather than designing only for this Markdown/GitHub Pages site.
- Inspected the live article response and common discovery endpoints. The current route depends on client-side Markdown fetching, returns a generic server-visible title, and does not yet expose the inspected canonical/structured/discovery outputs.
- Refined the voice hypothesis around three independently evaluated dimensions: voice fit, content preservation, and naturalness.
- Recorded a provisional two-document schema: a versioned workflow definition plus an immutable per-run record.
- Created a claim ledger that separates direct evidence, project observations, cross-source inferences, caveats, and claims excluded from public prose.
- Created an article-specific style anchor and a versioned voice profile grounded in five project reference articles, with held-out regression cases and pairwise order reversal for disputed comparisons.
- Rechecked the intended primary and authoritative citation URLs before drafting; all returned successful responses on 2026-08-18.
- Created the operator-approved Article Brief, article-specific style anchor, and voice profile.
- Drafted a 2,000–2,700-word publication candidate with one plain-text workflow diagram and practical gate/voice/build checklists.
- Completed separate adversarial attacks on evidence, workflow failure modes, voice/meaning preservation, and reader complexity; repaired all material findings.
- Applied the mandatory final prose naturalization pass and re-ran link, duplication, placeholder, private-path, citation, and held-out voice checks.

## Operator effort and follow-ups

- First reading response clarified the public purpose, proof style, and two central design concerns without forcing a premature outline.
- The operator selected the Google and Anthropic sources for use, explicitly requested further research, and prioritized stages/gates plus iterative voicing.
- Follow-up usefulness: high; it materially narrowed purpose and emphasis.
- The second decision-forming follow-up resolved presentation depth: use a simple diagram and practical checklists, not a copyable workflow schema. This enabled a candidate intent without forcing a platform choice.
- The operator confirmed the candidate intent and explicitly requested deep research, voice matching, and adversarial review before delivery.

## Not tested yet

- Operator acceptance of the reviewed publication candidate.
- Completed-article packaging, site handoff, deployment, and post-deployment HTTP/browser/crawler verification.
- Dynamic model routing.
- Cross-environment invocation and propagated workflow updates.

## Publication state

- An operator-approved Article Brief and reviewed publication candidate exist in the active run folder.
- No `docs/` or website files have been changed.
- No commit, push, publication, or distribution has occurred.
- Live link: none.
