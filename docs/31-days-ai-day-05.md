# Day 05: Evaluating AI Outputs (Bias, Hallucinations, and Facts)

## The Reality Check

You are not talking to an expert. You are talking to a statistical prediction engine that has read a lot of text, but does not actually understand any of it. It behaves like a confident toddler that will invent facts, mirror stereotypes, and give you fluent, polished nonsense without hesitation. If you treat its output as truth without checking, you are the one on the hook for whatever happens next.

## Mental Models

1. **The Learning Toddler**
   Think of the model like a child learning the word “cat” from pictures. If it only ever sees black cats, it quietly concludes that all cats are black. It does not hold beliefs, it just learns statistical patterns from data and repeats what is most likely to come next.

2. **The Confident Hallucinator**
   When the model does not know something, it does not stop and admit confusion. It still predicts the next likely word. Often, that “most likely” continuation is a clean, plausible lie. That is baked into how it works, not an edge case or implementation bug.

## The Workflow: The Trust But Verify Loop

### 1. Spotting Hallucinations (The “Show Your Work” Check)

**When/Why:** Use this pattern whenever you are asking for facts, citations, or reasoning where accuracy really matters. Models routinely invent case law, APIs, historical events, and academic references that look perfect on the surface.

**The Pattern:**

```markdown
[Your Question]

Constraint: If you do not know the answer with 100% certainty, state "I don't know." Do not invent facts. If you provide citations, include the URL or DOI.
```

**The Steps:**

1. Scan the output for concrete claims: dates, names, numbers, titles, case identifiers.
2. Click through every URL it gives you, because many will not resolve or will not match the quoted text.
3. Treat any claim that feels “too perfect” or argument completing as a red flag and verify it separately.

### 2. Identifying Bias (The “Bias Scan”)

**When/Why:** Use this for anything involving people, teams, hiring, performance reviews, demographics, or cultural topics. The model reflects the biases in its training data, and those biases are not subtle.

**The Pattern:**

```markdown
[Your Draft Content]

Task: Review the content above for potential bias.
1. Are there gendered assumptions in the language?
2. Are certain groups represented more favorably than others?
3. Suggest neutral alternatives for any biased phrasing found.
```

**The Steps:**

1. Run this scan on your AI generated draft before you send or publish it.
2. Manually check pronouns and role associations (for example, “doctor” = he, “nurse” = she) and flag any patterns.
3. Use the neutral alternatives as suggestions, then apply your own judgment to decide what to change.

### 3. Fact Checking (The “Source Audit”)

**When/Why:** Use this for summaries of complex topics, research, or anything that might be cited in a deck, memo, or decision document.

**The Pattern:**

```markdown
Summarize the key points of [Topic].

Requirement: For every key point, provide a quote or specific reference that supports it. If you cannot find a specific reference for a point, do not include it.
```

**The Steps:**

1. Force the model to attach each key point to a specific quote or reference. If you can, prefer a proper retrieval augmented generation (RAG) setup for this. See Day 08.
2. Check that each quote actually supports the claim it is paired with, rather than just sharing some keywords.
3. Treat the summary as a navigation aid to the real material, not as a replacement for reading the source.

## Caution: What Not to Outsource

Do not outsource final judgment on what is true. You can offload pattern matching, cross checking, and draft edits. You cannot offload the actual decision about what is correct. The model is a text generator, not an authoritative knowledge base.

## The Tri Stage Checklist

* **Before:** Is this a high stakes topic (legal, medical, financial, safety, or compliance)? If yes, you must not rely on AI alone.
* **During:** Does the output sound extremely polished and confident? Be more skeptical, not less. Confidence ≠ accuracy.
* **After:** Did you check the key claims against primary, trusted sources, not just another AI pass?

## Closing Activation

Take a recent output you used, maybe an email draft, a summary, or a code snippet. Pick one factual claim or assumption inside it and spend two minutes verifying it properly. Did the model get it right?

---

*Methodology Note: This article was drafted using the Unified Article Spec and then refined for clarity.* 

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
