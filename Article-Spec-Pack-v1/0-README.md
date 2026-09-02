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
2. Let the active local model complete the returned research, intent, recipe, drafting, verification, editing, and packaging tasks.
3. Intervene only when the controller asks you to confirm intent, choose an article recipe or voice probe, proofread the result, approve publication, or complete a credentialed publishing handoff.
4. Continue until exact live verification returns the `theproductiveprompter.com` article URL.

`article-flow list` is the small operational index. It shows the original idea, current state, run directory, and returned live link for every run. The same response identifies the canonical process directory, private captured-material directory, and public `docs/` directory. Windows and WSL keep separate installation and health records but use one private captured-material directory, so either command sees and resumes the same runs. A stopped session is resumed with `article-flow resume RUN_ID`; the idea does not need to be entered again.

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
- credential preflight, one explicit publication handoff when the active host cannot push, and remote-branch attestation before live verification;
- global Windows/WSL command installation and drift checks;
- evaluation-backed routing when calibrated results exist, with an honest active-host fallback while they do not.

Models work only inside the task packet they receive. They do not advance their own state, certify deterministic checks, choose publication targets, or infer operator-owned decisions.

## Public and private artifacts

The canonical private article is `article.md`. The website publication target renders it to `docs/{slug}.html`, updates the home page, article index, feed, and sitemap, and verifies the exact live bytes. Internal task packets, receipts, claim ledgers, and run events remain private.

`package`, `publish --plan`, scoped approval, `publish --execute`, and `verify-live` are separate operations. The brief gate applies the deterministic character and formulaic-phrase checks to the public title and description when they are first written, so display-text problems are normally repaired inside the brief's own bounded window. If one still needs correction later, `amend` changes the public title or description from `EDIT` onward without replaying research or drafting: before packaging it leaves the run where it is, so the gate that asked for the change still runs, and from `PUBLISH_APPROVAL` it returns to `PACKAGE` to rebuild. A bounded article amendment can repair naturalization without replaying research; a changed article must repeat post-edit claim verification and editorial QA before the controller permits another package. If the active host cannot publish, the controller returns one `human_action`; `deployment-attest` accepts the handoff only when the named commit is the current publication-branch head and every planned public file matches. An expired approval is never reused silently: `next` asks the operator whether to run `publish --renew-approval`, and renewal succeeds only when the target, package revision, and hashed plan are unchanged. Smoke and conformance tests cannot publish.

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

The current voice profile is provisional. Trial output is not silently promoted into the author corpus. Profile changes require author judgment and a held-out comparison. Editorial assessment covers the article and its public title and description. Packaging also rejects a deliberately narrow set of high-confidence formulaic public-display phrases; contextual voice judgment remains with the operator rather than a blacklist. Separately, the controller rejects U+2014 in drafts, edited articles, titles, and descriptions. That character policy is deterministic and does not depend on the contextual cliché assessment.

Every material factual claim must be traceable and fresh enough for its use. Model memory is not a citation source. The final naturalization pass is conservative and fact-locked; a changed number, date, name, citation, URL, code token, quotation, or qualified claim reopens verification.

## Capability boundary

A model can participate when its host can execute the local `article-flow` command, call the optional local MCP tool, or when the controller can invoke it through a configured provider adapter. A remote chat page with no access to this machine cannot invoke the global local command; that is an explicit capability boundary, not a reason to copy the workflow into the remote product.

See `article-flow --help` for the complete command surface.
