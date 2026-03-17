---
created: 2026-03-17T03:53
updated: 2026-03-17T03:53
---
# Article Brief

## 1. Article Metadata

**Title:**
AI First Principles: How to Decide When AI Is the Right Tool

**Intended Audience:**
Software engineers, technical leads, and AI power users who use editors, CLIs, code review, and automation tooling in daily work.

**Publication Context:**
Standalone article for The Productive Prompter focused on operational decision-making for AI-assisted work.

**Estimated Scope:**
A practical article that helps readers decide whether to use plain code, a single prompt, a workflow, tool use, or an agent. Include decision rules, reusable prompt patterns, and guardrails. Exclude deep implementation detail for RAG pipelines, full orchestration frameworks, and vendor-specific product comparisons.

## 2. Objective & Scope

**Objective:**
Help readers stop treating AI as the default answer and instead choose the right method for the job. By the end, they should be able to classify a task, reject bad AI fits early, and select a safer execution pattern with an explicit verification plan.

**Scope:**
- Covers AI suitability, problem-type classification, verification-first design, automation boundaries, and method selection.
- Focuses on developer and technically fluent knowledge work.
- Includes recurring patterns for choosing between code, prompts, workflows, and agents.
- Excludes full framework implementation, benchmark comparisons, and deep product-specific setup guides.

**Constraints:**
Approx. 1,500-2,500 words; second-person developer voice; link-based citations by default; no internal scaffolding terms in public text.

**Required Blocks (for article parity with reference style):**
- 2-3 brief mental models
- 4 workflow sections with reusable prompt snippets
- Caution section on what not to outsource to AI
- Tri-stage checklist: Before / During / After

## 3. Core Argument

**Central Thesis:**
Most AI failures come from choosing the wrong operating model, not from weak prompting, so the highest-leverage skill is deciding when AI should be used, how far it should be trusted, and what verification boundary must contain it.

**Supporting Claims:**
- Stable, rule-based work should usually become code, not an AI conversation.
- Verification quality is the real limit on safe delegation.
- Repeated tasks often benefit more from AI-generated deterministic artifacts than from repeated runtime inference.
- Agents only make sense when the path is genuinely open-ended and the environment can provide ground truth at each step.

## 4. Planning Aids (Internal Behaviors)

- Scenario/vignette: open with a developer choosing between scripting a workflow and handing it to an agent.
- Comparison table: compare code, single prompts, workflows, and agents.
- Prompt plate: include compact prompts for suitability checking, workflow design, and guarded agent planning.
- Decision checklist: end with Before / During / After actions.
- Workflow blocks: suitability gate, method selection, build-time AI, bounded agent use.

## 5. Freshness Expectations

**Default:** Freshness is dynamic and topic-specific; avoid stale statistics.

**Time-Sensitive Topics:**
- Agent tooling and model capabilities: prefer recent vendor documentation and current engineering guidance.
- Product-specific orchestration patterns: avoid precise capability claims unless still current.

**Stable Topics:**
- Automation levels and human oversight models: foundational sources are acceptable.
- Verification-first system design and deterministic-vs-probabilistic tradeoffs: older authoritative sources are acceptable when still conceptually relevant.

**Research Gaps:**
- Avoid precise industry failure statistics unless they can be strongly sourced.
- Prefer durable operating principles over fast-aging benchmark claims.

**Companion-Site Policy:**
Prefer evergreen guidance with linkable further reading.

## 6. Success Criteria

**Evaluation Checks:**
- [ ] Reader can reject at least three bad AI fits before starting implementation.
- [ ] Reader can distinguish when to use code, a prompt, a workflow, or an agent.
- [ ] Article includes at least three prompt patterns tied to real developer workflows.
- [ ] Article gives clear guidance on verification and human review boundaries.
- [ ] Final section gives a concrete checklist a reader can use this week.

**Quality Benchmarks:**
Include a compact comparison table and at least one prompt pattern that turns repeated runtime prompting into deterministic build-time artifacts.

## 7. Risks & Assumptions

**Risks:**
- Topic can drift into abstract framework language and lose operational clarity.
- Readers may expect one universal answer instead of conditional decision rules.
- Overstating agent capabilities would undermine the main argument.

**Assumptions:**
- Readers already use AI in some engineering workflow.
- Readers value concrete decision rules more than motivational framing.
- Readers can interpret prompts, diffs, and CLI-oriented examples.

## 8. Integration Notes

**Cross-References:**
- Anthropic engineering guidance on effective agents
- NIST AI Risk Management Framework
- Parasuraman, Sheridan, and Wickens on human interaction with automation

**Tone Adjustments:**
Keep the article direct, practical, and skeptical of unnecessary complexity.

**Special Instructions:**
Do not use precise industry failure statistics unless they can be strongly sourced. Keep the article portable across tools and vendors.