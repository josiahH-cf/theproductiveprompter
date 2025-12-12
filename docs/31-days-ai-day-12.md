# Day 12: How the Machine Learned to Write

Over a decade ago, a neural network looked at a picture and said "cat." That sounds trivial now. But at the time, no one had explicitly programmed it to recognize cats. No one had written rules like "if whiskers AND pointed ears AND fur THEN cat." The system had looked at millions of labeled images and figured out the pattern on its own.

That moment changed everything. It meant machines could learn tasks that humans could not explicitly describe.

Today, the same principle powers the models you prompt. Understanding how they learned shapes how you should use them.

---

## The Three-Stage Assembly Line

Training a large language model is not one process. It is three distinct stages, each with different goals, different data, and different failure modes.

| Stage | What Happens | Data Source | What Can Go Wrong |
|-------|--------------|-------------|-------------------|
| **Pre-training** | Model reads billions of documents and learns to predict the next word | Public web, books, code, Wikipedia | Absorbs outdated info, biases, factual errors |
| **Fine-tuning** | Model learns to follow instructions and refuse harmful requests | Curated datasets of Q&A pairs, human demonstrations | Narrow training can create blind spots |
| **RLHF** | Model learns which responses humans prefer | Human rankings of model outputs | Optimizes for "sounds good" over "is correct" |

Most users only interact with the final product. But the behavior you see, both the impressive parts and the frustrating parts, traces back to decisions made at each stage.

---

## Pre-training: The Compression Engine

During pre-training, the model consumes text at a scale no human could match. Providers do not fully disclose training corpora, and public estimates vary widely.

But the model does not memorize this text. It compresses it into patterns.

Think of it like this: if you read a thousand mystery novels, you would start to notice patterns. The detective always has a flaw. The twist comes in the third act. The seemingly minor detail from chapter two turns out to be crucial. You could not recite any single novel word-for-word, but you could write a plausible mystery that feels like all of them.

That is what the model does, at scale, with everything from legal contracts to Python documentation to Reddit arguments.

**What this means for you:**

- The model "knows" things it never explicitly memorized. It can write in styles it was never directly taught.
- The model also absorbed every error, bias, and outdated claim in its training data. The cutoff date is real. So are the misconceptions.
- Asking for obscure facts is risky. The model will pattern-match to something plausible, whether or not it is true.

---

## Fine-tuning: Teaching It to Be Helpful

A pre-trained model is not useful out of the box. If you ask it a question, it might respond with another question, or continue your sentence as if it were writing a novel, or generate something offensive.

Fine-tuning adds a layer of instruction-following. Human annotators create thousands of examples:

```
User: Summarize this article in three bullet points.
Assistant: • First key point
• Second key point
• Third key point
```

The model learns the format. It learns that "summarize" means compression, not continuation. It learns that "three bullet points" means exactly three.

**Where fine-tuning breaks down:**

Fine-tuning teaches patterns, not understanding. If most training examples for "explain like I'm five" use simple vocabulary but still assume adult background knowledge, the model will do the same. It mimics the form without grasping the intent.

This is why you sometimes get technically correct but contextually wrong answers. The model matched the pattern but missed the point.

---

## RLHF: The Preference Layer

Reinforcement Learning from Human Feedback (RLHF) is the final polish. Human raters compare pairs of model outputs and pick which one is better. The model learns to maximize that preference signal.

This is where the model learns to sound confident, be concise, avoid controversy, and generally produce responses that people click "thumbs up" on.

**The tradeoff:**

RLHF optimizes for what *sounds* good to a human rater in a few seconds of evaluation. That is not the same as what *is* good for a complex task.

| RLHF Encourages | RLHF Discourages |
|-----------------|------------------|
| Confident tone | Expressions of uncertainty |
| Direct answers | "It depends" nuance |
| Agreeable framing | Pushback on flawed premises |
| Concise responses | Lengthy caveats |

This explains a failure mode you have probably seen: the model gives a clean, confident, wrong answer instead of saying "I'm not sure" or "your question assumes something that may not be true."

---

## Practical Implications: Working With (Not Against) the Training

Once you understand the assembly line, you can work with it instead of fighting it.

**For pre-training artifacts:**

The model's knowledge has a cutoff date. For anything time-sensitive, provide context explicitly or use retrieval-augmented generation (RAG).

```
Context: Here is the current LTS version of Node.js for my environment: [paste exact version].
Given this context, recommend a migration path from my current version.
```

**For fine-tuning blind spots:**

If the model misunderstands your intent, do not just rephrase. Show it an example of what you want.

```
Here is an example of the format I need:

Input: "The meeting is at 3pm tomorrow"
Output: { "event": "meeting", "time": "15:00", "date": "YYYY-MM-DD" }

Now process this: "Lunch with Sarah next Tuesday at noon"
```

**For RLHF overconfidence:**

Explicitly request uncertainty when it matters.

```
Analyze this contract clause for potential risks.

Important: If you are uncertain about any interpretation, say so explicitly. 
I would rather have honest uncertainty than confident speculation.
```

---

## The Training Data Question

"What was this model trained on?" is a question with legal, ethical, and practical dimensions.

**Legally:** Training data provenance is increasingly contested. Lawsuits are active. Licensing terms are murky.

**Ethically:** Models trained on public internet data inherit its biases, and amplify them. A model that learned from text where "doctor" statistically co-occurs with "he" will reproduce that association unless explicitly corrected.

**Practically:** You cannot audit what you cannot see. Model providers rarely disclose full training data. This means you cannot know, for certain, whether the model was trained on data relevant to your domain or whether it is extrapolating from distant analogies.

The mitigation is verification. Treat model outputs as drafts to be checked, not facts to be trusted.

---

## Before You Prompt

A quick checklist before your next interaction:

- [ ] Is my question about something after the model's knowledge cutoff? If yes, provide context.
- [ ] Am I asking for facts the model might plausibly hallucinate? If yes, request citations and verify them.
- [ ] Does my task require nuance the model might have been trained to smooth over? If yes, explicitly request caveats.
- [ ] Am I relying on the model's confidence as a signal of correctness? Stop doing that.

The model learned from patterns. Your job is to shape which patterns it matches.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
