# Day 14: Creative Iteration: How to Get Useful Work From a Model (Without Getting Generic)

Leo is staring at a draft that looks fine.

It has a clean headline, a decent hook, and sentences that flow.

It also feels like it could have been written for anyone.

This is the failure mode most people call “AI writing.” The model produces an average-shaped artifact, and you can’t find your own voice inside it.

Iteration with constraints is what turns that draft into something specific.

---

## The Only Part That Matters: The Second Draft

A model is good at first drafts. It can generate structure, phrasing, and options quickly.

The problem is that first drafts are where the model is most generic.

If you want something publishable, you need a loop that turns “plausible” into “specific.”

Here is the loop Leo uses when he wants output that survives a real reader.

Here is what that looks like in miniature:

**Before**

> "AI can help teams move faster by improving communication."

**After**

> "If you want AI to speed up real work, ask for artifacts you can inspect, like a sprint plan table, a review checklist, or a diff you can run through CI."

---

## A Practical Mental Model: Sculpting the Draft

Working with a model feels less like writing and more like sculpting.

You start with too much material, then you remove, sharpen, and impose boundaries until the shape matches what you meant.

That framing changes your behavior:

- You stop expecting the first output to be good.
- You start expecting the second and third passes to be where quality appears.
- You treat constraints as a tool that creates clarity.

---

## The Constraint Stack (Voice, Scope, Proof)

Use this when you have a decent draft that feels generic.

The goal is to stack a small set of constraints that force specificity.

```text
Role: You are a senior editor for a developer-facing blog.
Input: Here is my draft.

Task:
1) Rewrite for a competent technical reader.
2) Remove generic phrases and replace them with concrete language.
3) Add one proof artifact (choose one): a table, a before/after example, or a short scenario.

Constraints:
- Avoid buzzwords and hype.
- Avoid lazy contrast (X vs Y framing without proof).
- Do not add numbers, dates, or version claims unless the draft already includes a credible source link.
- Keep placeholders and code blocks unchanged.

Output:
- Return the full revised article.
```

Verification you can do immediately:

- Skim only the first sentence of each paragraph. If it still reads like generic advice, the constraints didn’t bite hard enough.
- Search for vague words you personally overuse (“leverage,” “unlock,” “transform,” “powerful”). Replace them with the concrete action you mean.

---

## Before/After Proof (Make the Upgrade Visible)

Use this when you want the reader to trust your recommendation.

A before/after example does more work than a paragraph of explanation.

Start with a tiny artifact: a prompt, a paragraph, a headline, a CTA.

```text
I will give you a BEFORE artifact and my goal.

Task:
1) Produce an AFTER version that matches the goal.
2) Explain the delta in 5 bullets, each bullet must reference a specific change you made.
3) List 3 “rules” the AFTER version followed.

Constraints:
- Do not claim the change is better. Demonstrate it by showing the change.
- No lazy contrast.

Format:
BEFORE:
AFTER:
DELTA:
RULES:
```

This creates a pattern you can reuse across posts: you prove you have taste by showing what you changed.

---

## The Critic Pass (Make It Argue Back)

Use this when your draft reads smoothly but feels unearned.

You want pushback that targets substance and decisions, beyond line edits.

```text
Role: You are a skeptical peer reviewer.
Input: Here is my draft.

Task:
1) Identify the 5 weakest claims.
2) For each claim, say what evidence would make it credible.
3) Flag any sections that feel like they could appear in any blog post.
4) Suggest one topic-specific header rewrite per major section.

Constraints:
- Keep your critique concrete. Point to sentences and explain why they are weak.
- If a claim needs a source, say so explicitly.

Output:
- A numbered list.
```

Verification step:

- If the critic can’t find any weak claims, it didn’t try. Ask it for “the harsh version” and require quotes.

---

## Guardrails: What You Still Own

Creative iteration still needs human ownership.

Keep these pieces human-led:

- **The point of view.** A model can remix patterns, but it can’t supply your lived constraints.
- **The risk calls.** You decide what’s safe to publish, what’s confidential, what’s speculative.
- **The final taste.** If you wouldn’t sign your name to a sentence, cut it.

---

## A Short Checklist Before You Publish

- [ ] Does the opener sound like a real moment with stakes?
- [ ] Did I include at least one proof artifact (table, before/after, scenario)?
- [ ] Did I remove generic “AI blog” language and replace it with concrete choices?
- [ ] Did I avoid lazy contrast?
- [ ] Did I remove unsourced specifics (numbers, dates, “as of” claims)?

If you run this loop a few times, you stop arguing about whether the model can write. You start shipping drafts you can actually stand behind.

---

*Methodology Note: This article was drafted using the Unified Article Spec v1.1 (Narrative Arc) and refined for clarity.*

(created with AI)

View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)
