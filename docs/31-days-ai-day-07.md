# Day 07: The CRIT Framework (Structuring Your Prompts)

## Why Structure Matters

"Garbage in, garbage out" is the iron law of computing, and it applies even more with AI. If you ask with a vague, lazy prompt like "Write a blog post," you should expect a vague, lazy response. If you want professional output, you have to prompt like a professional. Structure is not a nice to have, it is the interface.

## Two Useful Mental Models

1. **The Detective:** The AI needs evidence, your Context, to solve the case. If you hold back the facts, it is forced to guess.
2. **The Actor:** The AI needs a character, a Role, to inhabit. If you do not give it a part to play, it defaults to a bland, generic assistant.

## The CRIT Framework

CRIT is a simple way to structure almost any serious prompt: **Context, Role, Instruction, Task Format**. Use these four parts when you care about the quality and usability of the output.

### 1. Context (The Setup)

**When/Why:** Use this every time. This is the background your amnesiac expert needs to understand why you are asking and what problem you are actually trying to solve.

**The Pattern:**

```markdown
**Context:**
I am a [Job Title] working on [Project].
We are facing [Problem/Challenge].
Here is the raw data/email thread/code snippet:
[Paste Data Here]
```

**The Steps:**

1. State who you are and what you are working on.
2. Paste the raw material the AI should read or transform.

### 2. Role (The Persona)

**When/Why:** Use this when you care about tone, seniority, or viewpoint. The Role shapes how the AI thinks and speaks.

**The Pattern:**

```markdown
**Role:**
Act as a [Expert Role, e.g., Senior Project Manager / Python Architect / Copywriter].
You are [Adjective, e.g., critical, concise, creative].
```

**The Steps:**

1. Pick a concrete job title, not just "assistant."
2. Add one or two adjectives to set the vibe, for example, "skeptical security engineer" or "enthusiastic marketing intern."

### 3. Instruction (The Task)

**When/Why:** Use this to tell the AI exactly what to do with the context. This is where you define the work, not just the topic. Be direct and specific about the deliverables.

**The Pattern:**

```markdown
**Task:**
Based on the context above, please:
1. Analyze the [Data].
2. Identify the top 3 [Insights].
3. Draft a [Deliverable].
```

**The Steps:**

1. Use a numbered list so each action is clear.
2. Start every line with a strong verb, for example, Analyze, Draft, Critique, Refactor.

### 4. Task Format (The Output)

**When/Why:** Use this so the output is immediately usable, without you having to rework or reformat it.

**The Pattern:**

```markdown
**Format:**
Output the result as a [Format, e.g., Markdown Table / JSON / Bulleted List].
Include columns for: [Column A], [Column B].
```

**The Steps:**

1. Picture exactly what you want to copy and paste into your document, tool, or system.
2. Describe that structure explicitly so the AI can match it.

## What Not to Outsource

Do not outsource the "why." The Context step forces you to define the problem in your own words. If you cannot explain the context, you do not understand the problem well enough to prompt the AI in a reliable way.

## Quick Checklist

* **Before:** Did I include the raw data and relevant details in the Context?
* **During:** Did I define a specific, concrete Role? (Generic AI means generic output.)
* **After:** Did the output follow the Format I asked for? If not, tell it explicitly to "reformat as X" and run it again.

## Next Step

Grab a recent prompt that produced a mediocre result. Rewrite it using the CRIT headers, **Context**, **Role**, **Task**, and **Format**, then run it again. Compare the two outputs side by side.

---

*Methodology Note: This article was drafted using the Unified Article Spec and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
