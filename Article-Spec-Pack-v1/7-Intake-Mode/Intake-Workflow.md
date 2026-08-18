---
article_flow_document_status: superseded
article_flow_authority: false
article_flow_redirect: ../workflow/workflow.json
article_flow_removal_version: "3.0.0"
---

# Intake → Expert Blog Workflow

> Superseded process reference. The executable v2 state machine controls intake and intent discovery.

Audience
- Operators and CLI-selected models implementing an intake-driven blog generation flow.

Overview
- Convert raw content (notes, bullets, or source files) into an expert blog using the repository CLI and consolidated Article Spec.

Runtime
- The CLI discovers configured and reachable models, selects the best eligible model separately for each task, and applies fallback routing when a selected model cannot pass its gates.
- No provider, named model, GUI, or manual upload flow is a required dependency.

Steps
1) Intake Content
- For the standalone MVP proof, accept one operator-written paragraph or less describing what the article might be about. Do not ask the operator to pre-structure it for the system.
- Preserve that seed verbatim before interpretation. Richer notes or source files may remain supported inputs outside this proof fixture.

2) Intent Discovery
- Separate explicit seed content from system assumptions.
- Identify material unknowns about purpose, audience, scope, position, evidence, and desired reader outcome.
- Start subject-appropriate research and return direct sources when they could change the article's intent.
- Ask focused follow-up questions; do not decide or define the operator's intent.
- Produce a candidate article intent plus remaining assumptions, then apply the configured intent-confirmation policy.

3) Autofill Article Brief
- Use `2-Templates/Article-Brief-Template.md`.
- Populate: Objective (1–2 sentences), Scope (IN/OUT), Constraints (second-person developer voice; no internal labels), Supporting claims, and Planning Aids (internal behaviors only).
- Set Freshness Expectations for any time-sensitive statements.

4) Draft Generation
- Use the CLI-selected model best suited to the article's subject, evidence, context, and length requirements.
- Follow `Blog-Output-Format-Template.md` for the final deliverable.
- Apply the consolidated spec: invisible structure (hook → models/definitions → workflows/examples → pitfalls → next steps).
- Render planning behaviors naturally; no device/gate/style-anchor labels in public text.

5) Silent QA
- The CLI may select a different model for criticism and naturalization than it used for drafting.
- Apply `1-Master/Critic-Loop-(Single-Pass-Self-Check).md` internally (Voice, Focus, Evidence).
- Apply `10-Final-Prose-Naturalization/Final-Prose-Naturalization-Directive.md` and re-run affected checks.
- Validate Gates A–C internally; do not print gate names/statuses.

6) Package Blog
- Create `6-Completed-Articles/Article-[N]-[slug]/`.
- Write `index.md` with valid YAML front matter: `title`, `date`, `slug`, `tags`, `description`.
- Include a references section with links (APA if required by venue).
- Copy the generated `Article Brief` into the folder as `brief.md` (internal reference).
- Run `python scripts/package_article.py --article-folder ... --source-file ...` so the helper normalizes folders and moves the source intake file out of `0-Article-Content/`.

7) Logging
- Append entry in `CHANGELOG.md` (date, files, run-id).
- Update `manifest.json` as required.

Key Rules
- No internal scaffolding in public text.
- Link-based citations by default; APA only when required.
- Keep tables reflowable; avoid images for core data.
- Do not include gate/device summaries in the public post.
