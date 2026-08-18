---
name: start-article
description: Start or resume the canonical The Productive Prompter article workflow through the local article-flow controller. Use when the user invokes $start-article or /start-article, asks to start or create a blog post from a rough idea, or says an idea could make a good article. Do not use this adapter as an independent writing prompt; the controller owns state, rules, gates, and side effects.
---

# Start Article

Use this skill only as a thin host adapter.

1. Run `article-flow doctor --scope authoring`.
2. If the user supplied an idea, pass it unchanged to `article-flow start --seed`. Otherwise run `article-flow start` and relay the controller's one-paragraph-or-less seed question.
3. Follow the controller response. Use `article-flow next RUN_ID --json` to obtain the next action and its complete task packet.
4. When the controller returns a model task, perform only that packet with the allowed tools and side-effect policy, save the requested observable output, then use the exact submission command returned by the controller.
5. When the controller returns a human decision, ask only its escalation question and submit only the user's confirmed answer or gate outcome.
6. Stop when the controller reports `COMPLETE`, `TERMINAL`, or an unresolved escalation.

Never copy workflow rules into this skill, infer approval, bypass a hard gate, publish directly, or claim model routing or live verification that the controller did not record.
