# Article Workflow

This directory contains the provider-neutral article system for The Productive Prompter.

## Start here

From any shell-capable host:

```text
article-flow start
```

In a fresh Codex session, invoke `$start-article`. In Claude Code, invoke `/start-article`. Gemini CLI uses the shared Agent Skills adapter when installed. These are thin launchers; they do not contain workflow logic.

The first prompt is intentionally small:

> In one paragraph or less, what feels like it could be a good article? Write it naturally; you do not need to structure or polish it.

The controller preserves that seed verbatim, creates a resumable run, and returns one self-contained task or decision at a time. Use `article-flow status RUN_ID`, `article-flow next RUN_ID`, or `article-flow resume RUN_ID` to continue.

## Authority

The machine-readable authority is [`workflow/workflow.json`](workflow/workflow.json). Conflicts resolve in this order:

```text
run overrides > approved article recipe > workflow schema > house policy > examples
```

The generated human view is [`1-Master/Article-Workflow-v2.md`](1-Master/Article-Workflow-v2.md). Older prose specifications remain available as historical or editorial reference, but they do not override the workflow, an approved article recipe, or the house policy.

This distinction is deliberate. Narrative person, article length, opening, ending, summary, components, citation mode, and shape belong to the article recipe. There is no universal skeleton, workflow count, grammatical person, word band, citation style, or closing formula.

## What code owns

`scripts/article_flow.py` owns:

- run identity, locking, state transitions, retries, and the append-only audit chain;
- integrity checks and a SHA-256 release manifest;
- complete provider-neutral task packets;
- hard gates, artifact hashes, claim/evidence checks, and locked-field preservation;
- package generation, a publication dry run, scoped approval, exact deployment, and live-revision verification;
- host adapter installation and drift checks;
- evaluation-backed routing when calibrated results exist, with an honest active-host fallback while they do not.

Models work only inside the task packet they receive. They do not advance their own state, certify deterministic checks, choose publication targets, or infer operator-owned decisions.

## Public and private artifacts

The canonical private article is `article.md`. The website publication target renders it to `docs/{slug}.html`, updates the home page, article index, feed, and sitemap, and verifies the exact live bytes. Internal task packets, receipts, claim ledgers, and run events remain private.

`package`, `publish --plan`, scoped approval, `publish --execute`, and `verify-live` are separate operations. Smoke and conformance tests cannot publish.

## Health commands

```text
article-flow doctor --scope launcher
article-flow doctor --scope authoring
article-flow doctor --scope release
article-flow manifest check --against-worktree
article-flow adapters verify
article-flow conformance
```

Launcher health proves only that the command and canonical root resolve. Authoring health also requires specification integrity and an eligible execution route. Release health additionally requires a clean approved commit, current adapters, tests, and publication prerequisites.

## Voice and evidence

The current voice profile is provisional. Trial output is not silently promoted into the author corpus. Profile changes require author judgment and a held-out comparison.

Every material factual claim must be traceable and fresh enough for its use. Model memory is not a citation source. The final naturalization pass is conservative and fact-locked; a changed number, date, name, citation, URL, code token, quotation, or qualified claim reopens verification.

## Capability boundary

A model can participate when its host can execute `article-flow`, call the optional local MCP tool, or when the controller can invoke it through a configured provider adapter. A remote chat page with no shell, connector, API, or MCP access cannot run a local workflow.

See `article-flow --help` for the complete command surface.
