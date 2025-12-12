# Day 24: Long Context, Short Attention: How to Keep a Model on Track in Big Inputs

You paste a 40-page incident retro into a model.

It summarizes the easy parts, misses the one timeline detail that matters, and confidently “concludes” a root cause that was already disproven on page 12.

Nothing is wrong with the model.

You asked it to do a hard human job—build a mental map of a long document—without giving it a map.

Long context doesn’t remove the need for structure. It increases it.

---

## The Problem You’re Actually Solving: Navigation, Not Storage

When people talk about “long context,” they usually mean one thing:

> “I can paste more stuff.”

But the real problem in large inputs is not fitting tokens. It’s **keeping the model’s attention anchored on the parts you care about**.

A long input has three predictable failure modes:

- **Recency bias:** it overweights what’s near the end.
- **Salience bias:** it overweights what looks dramatic (alerts, big errors, scary phrases).
- **Goal drift:** it starts answering the question it *wishes* you asked.

If you want reliable outputs from big context, your job is to turn “a pile of text” into **an inspectable reading plan**.

---

## Proof Artifact: The Same Document, Two Outcomes

Here’s a simple before/after that shows what changes the output.

**Before (the common approach)**

```text
Summarize this postmortem and tell me the root cause.

[PASTE 40 PAGES]
```

**After (a reading plan + constraints)**

```text
Role: You are a careful incident reviewer.

Goal:
- Produce a root-cause narrative that matches the document.

Reading plan:
1) First extract a timeline table (timestamp, system, event, evidence quote).
2) Then list hypotheses mentioned in the document and mark whether each was confirmed, disproven, or still unknown.
3) Only then propose the most likely root cause, but you must cite the exact evidence quote(s).

Rules:
- If the document does not contain a definitive root cause, say "not determined" and list what evidence is missing.
- Do not invent metrics, dates, or claims.

Output:
1) Timeline table
2) Hypotheses table
3) Root-cause narrative (max 200 words)
4) Open questions

Document:
[PASTE]
```

Same input. Different behavior.

The model didn’t become smarter. You changed the task from “be insightful” to “produce verifiable intermediate artifacts.”

---

## The Context Budget Plan (What Goes In, What Stays Out)

Use this when you feel tempted to paste “everything.”

Your goal is to include the *minimum* context that lets the model do the job, and keep the rest available as on-demand evidence.

```text
Task: Help me decide what context to include.

I will provide:
- The decision I need to make
- The audience for the output
- The source materials I have (docs, logs, tickets)

You will:
1) Propose a context budget: what to include verbatim vs what to summarize vs what to omit.
2) Identify the 5 highest-risk missing details (things that would change the answer).
3) Produce a "request for evidence" list: what you would ask me for next if you had doubts.

Rules:
- Prefer verifiable artifacts over narrative.
- If the sources are contradictory, flag it.

Output:
- Context plan + evidence requests
```

Verification step:

- If the plan says “include everything,” it failed. Ask for the plan again with the rule: “Assume I can only paste 1–2 pages.”

---

## Build an Index First (Make the Model a Librarian)

Use this when you have a long doc (design doc, retro, PRD, security review) and you want to query it repeatedly.

Instead of asking for answers, ask for an index you can reuse.

```text
Role: You are a documentation librarian.

Task:
1) Create a table of contents with 10–20 entries.
2) For each entry, write a 1-sentence summary.
3) For each entry, list 3 keywords and 1 "why it matters" note.

Rules:
- Do not claim facts; summarize what is written.
- If a section is ambiguous, label it ambiguous.

Output:
- A Markdown table with: Section, Summary, Keywords, Why it matters

Document:
[PASTE]
```

How to use it:

- Once you have the index, you can ask targeted questions (“Use only sections 3, 7, and 9”).
- If the output matters, you can verify it by spot-checking the “why it matters” notes against the doc.

---

## Evidence-First Q&A (Force Quotes Before Conclusions)

Use this when the model keeps giving plausible conclusions that you can’t trace back to the source.

```text
Task: Answer my question using only evidence from the document.

Question:
[YOUR QUESTION]

Rules:
1) First, quote 3–7 relevant passages (exact text).
2) Then answer the question.
3) If the quotes do not contain an answer, say so.
4) Keep a clear line between "quoted evidence" and "inference".

Output:
- Evidence quotes
- Answer
- Inference notes

Document:
[PASTE]
```

Verification step:

- If the quotes do not support the conclusion, treat the answer as untrusted and tighten the question (or ask for different evidence).

---

## Guardrails: What Not to Outsource in Big-Context Work

Long documents often contain the most sensitive decisions.

Don’t hand these over to an unverified synthesis:

- **Final blame/causality statements** (especially in incidents and security)
- **Compliance interpretations** (what a policy “means”)
- **Legal conclusions** (what a contract “allows”)
- **Anything irreversible** (migrations, deprecations, comms to customers)

Use the model to produce **draft artifacts you can inspect**: timelines, risk tables, open questions, option comparisons.

---

## A Short Checklist

- [ ] Did I ask for intermediate artifacts (index, timeline, hypotheses) before asking for conclusions?
- [ ] Did I force evidence quotes before any summary claim?
- [ ] Did I avoid pasting sensitive or unnecessary data?
- [ ] Did I separate what the document says from what we infer?
- [ ] If this output matters, did I spot-check 2–3 citations against the source?

If you want models to be reliable on long inputs, treat context like a system you design, not a bucket you fill.

---

## Further Reading (Optional)

- Transformers (the core architecture behind most modern LLMs): https://arxiv.org/abs/1706.03762
- Mixture of Experts (conditional computation and routing): https://arxiv.org/abs/1701.06538
- Switch Transformers (simplified routing for sparse models): https://arxiv.org/abs/2101.03961

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
