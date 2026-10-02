# The Model Release Experiment

Use `/model-experiment` in Claude Code or the repository's `model-experiment` skill in Codex. Both invoke `python scripts/model_experiment.py update`. The command discovers current client-visible models, runs the frozen prompt once for missing versions, appends exact responses and usage, and renders the preview. A second unchanged update performs no generation.

For a terminal shortcut, run `python scripts/install_model_experiment.py` once, then use `model-experiment update`. `preview` refreshes the view without generation; `check` verifies prompt, records, and catalog coverage; `status` reads saved state. `update --model <exact-model-id>` restricts generation to one discovered release. The local daily automation invokes the same controller.

`prompt.txt` is frozen UTF-8 with LF newlines. Both its manifest and controller pin SHA-256 `d6ea22391915e294a6ed80dc109550b035cf7c9548159dc71d0efc39e661f96d`. A new challenge needs a separate experiment version, not an in-place digest update. `registry.json` indexes version identities and results. Each `records/<key>/` contains an exclusively created response and public evidence. Earlier responses are never polished or replaced.

Private attempt events, stderr, prompt copies, recovery checkpoints, and the update lock live outside the checkout under `~/.local/state/ProductivePrompter/model-release-v1`; use `--state-dir` to select another durable location. This path avoids differences between desktop-app and terminal environment variables. A captured result resumes without generation. An ambiguous started attempt stops for reconciliation. Its existence is never treated as permission to resend.

A recorded authentication failure is preserved as an eligibility failure. After Claude's normal authentication status reports restored access, an update may append its first actual response as a separate recovery attempt. It never replaces the error record. Ordinary generation failures and unknown interruptions are not automatically retried. Missing response coverage is reported separately from missing model entries.

Discovery performs no model-generation probes. Codex uses `debug models` without `--bundled`; Claude uses an initialization control response containing resolved models. Aliases and context-window annotations are deduplicated. This covers client-visible models rather than every API-only, manually selectable, or hidden service model. Discovery failure is partial coverage, not an empty provider list. Model revisions that providers do not expose remain labeled as such.

Candidates receive only the exact stored challenge as their user prompt, with each CLI's necessary platform instructions. Session-specific isolation disables task tools and customizations. Codex additionally uses a narrowed client catalog that preserves provider model identity and platform instructions while removing task tool metadata. Any observed task tool activity makes the result a protocol violation. The clients' system contexts and tokenizer costs differ; usage is preserved as reported, including cache and reasoning fields, without double-counting. A client-reported dollar estimate is an estimate, not a verified cash charge.

The independent checker enumerates all 256 order subsets and checks receipt arithmetic and donation status. Literary quality, story consistency, and word limits are currently marked unassessed. Original outputs remain available even when a check fails. One response is an anecdotal observation, not evidence of reliability or overall superiority.

The preview contains only the title and provider groups; technical details appear when a model is expanded. Ordering uses sourced release dates, with explicitly labeled first-seen fallback for unknown dates. `release-dates.json` can supply dated official sources for new releases. Website publication is a separate release step described in `runner-prompt.txt`; generation does not establish live publication.

Validation: `python -m unittest discover -s tests -p test_model_experiment.py -v`.
