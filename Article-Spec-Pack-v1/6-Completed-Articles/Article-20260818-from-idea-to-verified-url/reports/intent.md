# Intent Discovery

## Explicit seed content

- The article is about how to start an article-creation workflow and schema.
- The Personal Growth project under `MAIN-Plan` is a baseline source.
- Documentation surrounding the article-workflow creation mechanism is a baseline source.
- Research must extend beyond those local materials.

## Operator-confirmed interpretations

- The article should inform readers how to build their own blog-publication automation.
- This article system should serve as the worked example; the self-referential nature of the example is welcome.
- Stages and gates are crucial parts of the design.
- Iterative voice development is a crucial part of making the resulting system unique to a particular blog.
- The Anthropic workflow article and Google's Article structured-data guidance should be used, but research must continue before intent is settled.
- The article should communicate the workflow through a human-readable diagram and practical checklists.
- It should remain easy to follow and avoid unnecessary technical complexity; a copyable YAML/JSON schema is out of scope for the main article.

## Relevant facts found in the supplied baseline

- The active Personal Growth project is `Documenting My Journey`.
- Its current desired path begins with a sparse, natural idea and ends with a vetted, published article and returned link.
- The project requires research before definition, explicit human ownership of material decisions, reusable infrastructure, traceability, and proof through a real run.
- The installed launch mechanism is a thin global skill plus a repository-resolving CLI and repository-owned entrypoint.
- The current launcher passes preflight and resolves controls, but the specified dynamic model router is not implemented.

These facts describe the baseline system. They do not establish which of them the operator wants emphasized publicly.

## System assumptions awaiting confirmation

- The likely audience is technically fluent people building AI-assisted content systems.
- The piece is likely a reusable guide carried by a transparent case study of this project.
- “Start” may mean begin with the smallest durable contract—input, end-state, state transitions, artifacts, ownership, gates, and one proof run—rather than begin by choosing tools.
- “Schema” may need to be split into workflow, run/provenance, content, and publication layers.
- The article may use this first `$start-article` run as a concrete opening or worked example without exposing private paths or internal notes.
- A two-loop model—editorial development followed by publication/deployment—may be the clearest portable architecture.
- The voice method may need to combine curated examples, explicit dimensions, anti-patterns, a preservation contract, evaluation cases, and occasional human calibration.
- The implementation may need separate workflow-definition and run-record schemas, joined by immutable version identifiers.
- Stages and gates may be clearest when modeled as a state machine with explicit pass, repair, bounded retry, escalation, and terminal-failure transitions.
- “Published” may need to mean a verified bundle of page, metadata, discovery surfaces, deployment revision, and returned canonical URL—not merely a successful deploy job.
- The project's current client-rendered article shell and missing discovery metadata may be useful as an honest worked example of why a live-verification gate exists.

## Material unknowns

1. Which meaning of “schema” is primary?
2. Who is the primary reader: an individual creator who can follow technical instructions, a software builder, or a content/engineering team?
3. Resolved: show the workflow/run contract conceptually through a diagram and checklists; do not include a copyable machine-readable schema in the main article.
4. What constitutes acceptable evidence that a generated draft sounds like the blog without merely copying a few surface traits?
5. Which gates are universal, and which should vary with subject, risk, and publication stack?
6. How much of the incomplete first-trial architecture should be exposed as an honest limitation?
7. What should the reader be able to do immediately after reading?
8. Should the worked example expose the current discoverability gaps and show the intended repair, or focus only on the finished architecture?

## Confirmed intent

**Confirmed by operator:** 2026-08-18

Write a practical, human-readable guide for independent creators and technically curious blog operators who want to build an AI-assisted publication workflow without turning it into an opaque content machine. Use this project's evolution—and this article's own creation—as the worked example.

The article's central position is that useful blog automation is not one giant prompt. It is a visible sequence of work stages, decision gates, bounded repair loops, and a verified publication outcome. Its distinctive voice is not installed once; it is taught iteratively through representative posts, explicit traits and anti-patterns, author feedback on near misses, conservative revision, and checks for voice fit, meaning preservation, and naturalness.

The reader should leave able to:

1. sketch a two-loop workflow covering editorial development and publication
2. distinguish a stage from a gate, retry, repair loop, escalation, and terminal state
3. choose a small set of intent, evidence, voice, package, deployment, and live-verification gates
4. establish an iterative voice-calibration practice unique to their own blog
5. define "published" as a verified page and discoverable public artifact rather than a successful deployment command
6. test the design with one real article and use the failures to improve the workflow

The main teaching devices will be one uncluttered workflow diagram, compact gate checklists, and brief callouts showing how the example project solved parts of the system over time and where it still has gaps. Implementation syntax, vendor-specific orchestration, and a copyable machine-readable schema remain outside the main path.
