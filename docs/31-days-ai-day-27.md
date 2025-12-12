# Day 27: RAG in Production: Why “Just Add Retrieval” Still Ships Wrong Answers

You connect your model to your docs.

Now it can “use sources.”

So you ship it.

A week later someone asks a policy question, the model cites the right document… and still answers incorrectly because it pulled the wrong paragraph and smoothed over a key exception.

Retrieval doesn’t make the model truthful.

It gives the model **more plausible text to be wrong with**.

The win from RAG (retrieval-augmented generation) is not magic accuracy.

The win is that you can force the system to show receipts.

---

## The Mental Model: Retrieval Is a Noisy Sensor

Treat your retriever like a sensor.

Sometimes it returns the right evidence.

Sometimes it returns a near miss.

Sometimes it returns something that looks relevant but is outdated, incomplete, or missing the critical clause.

If your generator treats retrieval as ground truth, you will ship wrong answers with citations.

A RAG system has three jobs:

1. **Find** candidate evidence.
2. **Select** what matters.
3. **Answer** in a way you can verify.

Most “RAG failures” are actually selection failures.

---

## Proof Artifact: A Citation That Still Lies

Here’s the pattern you should expect.

| What you asked | What you wanted | What the system often does |
|---|---|---|
| “Can we store customer data X?” | a correct, scoped answer with exceptions | retrieves a general policy section and ignores the exception paragraph |
| “What changed in this release?” | a summary anchored to release notes | retrieves a changelog fragment and invents missing details |
| “How do I rotate credentials?” | steps for your actual system | retrieves a generic doc and outputs plausible but wrong commands |

The presence of a link does not make the answer safe.

The answer becomes safer only when you force the model to:

- quote the relevant lines
- name uncertainties
- refuse to guess when evidence is missing

---

## The Retrieval Contract (Make the Model Prove It Read the Source)

Use this when correctness matters.

```text
Role: You are a careful analyst.

Task: Answer the question using only the provided sources.

Question:
[QUESTION]

Sources:
[PASTE 3–10 EXCERPTS]

Rules:
1) First, quote the exact lines you will rely on.
2) Then answer using only what the quotes support.
3) If the sources do not contain an answer, say "not found" and list what you need.
4) Keep a clear separation between "quoted evidence" and "inference".

Output:
- Evidence quotes
- Answer
- Inference notes
- Missing information
```

Verification step:

- If the answer does not cite quotes, treat it as ungrounded and rerun with the rule: “No quotes, no answer.”

---

## Build a Source Pack (Stop Letting the Retriever Choose the Story)

Use this when your corpus is large or the question is high-stakes.

Instead of retrieving blindly, build a small “source pack” first: the handful of documents that should govern the answer.

```text
Task: Build a source pack for this question.

Question:
[QUESTION]

Candidate sources available:
- [doc list, links, or titles]

Rules:
- Select 3–7 sources that should control the answer.
- For each source, explain why it is relevant.
- Flag any missing source that would be necessary (e.g., policy exceptions, regional rules).

Output:
- Source pack list + why
- Missing sources
```

How this helps:

- It reduces retrieval variance.
- It makes review possible (“yes, these are the right docs”).
- It exposes missing governance (“we don’t have a canonical policy doc”).

---

## Chunking and Indexing Hygiene (Make Retrieval Less Random)

Use this when the model keeps citing the wrong part of the right document.

This is where many production RAG systems quietly fail:

- chunks that cut sentences in half
- chunks that separate definitions from rules
- chunks without titles, headings, or section names

You don’t need perfect chunking.

You need chunking that preserves meaning.

```text
Task: Improve retrieval quality by redesigning chunk structure.

I will provide:
- a sample document
- examples of bad retrieval (the wrong chunks returned)

You will:
1) Propose a chunking strategy (by heading, by section, by rule/exception pairs).
2) Propose what metadata to attach (doc title, section heading, last updated, access level).
3) Suggest 5 test queries to validate retrieval.

Rules:
- Do not invent claims about my system.
- If you need more context, ask specific questions.

Output:
- Chunking plan + metadata + test queries
```

Verification step:

- If the test queries only cover “easy” lookups, add 3 exception-heavy queries (where the wrong chunk is tempting).

---

## A Practical Guardrail: Refuse When Evidence Is Missing

High-trust RAG systems do one boring thing well:

They refuse to answer when the sources do not support the claim.

You can force this behavior in the prompt and in the UI:

- show “not found” as a valid outcome
- ask the user for the missing doc
- route to a human when the question is policy/contract/security

If the product forces an answer, the model will comply.

---

## A Short Checklist

- [ ] Does the answer quote the exact lines it relies on?
- [ ] Does the system separate evidence from inference?
- [ ] Can the system return “not found” without pretending?
- [ ] Are we validating retrieval quality with hard test queries?
- [ ] Do we have a source pack for high-stakes questions?

RAG becomes reliable when you treat retrieval as evidence, not as truth.

---

## Further Reading (Optional)

- RAG (retrieval-augmented generation): https://arxiv.org/abs/2005.11401
- REALM (retrieval-augmented pretraining): https://arxiv.org/abs/2002.08909
- RAG survey (patterns and evaluation): https://arxiv.org/abs/2312.10997

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc). The finalized article is then run through a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
