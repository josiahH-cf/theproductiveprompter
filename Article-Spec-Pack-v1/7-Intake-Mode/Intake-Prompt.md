# Intake Meta-Prompt: General Content → Expert Blog (One-Shot)

System (Model Instructions)
- Follow Article-Spec-Pack-v1. Precedence: Article Spec (Consolidated) → Style Baseline → Brand Pack → Article Brief → Critic Loop (silent) → Evidence & IP Annex → Device Catalog.
- Public text must be clean: no internal labels (Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass).
- Use link-based citations by default; APA only if required. Keep tables reflowable.

User (You Provide)
- Topic (one line)
- General content (notes, bullets, or pasted excerpts)
- Audience nuance (optional)
- Desired tags/slug (optional)

Assistant (Steps to Execute)
1) Autofill Article Brief
- Use `2-Templates/Article-Brief-Template.md` and fill: Title, Audience, Publication Context, Scope (IN/OUT), Objective, Constraints (developer voice; no internal labels), Supporting Claims, Planning Aids (internal behaviors), Freshness Expectations, Success Criteria, Risks & Assumptions.
- Show the brief and ask for APPROVE/REVISE. If user says "auto-approve," proceed.

2) Draft the Expert Blog
- Use `Blog-Output-Format-Template.md`. Apply invisible structure (hook → models/definitions → 2–4 workflows/examples → pitfalls → next steps).
- Render planning behaviors naturally; do not print device names or gate statuses.
- Add link-based citations. Include references section.

3) Silent QA & Package
- Apply Critic Loop (Voice, Focus, Evidence) silently; fix issues.
- Validate Gates A–C internally; do not print gate names or statuses.
- Create folder `6-Completed-Articles/Article-[N]-[slug]/` and save `index.md` with YAML front matter and references.
- Save the approved brief as `brief.md` in the same folder. Append CHANGELOG entry.
- Run `python scripts/package_article.py --article-folder ... --source-file ...` so the packaging helper normalizes artifacts and moves the intake file into the article’s `sources/` directory.

Acceptance Criteria
- Blog folder exists with `index.md` and valid front matter.
- Developer voice; invisible structure; no internal labels.
- Link-based citations present; APA only if required by venue.
- References section included; tables reflowable.
- Final line includes next action; content passes silent gates A–C.
