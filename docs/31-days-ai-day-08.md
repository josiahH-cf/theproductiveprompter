# Day 08: Advanced Patterns (CoT, RAG, ReAct)

## The Reality Check

Simple prompts fall apart on complex work. If you ask an AI to solve a logic puzzle or interpret a 50 page document in one breath, it will usually hallucinate, skip key steps, or latch onto the wrong detail. To handle real complexity, you need to make the AI think before it talks.

## Mental Models

1. **The Math Student (CoT):** You do not just want the final answer, you want to see the work. If the reasoning is sound, the answer is usually sound.
2. **The Librarian (RAG):** Do not guess, go to this specific shelf, open this specific book, and use only what is inside.

## The Workflow: Advanced Reasoning Patterns

### 1. Chain of Thought (CoT)

**When/Why:** Use this for logic puzzles, math, system design, or any decision with many moving parts. You are forcing the AI to break the problem into pieces instead of jumping to a conclusion.

**The Pattern:**

```markdown
[Complex Problem Description]

**Task:**
Analyze this problem. **Before providing the final answer, think step-by-step.**
1. Break down the constraints.
2. Evaluate Option A vs Option B.
3. Show your reasoning for each step.

**Format:**
## Reasoning
[Step-by-step logic]

## Final Conclusion
[The Answer]
```

**The Steps:**

1. Clearly ask for "step-by-step" reasoning.
2. Separate the "Reasoning" section from the "Final Conclusion" section so you can inspect the logic independently of the answer.

### 2. Retrieval Augmented Generation (RAG), Manual Version

**When/Why:** Use this when you want answers based on your internal material, not whatever the model remembers from the public internet. Think policies, internal docs, specs, or proprietary knowledge.

**The Pattern:**

```markdown
**Context:**
Here is the text of our internal policy / API documentation:
---
[Paste Text Here]
---

**Task:**
Answer the following question **using ONLY the text provided above**. Do not use outside knowledge. If the answer is not in the text, state "I don't know."

**Question:** [Your Question]
```

**The Steps:**

1. Paste the source text as Context.
2. Add a clear negative constraint: "Do not use outside knowledge." This keeps the model grounded in the document and makes it easier to spot when something is missing.

### 3. ReAct (Reasoning + Acting)

**When/Why:** Use this for multi step workflows where the AI has to plan, do something, look at what happened, and then adjust. This is common in agent style systems, but the pattern is just as useful inside a single prompt.

**The Pattern:**

```markdown
**Goal:** [Objective]

**Task:**
Create a plan to achieve this goal.
1. **Thought:** What is the first step?
2. **Action:** What specific tool or sub-task is needed?
3. **Observation:** What would the result look like?
Repeat this loop until the goal is met.
```

**The Steps:**

1. Make the ultimate Goal explicit.
2. Enforce the "Thought → Action → Observation" loop, so the AI does not just plan once and then freewheel to a conclusion.

## Caution: What Not to Hand Off

Do not use CoT for creative writing. Step by step reasoning flattens the rhythm and tone you want for poetry, narrative, or freeform brainstorming. Use structured reasoning for logic and decision making, and let creative work stay loose.

## The Tri Stage Checklist

* **Before:** Is this a complex logic or trade off decision? Use CoT. Is this about specific, local knowledge in a document? Use RAG.
* **During:** Did the AI actually show its work, or did it jump straight to an answer and slap a few generic sentences on top?
* **After:** For RAG style prompts, did the response clearly rely on and cite the provided text, or does it sound like outside guessing?

## Closing Activation

Pick a real decision you are wrestling with, for example, "Should I refactor this codebase?" Use the Chain of Thought pattern and ask the AI to argue both sides step by step, then synthesize a recommendation at the end.

---

*Methodology Note: This article was drafted using the Unified Article Spec and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
