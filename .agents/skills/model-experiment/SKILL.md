---
name: model-experiment
description: Refresh The Productive Prompter Model Release Experiment, verify its frozen prompt and preserved records, and identify missing models. Use for /model-experiment, $model-experiment, or an experiment catalog update.
---

Run the repository controller from the repository root:

`python scripts/model_experiment.py update`

This refreshes the authenticated Codex and Claude CLI catalogs, verifies the frozen challenge and saved evidence hashes, deduplicates aliases, runs the exact stored prompt once on missing models, saves each original response, and regenerates the minimal preview. Existing results and ambiguous interrupted attempts are never regenerated. Read the returned JSON before reporting success. Open the returned preview when the user asks to see it.

A known Claude authentication failure stays recorded. After normal sign-in status confirms restored access, update may append the first actual response as a separate recovery attempt. Ordinary generation failures stay skipped. Report missing response coverage separately from models missing an entry.

`python scripts/model_experiment.py preview` refreshes the preview without generation. `python scripts/model_experiment.py check` performs discovery and checks without rendering or generation. `python scripts/model_experiment.py status` inspects saved state without refreshing catalogs. To restrict an update to one release, pass `--model` followed by the user's exact discovered model ID as one argument; do not silently substitute an alias or successor.

Never overwrite an original response, treat an unsuccessful catalog read as an empty model list, or describe a missing result as a completed test. A partial catalog is incomplete coverage. This command's catalog scope is client-visible models, not every model supported by an API or hidden service models. Use the hash-verified `experiments/model-release/prompt.txt` for any subsequent candidate call; do not reconstruct the challenge from memory.

The automatic checker invokes this same update controller. Read `experiments/model-release/runner-prompt.txt` for the separate website publication contract. The controller appends repository results and a local preview; public-site publication follows the repository's release process and is not implied by generation. Never report a live URL without verifying it.
