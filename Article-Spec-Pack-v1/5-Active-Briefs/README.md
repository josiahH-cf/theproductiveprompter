# Active Briefs

**Purpose:** This folder contains Article Briefs currently in development or awaiting approval.

---

## Workflow

When executing the Article Execution Meta-Prompt:

1. **Phase 1: Topic Intake** creates a new brief here as `Article-Brief-[topic].md`
2. Brief awaits `APPROVE` command from user
3. Upon approval, brief moves to production workflow (Phases 4–5)
4. Upon article completion, brief moves to `6-Completed-Articles/` alongside final article

---

## File Naming Convention

```
Article-Brief-[topic-slug].md
```

**Examples:**
- `Article-Brief-prompt-engineering-basics.md`
- `Article-Brief-context-window-management.md`
- `Article-Brief-token-optimization.md`

---

## Brief Status Tracking

Briefs in this folder may have status markers in their metadata:

- `DRAFT` — Created but not yet reviewed
- `PENDING` — Awaiting user approval
- `APPROVED` — Ready for article generation
- `IN-PROGRESS` — Article currently being drafted
- `REVISE` — Returned for modifications

---

## Archive Policy

Once an article is completed and passes all quality gates (A, B, C):
- Move brief to `6-Completed-Articles/[article-name]/brief.md`
- Update manifest.json with brief checksum
- Log move in CHANGELOG.md

---

**Do not manually edit briefs during execution.** All modifications should flow through the Execution Meta-Prompt's approval loop (Phase 3).
