---
article_flow_document_status: superseded
article_flow_authority: false
article_flow_redirect: ../0-START-ARTICLE.md
article_flow_removal_version: "3.0.0"
---

# Intake Meta-Prompt: General Content → Expert Blog (One-Shot)

> Superseded by `article-flow start`; do not execute this prompt as a parallel workflow.

System (Instructions for the CLI-Selected Model)
- The repository CLI selected this model for the current task from the eligible models configured and reachable at runtime. Do not assume a provider-specific capability or change the model-routing policy.
- Follow Article-Spec-Pack-v1. Precedence: Article Spec (Consolidated) → Style Baseline → Brand Pack → Article Brief → Critic Loop (silent) → Evidence & IP Annex → Device Catalog.
- Public text must be clean: no internal labels (Device/Gate/Shape/Style Anchor/Critic Loop/Research Pass).
- Use link-based citations by default; APA only if required. Keep tables reflowable.

User (You Provide)
- Raw article seed (one paragraph or less for the standalone MVP proof, written naturally rather than formatted for the system)
- Optional source material (notes, files, or excerpts)
- Audience nuance (optional)
- Desired tags/slug (optional)

Assistant (Steps to Execute)
0) Discover the Intended Article
- Preserve the operator's raw seed verbatim and distinguish it from every system inference.
- Identify material unknowns about purpose, audience, scope, position, evidence, and desired reader outcome.
- Run subject-appropriate research before narrowing when outside knowledge could improve or challenge the interpretation. Provide direct sources for the operator to read where the research affects intent.
- Ask focused follow-up questions one at a time; the operator defines and decides.
- Present a candidate article intent and unresolved assumptions. Do not treat it as confirmed until the configured intent-confirmation boundary is satisfied.

1) Autofill Article Brief
- Use `2-Templates/Article-Brief-Template.md` and fill: Title, Audience, Publication Context, Scope (IN/OUT), Objective, Constraints (developer voice; no internal labels), Supporting Claims, Planning Aids (internal behaviors), Freshness Expectations, Success Criteria, Risks & Assumptions.
- Apply the configured approval route; do not invent whether this article requires human confirmation.

2) Draft the Expert Blog
- Use `Blog-Output-Format-Template.md`. Apply invisible structure (hook → models/definitions → 2–4 workflows/examples → pitfalls → next steps).
- Render planning behaviors naturally; do not print device names or gate statuses.
- Add link-based citations. Include references section.

3) Silent QA & Package
- Apply Critic Loop (Voice, Focus, Evidence) silently; fix issues.
- Apply the Final Prose Naturalization Directive; preserve substance and re-run affected checks.
- Validate Gates A–C internally; do not print gate names or statuses.
- Create folder `6-Completed-Articles/Article-[N]-[slug]/` and save `index.md` with YAML front matter and references.
- Save the approved brief as `brief.md` in the same folder. Append CHANGELOG entry.
- Run `python scripts/package_article.py --article-folder ... --source-file ...` so the packaging helper normalizes artifacts and moves the intake file into the article’s `sources/` directory.

Acceptance Criteria
- The verbatim raw seed, research consulted, follow-up answers, candidate intent, and unresolved assumptions are traceable.
- No Article Brief or draft was created before the configured intent-confirmation boundary was satisfied.
- Blog folder exists with `index.md` and valid front matter.
- Developer voice; invisible structure; no internal labels.
- Link-based citations present; APA only if required by venue.
- References section included; tables reflowable.
- Final line includes next action; content passes silent gates A–C.
