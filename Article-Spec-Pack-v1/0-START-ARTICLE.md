# Start Article Adapter Contract

This is a human-readable adapter guide. The executable authority is [`workflow/workflow.json`](workflow/workflow.json), enforced by `article-flow`.

## Fresh session behavior

1. Run `article-flow doctor --scope authoring --json`.
2. If authoring is ready, run `article-flow start` with the user’s supplied seed. If no seed was supplied, show the controller’s exact seed question and wait.
3. Preserve and return the `run_id`.
4. Run `article-flow next RUN_ID --json`.
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

The shortest supported direct entrypoint is:

```text
article-flow start --seed "<operator seed>"
```
