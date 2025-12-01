# Intake Mode: General Content → Expert Blog

Purpose
- Enable a simple path: you provide general content (notes, bullets, a short brief, or a PDF) and the system generates a publication-ready expert blog post that matches the consolidated spec.

End State
- A blog-ready folder in `6-Completed-Articles/Article-[N]-[slug]/` with `index.md` (YAML front matter + clean article text), plus a copy of the brief used.

Core Principles
- Developer voice; invisible structure; no internal labels (Device/Gate/Hard Shape/Style Anchor) in public text.
- Link-based citations by default; APA only if the venue requires it.
- Dynamic freshness horizons based on topic; bracket research gaps if needed.

Workflow Summary
1) Intake: Drop general content (text/notes/PDF) and provide a topic.
2) Brief Autogeneration: Autofill `Article-Brief` using the intake (objective, scope, planning aids, freshness).
3) Draft: Generate the blog following the consolidated spec and Blog Output Template.
4) Silent QA: Critic Loop (Voice, Focus, Evidence) and internal gate validation.
5) Package: Save results into `6-Completed-Articles/Article-[N]-[slug]/index.md` with YAML front matter and references.

Files
- `Intake-Workflow.md`: Step-by-step instructions for operators.
- `Intake-Prompt.md`: A ready-to-run meta-prompt that turns general content into an expert blog.
- `Intake-Brief-Autofill-Template.md`: Structured mapping from intake fields → Article Brief fields.

Notes
- The Default Style Anchor is an internal calibration tool only; never mention it in public text.
- Planning aids (vignettes, tables, before/after) are rendered naturally without labels.
- Gate statuses are internal-only.
