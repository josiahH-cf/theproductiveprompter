# Spec Conformance Checklist (Author QA)

Purpose: Ensure each article conforms to the Unified Article Spec, Style Baseline, Brand Pack alignment, and Evidence/IP policies—without leaking internal scaffolding.

---

## Voice & Tone
- [ ] Second-person developer voice (direct “you”; occasional “we” in team context)
- [ ] Confident, plain-spoken, instructive; anti-hype; no marketing speak
- [ ] No anthropomorphism; models described as predictive systems

## Structure (Implicit)
- [ ] Opening reality check (concrete, work-grounded tension)
- [ ] 2–3 mental models (brief; utility-first)
- [ ] 3–5 workflow blocks, each using When / Why / Pattern / Steps
- [ ] Caution section (what not to outsource: security, architecture, compliance, unreviewed code)
- [ ] Tri-stage checklist (Before / During / After)
- [ ] Closing activation (a single concrete next step)
- [ ] Optional Further Reading (3–6 credible links)

## Utility & Examples
- [ ] Each workflow includes a tight prompt snippet (role, objective, constraints, success criteria)
- [ ] Examples are realistic, scoped, and tool-aware (IDE/CLI/PR/CI where relevant)
- [ ] Any tables are reflowable Markdown; no images for layout

## Workflow Schema (If Workflows Present)
- [ ] PromptSpec present in prose (role, objective, constraints, success criteria)
- [ ] Output mode stated in natural language (e.g., “return a unified diff” or “draft a 7–10 item checklist”)
- [ ] Expected artifacts clear (diff, checklist, codemod prototype, grep pattern)
- [ ] Validation plan present (tests, logs/metrics, compare script)
- [ ] Change isolation stated (scope and exclusions)
- [ ] Rollback notes present (how to revert per step/PR)
- [ ] Guardrails articulated (vendor-neutral; no new deps; avoid authZ/authN/compliance)

## Evidence & Freshness
- [ ] Credible linkable citations by default; APA only if required by Brief
- [ ] Time-sensitive claims current or generalized/removed
- [ ] No public bracket placeholders (research tracked internally or via Research Pass)

## Anti-Leak & Readability
- [ ] No internal scaffolding terms (Device, Gate, Shape, Style Anchor, Critic Loop, Research Pass)
- [ ] No activation headers or file paths in public text
- [ ] Short paragraphs; scannable bullets; no redundant sentences (>5 identical words)
- [ ] Final line is a verification or next action (not a maxim)

---

Version: 1.1
Date: 2025-11-13
