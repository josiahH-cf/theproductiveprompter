---
name: model-experiment
description: Refresh The Productive Prompter Model Release Experiment, verify its frozen prompt and preserved records, and identify missing models. Use for /model-experiment or an experiment catalog update.
---

Run `python scripts/model_experiment.py update` from this repository's root. It refreshes both authenticated client catalogs, verifies the exact frozen challenge and saved evidence hashes, runs the stored prompt once on missing models, appends original responses, and renders the minimal preview. Recorded results and ambiguous interrupted attempts are never regenerated. Read the returned JSON and open the returned preview if requested.

A known authentication failure stays recorded. Once normal Claude sign-in status confirms restored access, update may append the first actual response as a separate recovery attempt. Ordinary generation failures stay skipped. Distinguish missing model entries from missing actual responses.

Use `python scripts/model_experiment.py preview` to refresh without generation, `python scripts/model_experiment.py check` for discovery and verification only, or `python scripts/model_experiment.py status` for saved state only. Both adapters call the same maintained repository controller. An update may use `--model` with the exact discovered release ID as one argument.

Never overwrite an original response or infer complete coverage from a failed catalog read. A missing result is not a completed experiment. Catalog scope is the selectable client models; API-only and hidden service models are outside that list. For subsequent candidate calls, use the verified bytes of `experiments/model-release/prompt.txt`. For the separate execution/publication contract, read `experiments/model-release/runner-prompt.txt`; it does not prove execution or publication occurred.
