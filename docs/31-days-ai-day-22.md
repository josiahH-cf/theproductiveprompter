# Day 22: The Developer’s Primer: How AI Actually Works Under the Hood

## The Reality Check: It’s Not Magic, It’s Math

To most people, AI feels like magic. To sci fi fans, it’s a character with intent. As a developer, you need a different frame. You’re not talking to a person or a black box; you’re working with **a system**.

If you treat AI like a human, you’ll get annoyed when it “lies” or “forgets.” If you treat it like a normal function, you’ll stumble when it gives different answers to identical inputs. The right approach sits between those extremes. You need a mental model that matches how the machine actually behaves.

## Mental Models: The Prediction Engine

### 1. Probabilistic vs. Deterministic Systems

Traditional software is deterministic. `2 + 2` always returns `4`.
Language models are probabilistic. They calculate something closer to:
`[4: 0.99, 5: 0.0001, "fish": 0.000001]`.

They don’t “know” answers; they generate the next most likely token based on patterns in their training data. You’re steering probability distributions, not invoking rules.

### 2. The Latent Space

Think of the model’s internal representation as a vast, multidimensional map of concepts. Words and ideas cluster together by meaning and usage. “Cat” sits near “dog,” “king” near “queen.”

Your prompt drops a pin in that space. The model then navigates through those conceptual neighborhoods to assemble a response. Good prompting is essentially good navigation.

## The Workflow: Thinking Like an AI Engineer

### Block 1: Managing Temperature, or How Much Randomness You Allow

**Use this when you want control over creativity or precision.**

**Temperature guidelines:**

* **0.0:** Deterministic, or as close as you can get. Your friend for code, math, and anything you need to be repeatable.
* **0.7–1.0:** Open ended and creative. Useful for writing, ideation, and exploring options.

**How to work with it:**

1. Check your API parameters.
2. Use `temperature: 0` for code generation or anything correctness sensitive.
3. Use `0.8` (or nearby) for creative work.

### Block 2: Handling Context, or Managing State Yourself

Language models are stateless. They don’t remember anything unless you resend it.

**Two key concepts:**

* **The context window:** The text buffer you provide on every call.
* **The sliding window:** As conversations grow, old messages must be truncated to stay within token limits.

**How to work with it:**

1. Treat each API call as a fresh, cold start.
2. Include any history or data you want the model to reference.
3. Keep an eye on token usage and trim strategically.

### Block 3: Structured Outputs with JSON Mode

If you’re integrating a model into software, you want structured, parseable output.

**The pattern:**

* Tell the model to return valid JSON.
* Provide the schema you expect so the model has no ambiguity.

**How to work with it:**

1. Define your schema explicitly.
2. Include that schema in the system prompt or request metadata.
3. Parse and validate the output in your code.

## Caution: Avoid Anthropomorphism

It’s tempting to talk about what the model “thinks” or “believes,” but that framing will mislead you.

**Do not outsource:**

* **Belief:** The model doesn’t believe anything. It predicts text a human might produce.
* **Truth:** It doesn’t know what is fact. It only calculates probabilities.

Clear mental boundaries lead to clearer engineering decisions.

## The Tri Stage Checklist

### Before the Call

* [ ] **Mode Check:** Do I want precision (Temp 0) or creativity (Temp 1)?
* [ ] **State Check:** Did I include the history the model needs?

### During the Call

* [ ] **Parsing:** Am I prepared for probabilistic variation, including retries or fallbacks?

### After the Call

* [ ] **Validation:** Did I verify the JSON or structured output?

## Closing Activation

**Call the API.**
Don’t limit yourself to the chat interface. Pull an API key from OpenAI, Anthropic, or a local model like Ollama. Write a small script. Hit the API. Print the raw JSON. Inspect the tokens. See the probabilities yourself. Once you do that, the system stops feeling mystical and starts feeling like software again.

---

*Methodology Note: This article was drafted using the Unified Article Spec and refined for clarity.*

(created with AI)

View the source code on GitHub:
[ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)