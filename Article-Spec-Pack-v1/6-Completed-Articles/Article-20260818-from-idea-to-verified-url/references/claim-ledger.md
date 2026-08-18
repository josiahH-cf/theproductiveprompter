# Claim Ledger

This ledger is an internal drafting control. It separates directly sourced claims, observations about the example project, and cross-source inferences. Only claims marked **Use** may enter the public draft.

## Workflow and gate claims

### C01 — Workflows and agents are different operating patterns

- **Candidate claim:** A workflow follows predefined paths; an agent chooses parts of its path dynamically.
- **Evidence:** Anthropic, “Building effective agents.”
- **Scope limit:** This is Anthropic's useful terminology, not a universal formal definition.
- **Decision:** **Use**, attributed to Anthropic and expressed as a practical distinction.

### C02 — Start with the simplest workable architecture

- **Candidate claim:** A bounded workflow should precede added autonomy when the path is repeatable.
- **Evidence:** Anthropic's explicit “start simple” guidance plus the local project's “output quality first, automation second” retrospective.
- **Scope limit:** Open-ended work may justify dynamic routing earlier when the environment supplies reliable feedback.
- **Decision:** **Use**.

### C03 — A stage and a gate do different jobs

- **Candidate claim:** A stage produces an artifact or state change; a gate evaluates named conditions and chooses a transition.
- **Evidence:** BPMN's separation of activities and gateways; AWS Step Functions' Task/Choice distinction.
- **Scope limit:** The wording is a synthesis for blog workflows, not a quote from either standard.
- **Decision:** **Use**, identified as a design model.

### C04 — Failures need different paths

- **Candidate claim:** Transient failures may be retried; quality failures should return to a repair stage; exhausted or owner-controlled decisions should escalate.
- **Evidence:** AWS Retry/Catch behavior; Anthropic evaluator–optimizer loop; NIST oversight/role guidance.
- **Scope limit:** Retry safety depends on the side effect and implementation.
- **Decision:** **Use**.

### C05 — Publication retries must be safe

- **Candidate claim:** A timed-out publish step should not be blindly repeated if it might duplicate a post, card, or announcement.
- **Evidence:** RFC 9110's treatment of idempotent requests and warning on automatic retries of non-idempotent methods.
- **Scope limit:** The article will explain the effect in plain language rather than teach HTTP semantics.
- **Decision:** **Use**.

## Voice claims

### C06 — Examples steer visible output behavior

- **Candidate claim:** Relevant, diverse examples can steer tone, structure, and format.
- **Evidence:** Anthropic prompting best practices.
- **Scope limit:** Provider guidance for Claude; avoid presenting example counts as a universal law.
- **Decision:** **Use** without a prescriptive number.

### C07 — Examples alone do not reliably reproduce personal blog voice

- **Candidate claim:** Few-shot imitation remains weaker for informal blog/forum writing than for more structured domains, and adding examples produces limited gains in the studied setup.
- **Evidence:** Wang et al. (2025), over 400 authors and more than 40,000 generations per model.
- **Scope limit:** Primarily computational evaluation, within-genre setup, no large-scale human evaluation, and model/version-specific experiments.
- **Decision:** **Use** with the limitation attached; do not turn it into “AI cannot write in your voice.”

### C08 — Voice evaluation is multidimensional

- **Candidate claim:** A rewrite can sound more stylized while preserving less content or becoming less natural.
- **Evidence:** Mir et al. (2019) evaluates style intensity, content preservation, and naturalness separately; Anthropic recommends multidimensional, task-specific evaluations.
- **Scope limit:** Mir et al. studies sentiment style transfer, not personal blog voice. The three-part blog check is an analogy and synthesis.
- **Decision:** **Use**, explicitly framed as a useful adaptation.

### C09 — The author remains the final voice authority

- **Candidate claim:** Automated critics can scale feedback, but disputed voice judgments should return to the author.
- **Evidence:** ExPerT's framing of personalized evaluation; LLM-as-judge position-bias research; the project's retrospective on human tone work.
- **Scope limit:** The specific escalation rule is a workflow recommendation.
- **Decision:** **Use**.

