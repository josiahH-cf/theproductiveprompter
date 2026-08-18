---
article_flow_document_status: superseded
article_flow_authority: false
article_flow_redirect: ../0-START-ARTICLE.md
article_flow_removal_version: "3.0.0"
---

# Intake Mode: General Content → Expert Blog

> Superseded by the controller entrypoint. Retained for migration reference only.

Purpose
- Enable a simple CLI path: you provide general content (notes, bullets, a short brief, or a file) and the system generates a publication-ready expert blog post that matches the consolidated spec.

End State
- A blog-ready folder in `6-Completed-Articles/Article-[N]-[slug]/` with `index.md` (YAML front matter + clean article text), plus a copy of the brief used.

Core Principles
- The repository CLI is the canonical entrypoint and selects the best currently available eligible model for each task; no provider, named model, GUI, or manual upload path is required.
- Developer voice; invisible structure; no internal labels (Device/Gate/Hard Shape/Style Anchor) in public text.
- Link-based citations by default; APA only if the venue requires it.
- Dynamic freshness horizons based on topic; bracket research gaps if needed.

Workflow Summary
0) MVP Seed: Start with an operator-written paragraph or less describing the article idea; preserve it verbatim.
1) Intent Discovery: Research the subject, surface assumptions and plausible interpretations, and ask focused follow-ups before treating intent as understood.
2) Task Routing: Discover configured models and select the best eligible option for each task under the operator's runtime policy.
3) Brief Autogeneration: Once the intent boundary is satisfied, autofill `Article-Brief` using the confirmed input (objective, scope, planning aids, freshness).
4) Draft: Generate the blog following the consolidated spec and Blog Output Template.
5) Silent QA: Critic Loop (Voice, Focus, Evidence), mandatory final prose naturalization, fallback routing, and internal gate validation.
6) Package: Save results into `6-Completed-Articles/Article-[N]-[slug]/index.md` with YAML front matter and references.

Files
- `Intake-Workflow.md`: Step-by-step instructions for operators.
- `Intake-Prompt.md`: A ready-to-run meta-prompt that turns general content into an expert blog.
- `Intake-Brief-Autofill-Template.md`: Structured mapping from intake fields → Article Brief fields.

Notes
- The Default Style Anchor is an internal calibration tool only; never mention it in public text.
- Planning aids (vignettes, tables, before/after) are rendered naturally without labels.
- Gate statuses are internal-only.
