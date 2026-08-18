# Repository Article Entrypoint

When a user asks to start, create, develop, revise, package, publish, or verify an article, use the repository-owned `article-flow` command. Do not recreate the workflow in this file or substitute a provider-specific prompt.

For a new article:

1. Run `article-flow doctor --scope authoring --json`.
2. Run `article-flow start`, passing the user’s seed if one was supplied.
3. Follow the complete action returned by `article-flow next RUN_ID --json`.
4. Stop at operator-owned decisions and publication approval.

The machine-readable authority is `Article-Spec-Pack-v1/workflow/workflow.json`. The public website target is configured in `Article-Spec-Pack-v1/publication/theproductiveprompter.json`; do not infer a legacy Markdown-viewer URL or edit publication surfaces outside the controller’s exact plan.

For existing non-article website work, inspect the current page and repository conventions directly. Never treat archived article documents or completed articles as active workflow rules.
