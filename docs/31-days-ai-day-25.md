# Day 25: Inference Engineering: The Part of AI That Actually Hits Your Users

Your model is “good.”

Your demo is “fast.”

Then you ship it.

Now it’s slow in the one screen that matters, expensive in the one workflow people spam, and flaky under load.

That gap is inference engineering.

Most AI problems that feel like “model quality” are really systems problems: how you feed context, how you batch, how you cache, how you stream, and how you measure.

---

## A Simple Mental Model: Three Clocks and Two Bills

If you’re building a real feature, you care about five things:

- **Time to first token (TTFT):** how long until the user sees *anything*.
- **Time to last token (TTLT):** how long until the user sees *done*.
- **Tail latency:** how bad the slowest requests feel.

And you pay two bills:

- **Compute:** GPUs/CPUs, memory, networking.
- **Tokens:** what you send and what you generate.

Inference engineering is the craft of trading these off deliberately instead of accidentally.

---

## Proof Artifact: The Same Prompt, Different Production Reality

Here’s why this matters.

A single prompt can behave very differently depending on how you serve it.

| You changed… | What users feel | What typically caused it |
|---|---|---|
| streaming vs non-streaming | “it’s instant” vs “it’s frozen” | TTFT dominates perception |
| batching policy | smooth vs spiky latency | batch size fights tail latency |
| caching | repeat requests are cheap vs always expensive | cache keys and invalidation |
| context size | accurate vs rambling vs slow | token budget and retrieval strategy |
| decoding settings | stable vs creative vs inconsistent | randomness shows up as “flakiness” |

The model didn’t change.

Your system did.

---

## The Latency Budget Brief (Decide What You’re Optimizing)

Use this when the team is arguing about speed without a shared target.

```text
Role: You are a pragmatic performance engineer.

Task: Create a latency + cost budget for this AI feature.

Inputs:
- User action: [what triggers the request]
- UX: [blocking vs non-blocking]
- Output type: [one sentence | bullet list | JSON | code]
- Safety requirements: [must cite sources, must refuse, etc]
- Failure tolerance: [can degrade? can fallback?]

Deliverables:
1) A latency budget table with: TTFT target, TTLT target, tail-latency risk.
2) Cost levers (tokens in/out, caching, batching, model choice).
3) A “degrade gracefully” plan if targets are missed.

Rules:
- Do not invent numbers.
- If targets depend on product context, ask 3 clarifying questions.
```

Verification step:

- If the brief does not say what to do when you miss targets (fallback, partial response, smaller context), it’s incomplete.

---

## Caching That Doesn’t Lie (Design a Cache Key You Can Defend)

Use this when your traffic has repeats: same question, same doc, same ticket workflow.

Caching is the fastest win and the fastest way to ship wrong answers.

```text
Task: Help me design a safe cache key and invalidation rules.

Context:
- What the user asks: [describe]
- What changes over time: [docs, inventory, policies]
- What cannot be cached: [personalized, sensitive]

Output:
1) Proposed cache key fields (explicit list).
2) What must be included to avoid cross-user leakage.
3) Invalidation triggers (what events should bust cache).
4) A short set of “cache-safe” and “cache-unsafe” examples.

Rules:
- If personalization exists, assume cache must be per-user unless proven otherwise.
- If retrieval is involved, include retrieval versioning in the key.
```

Verification step:

- Pick one scary scenario (policy changed, user permissions changed, doc updated). If your cache key wouldn’t notice, tighten it.

---

## Prompt Shape for Serving (Shorter Is Not the Point, Predictable Is)

Use this when the model is “good” in testing but drifts in production.

Your goal is to reduce variance by making inputs more structured and outputs more checkable.

```text
Role: You are a staff engineer optimizing for reliability.

Task: Rewrite my prompt so it is stable under load.

Input prompt:
[PASTE]

Requirements:
- Separate inputs into: context, constraints, task, output contract.
- Add an explicit stop condition (when to ask questions vs answer).
- Add a verification hook (how to check the output quickly).

Rules:
- Do not add facts.
- Keep it short enough to reuse.

Output:
- Revised prompt + a 5-bullet explanation of what changed.
```

Verification step:

- Run the same request multiple times. If the output structure varies, your “output contract” is too vague.

---

## Guardrails: What to Measure Before You Touch Knobs

Inference tuning without measurement turns into superstition.

Before you optimize, decide what you will log and how you’ll evaluate:

- **Request shape:** tokens in/out, context sources used.
- **Latency:** TTFT, TTLT, tail.
- **Quality:** rubric score, refusal rate (if safety), tool-call correctness (if tools).
- **Variance:** repeated runs on a fixed test set.

If you can’t reproduce a regression on a small, fixed set, you can’t fix it confidently.

---

## A Short Checklist

- [ ] Do we know whether we’re optimizing TTFT, TTLT, or tail latency?
- [ ] Do we have a fallback when we miss targets?
- [ ] Are we caching with keys we can defend (and invalidate)?
- [ ] Are prompts structured enough to keep output shape stable?
- [ ] Do we have a fixed eval set for regressions?

Inference engineering is where AI stops being a demo and becomes a product.

---

## Further Reading (Optional)

- Speculative decoding (speed up decoding without changing outputs): https://arxiv.org/abs/2211.17192
- FlashAttention (IO-aware exact attention for efficiency): https://arxiv.org/abs/2205.14135
- vLLM / PagedAttention (serving + KV-cache memory management): https://arxiv.org/abs/2309.06180

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