### C10 — Voice and tone should be separated

- **Candidate claim:** Keep a stable voice profile while letting tone vary with subject and reader state.
- **Evidence:** Mailchimp Content Style Guide; Nielsen Norman Group tone dimensions.
- **Scope limit:** Brand-writing guidance, not an AI evaluation study.
- **Decision:** **Use**.

## Publication claims

### C11 — A successful deploy is weaker than verified publication

- **Candidate claim:** Deployment proves that a build reached an environment; it does not prove that the intended article renders correctly, carries consistent metadata, or is represented on discovery surfaces.
- **Evidence:** GitHub Pages build/deploy separation; Google build/test/deploy/inspect guidance; direct inspection of the example project.
- **Scope limit:** This is an operational definition chosen for the article, not an industry standard.
- **Decision:** **Use**.

### C12 — Google renders JavaScript, but rendered output still needs inspection

- **Candidate claim:** Google processes JavaScript pages through crawl, render, and index phases, so an initial HTML shell is not proof of indexing failure; it is a reason to inspect the rendered result.
- **Evidence:** Google JavaScript SEO basics and URL Inspection guidance.
- **Scope limit:** Do not promise or diagnose actual indexing without Search Console evidence.
- **Decision:** **Use**.

### C13 — Structured data and sitemaps aid representation and discovery but do not guarantee results

- **Candidate claim:** Article markup can help Google understand a post, while sitemaps and recrawl requests are discovery mechanisms rather than indexing guarantees.
- **Evidence:** Google Article structured-data, sitemap, canonical, and recrawl guidance.
- **Scope limit:** Article structured data currently has recommended, not required, properties for Google's article feature.
- **Decision:** **Use**.

## Project case-study claims

### C14 — The 31 Days experiment automated meaningful parts, not the complete current target

- **Candidate claim:** The project automated bulk article creation, scheduled visibility, and deployment, while its retrospective identified review, fact-checking, and tone as the expensive work.
- **Evidence:** Public Day 31 retrospective plus local source and release code.
- **Scope limit:** Self-reported timings and quality judgments must not be repeated as independently verified facts.
- **Decision:** **Use** without promotional timing/quality claims.

### C15 — The voice system evolved iteratively

- **Candidate claim:** The project moved through a default style anchor, reference examples, critique, and a preservation-focused final prose pass rather than discovering a final voice prompt in one attempt.
- **Evidence:** Changelog, style controls, Day 14, Day 31, and current directives.
- **Scope limit:** Some current controls are local work in progress and should be described as the current design, not necessarily the deployed public system.
- **Decision:** **Use**.

### C16 — The launcher is not the whole automation

- **Candidate claim:** The current launcher can find and load the canonical workflow, but planned dynamic model discovery/routing is not implemented.
- **Evidence:** `article_flow.py`, entrypoint, changelog, and preflight output.
- **Scope limit:** Keep private paths and run metadata out of public prose.
- **Decision:** **Use** briefly as an honesty check, not as a detour.

### C17 — The current article route demonstrates a verification gap

- **Candidate claim:** The raw response contains a generic title and shell; JavaScript fetches Markdown and updates the browser title, while the inspected source lacks post-specific canonical, social, and Article structured metadata. No sitemap/feed was found at the common endpoints.
- **Evidence:** Local `article.html`, direct live HTTP inspection, and common endpoint checks.
- **Scope limit:** This does not prove a Google indexing failure. A missing `robots.txt` is not itself a defect.
- **Decision:** **Use** as the worked example for a live gate.

## Claims excluded from the public draft

- The project has achieved fully autonomous idea-to-live publishing.
- The current launcher dynamically selects the best model for every task.
- Adding Article structured data or a sitemap guarantees indexing or rich results.
- More examples always improve personal voice imitation.
- An LLM score can prove that prose sounds like its author.
- Missing `robots.txt` means the site cannot be crawled.
- The 31 Days retrospective's time, quality, employment, or industry-wide claims are independently established.
