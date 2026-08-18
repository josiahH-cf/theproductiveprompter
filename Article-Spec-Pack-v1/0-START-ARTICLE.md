# Start Article Adapter Contract

This is the one canonical human-readable adapter guide. The executable authority is [`workflow/workflow.json`](workflow/workflow.json), enforced by `article-flow`.

Local, ChatGPT-account, Claude-account/Cowork, and future host adapters point here; they do not copy the commands below. The stable remote location is:

```text
https://raw.githubusercontent.com/josiahH-cf/theproductiveprompter/main/Article-Spec-Pack-v1/0-START-ARTICLE.md
```

## Resolve the one command

Resolve the controller once for the session, then use that same command for every returned operation:

1. Prefer `article-flow` when it is on the host's path.
2. If it is not on the path but the managed local installation is visible, use its launcher:
   - Windows: `%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\article-flow.cmd`
   - WSL/Linux: `$HOME/.local/bin/article-flow`
3. If this is an account-hosted code environment without the managed installation, use an existing clean checkout of `https://github.com/josiahH-cf/theproductiveprompter`. If none exists, clone `main` into a task-owned working directory. Invoke `Article-Spec-Pack-v1/scripts/article_flow.py` with that environment's Python executable and set `ARTICLE_FLOW_REPO_ROOT` to the checkout root.
4. Before intake, require `manifest check --against-head` and `doctor --scope authoring` to pass through the resolved controller.
5. If the host cannot execute a command, access a Git checkout, or use the optional MCP adapter, report the exact missing capability and stop. Do not replace the controller with an improvised chat-only workflow.

The environment-specific resolution above belongs only in this file. Adapters must continue to point here rather than copying it.

## Fresh session behavior

1. Run `doctor --scope authoring --json` through the resolved controller.
2. If authoring is ready, run `start` through the resolved controller with the user’s supplied seed. If no seed was supplied, show the controller’s exact seed question and wait.
3. Preserve and return the `run_id`.
4. Run `next RUN_ID --json` through the resolved controller.
5. If the controller returns `perform_task`, complete only the supplied task packet, write only the requested artifact, and submit it with the returned command. Do not load the whole specification pack or rely on prior chat context.
6. If it returns `human_decision`, show the question and stop. The model may explain options, but it may not record a `PASS` for the operator.
7. If it returns `run_command`, run that exact deterministic operation.
8. Continue until the controller reports `COMPLETE`, `TERMINAL`, or a capability/decision it cannot resolve.

## Boundaries

- The raw seed stays verbatim. Interpretation belongs in later artifacts.
- Research precedes claims or narrowing when it could change intent.
- Models cannot self-pass code-owned gates or publish.
- Publication requires an exact plan and scoped, expiring approval.
- Public output excludes workflow labels, task packets, receipts, routing metadata, and private paths.
- “Live” means the expected rendered revision was retrieved and verified. It does not mean search indexing.
- While routing evaluations are uncalibrated, use the active capable host and say so. Do not call it the “best model.”

The shortest supported local entrypoint is:

```text
article-flow start --seed "<operator seed>"
```
