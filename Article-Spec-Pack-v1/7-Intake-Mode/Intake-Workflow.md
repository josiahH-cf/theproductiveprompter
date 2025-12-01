# Intake → Expert Blog Workflow

Audience
- Operators and models implementing an intake-driven blog generation flow.

Overview
- Convert raw content (notes, bullets, PDFs) into an expert blog using the consolidated Article Spec.

Steps
1) Intake Content
- Accept general content: pasted notes, a short outline, or a PDF.
- Collect: title (working), topic, intended audience, and any must-include points.

2) Autofill Article Brief
- Use `2-Templates/Article-Brief-Template.md`.
- Populate: Objective (1–2 sentences), Scope (IN/OUT), Constraints (second-person developer voice; no internal labels), Supporting claims, and Planning Aids (internal behaviors only).
- Set Freshness Expectations for any time-sensitive statements.

3) Draft Generation
- Follow `Blog-Output-Format-Template.md` for the final deliverable.
- Apply the consolidated spec: invisible structure (hook → models/definitions → workflows/examples → pitfalls → next steps).
- Render planning behaviors naturally; no device/gate/style-anchor labels in public text.

4) Silent QA
- Apply `1-Master/Critic-Loop-(Single-Pass-Self-Check).md` internally (Voice, Focus, Evidence).
- Validate Gates A–C internally; do not print gate names/statuses.

5) Package Blog
- Create `6-Completed-Articles/Article-[N]-[slug]/`.
- Write `index.md` with valid YAML front matter: `title`, `date`, `slug`, `tags`, `description`.
- Include a references section with links (APA if required by venue).
- Copy the generated `Article Brief` into the folder as `brief.md` (internal reference).
- Run `python scripts/package_article.py --article-folder ... --source-file ...` so the helper normalizes folders and moves the source intake file out of `0-Article-Content/`.

6) Logging
- Append entry in `CHANGELOG.md` (date, files, run-id).
- Update `manifest.json` as required.

Key Rules
- No internal scaffolding in public text.
- Link-based citations by default; APA only when required.
- Keep tables reflowable; avoid images for core data.
- Do not include gate/device summaries in the public post.
