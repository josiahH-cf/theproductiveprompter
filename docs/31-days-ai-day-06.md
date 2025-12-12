# Day 06: Managing Context (Tokens, Memory, and Amnesia)

## The Core Constraint: No Long-Term Memory
Here's the reality: AI has no long-term memory of you or your work. It won’t remember your project from last week, your coding style, or your business goals—unless you explicitly include those details in the current conversation. Each new chat is like talking to a brilliant expert with amnesia: they’ve read every book in the library, but they forget everything you told them as soon as the conversation ends.

## Two Mental Models
1. **The Amnesiac Expert:** Think of a world-class consultant who forgets everything as soon as they leave the room. If you want good results, you have to brief them from scratch *every single time* you start a new discussion.  
2. **LEGO Bricks (Tokens):** AI reads text in chunks called *tokens* (rather than word by word). Rough conversions vary by language and content, so treat any token-to-word estimate as approximate. You pay for tokens (in money or in compute resources), and every model has a limit on how much it can handle at once—that limit is the model’s **context window**.

## Context Management
Managing context is an ongoing task when working with AI. Here’s a three-part workflow to keep the model on track:

### 1. Estimating the "Budget" (Token Awareness)
**When/Why:** Before you paste a massive block of text or code. If your input exceeds the model’s context window (its token limit), the AI will have to *“forget”* the beginning to make room for the end.

**The Pattern:**  
- **Rule of Thumb:** Tokenization varies by model and language. If you need accuracy, use your provider’s tokenizer or usage reporting.  
- **Quick Check:** If your input is novel-length (tens of thousands of words), it’s likely too much to feed at once—split it into smaller chunks or summarize it.

**The Steps:**  
1. Know your model’s context window (max token capacity). Check your provider’s docs for the exact limit.  
2. If your input is huge, stop and ask yourself: **do I really need everything, or just the relevant parts?**  
3. Only provide the content that’s necessary for the task at hand. In context management, *less is more*.

### 2. The "Mid-Project Summary" (Compressing Context)
**When/Why:** Use this after a long, winding session (e.g. after dozens of back-and-forth messages). The conversation may be getting convoluted, and the AI is starting to lose track or even hallucinate details from earlier in the discussion.

**The Pattern:**  
```markdown
We've covered a lot of ground on [Project Name].
Task: Summarize the key decisions we've made, the code structure we've agreed on, and the immediate next steps.
Format it as a concise "Context Brief" I can paste into a new chat to continue our work.
````

**The Steps:**

1. Give the AI the prompt above to generate a summary.
2. Copy the AI’s output (the summary brief).
3. Open a **new** chat session.
4. In the new chat, paste the summary and send a message like: *"Here is the context for our project. Now let's continue with [your next task or question]."*

### 3. Iterating (The "Sculptor's Mindset")

**When/Why:** The first answer you get is usually not perfect. Rather than scrapping your prompt and starting over, stay in the same chat and iteratively refine the output.

**The Pattern:**

```markdown
That's a good start, but [Critique]. Now please rewrite the response with the following changes:
1. Change [X] to [Y].
2. Expand on section [Z].
3. Keep the tone [Adjective].
```

**The Steps:**

1. Treat the AI’s initial output as a draft, not the final answer.
2. Point out exactly what needs to be changed or improved. Be specific in your feedback.
3. Remember, the AI still has that draft in its context, so it can apply your feedback and produce an improved result.

## What Not to Outsource

**Don't outsource your project history.** Never assume the AI will remember your past decisions in a new session. Keep your own "Project Bible"—a running document of key decisions, requirements, and facts—so you can reintroduce crucial details whenever you start a fresh chat.

## Quick Checklist

* **Before:** Do I have a "Context Brief" prepared and ready to paste if needed?
* **During:** Is the conversation getting unwieldy or off-track? (Signs include the AI forgetting instructions or repeating itself. If so, it’s time to summarize and reset with a fresh chat.)
* **After:** Did I save the final output outside the chat? (Remember, chat history is not a reliable file storage system.)

## Next Step

Go to one of your lengthy AI chat threads and scroll to the bottom. Ask the AI: **"Summarize the key takeaways of this discussion in a 3-bullet briefing."** Once it responds, save those bullet points as a handy "Context Brief" for that topic.

---

*Methodology Note: This article was drafted using the Unified Article Spec and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)