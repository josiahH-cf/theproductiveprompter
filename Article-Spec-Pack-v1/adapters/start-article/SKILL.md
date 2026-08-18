---
name: start-article
description: Start or resume The Productive Prompter article workflow. Use for $start-article, /start-article, or a request to turn a rough idea into a blog post.
---

# Start Article

This skill is a disposable pointer, not a copy of the article workflow.

1. In a local shell-capable environment, run `article-flow entrypoint --json`, open the returned file, and follow it.
2. If the managed command is unavailable or this is an account-hosted ChatGPT/Claude environment, load the current canonical entrypoint directly from:
   `https://raw.githubusercontent.com/josiahH-cf/theproductiveprompter/main/Article-Spec-Pack-v1/0-START-ARTICLE.md`
3. Follow that entrypoint as written. If neither source can be read, report the discovery failure and stop.

Do not cache, restate, or independently evolve the commands from the entrypoint in this skill. Never infer approval, bypass a hard gate, publish directly, or claim routing or live verification that the controller did not record.
