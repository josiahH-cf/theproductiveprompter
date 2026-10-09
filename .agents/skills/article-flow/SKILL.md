---
name: article-flow
description: Start, resume, revise, inspect, or improve The Productive Prompter Article Flow workflow, including evidence-backed author voice, bounded editorial collaboration, article maintenance, and automatic model-release articles. Use for $article-flow, /article-flow, or requests to use Article Flow.
---

Run the installed article-flow command with no arguments and follow its returned protocol and exact command arrays. The controller owns task packets, decisions, publication, and live verification.

For ordinary new articles, preserve the supplied seed verbatim in the returned start_command. If no idea was supplied, present the returned question and wait. For an existing run, preserve its stored seed and inspect or resume its run ID. Inspection does not start an article.

For a new-model article or automatic model-release campaign, use the returned model_release_command. It publishes a researched article using the pinned voice guide authorized by the author, verifies it, runs only missing frozen-prompt model/settings trials, and republishes the linked model cards and immutable run pages. This author explicitly authorized automatic approved-voice reuse for model-release articles; ordinary articles retain their voice choice. Supply an exact --model ID only when the user specifies one; never substitute a successor. A custom article seed can be supplied as a UTF-8 --seed-file. Read the final controller report; no live URL is established until verified.

If the command does not resolve, use article-flow.cmd on native Windows or /home/josiah/.local/bin/article-flow in WSL. In Git Bash use article-flow.cmd, including in returned arrays. If local command execution is unavailable, report that limitation. Read article-flow --help for inspection or revision commands.

For perform_task, read only the task_packet, create the expected_output, then execute submission_command. Wait for an ongoing stage before resuming or retrying. For a normal human_decision, present all three exact passages through the host's selectable-question tool and wait for the author's actual answer; elapsed time and a preselected option are not answers. Continue with the returned command after selection.

Honor explicit holds and blockers. Keep publication and verification inside the controller. The retired start-article adapters stay retired; article-flow is the surviving entry point.

For a model-release campaign's routine source, citation, or formatting repair that the authorized inputs resolve, follow the returned repair command, obtain its new task packet, submit the repaired current artifact, and resume the campaign. Preserve unaffected content and original experiment records. Ask only for a genuinely missing material decision or source; never invent a gate PASS.

For editorial improvement, use `article-flow editorial --help` and read [the editorial reference](references/editorial.md). The run-pinned compact profile owns voice; the article contract owns audience, register, person, form and author angle. Do not import archived prompt bodies, full profile history or candidate labels into prose instructions. Treat generated articles and selected AI paragraphs as generated evidence, not human-original writing.

For ordinary articles, show the actual A/B/C choices and wait for the author's answer. A choice applies locally and creates a pending reusable-learning proposal. Never supply human reasons or confirmation on the author's behalf. Once the answer arrives, continue automatically through publication; do not introduce another routine approval.

If the user explicitly delegates an unattended revision, use `revise --unattended-editorial --authorization` with their actual instruction and the scoped request file. Reuse the pinned guide without claiming a human voice choice or quality judgment. This exception applies to that revision only. Honor review-before-publication requests with `--hold-before-publish`; release the hold only within the existing authorization after the required review.

For a published article without a usable completed run, use the verified `revise --published-slug --expected-source-sha256` variant described in the editorial reference. Never resume or mark an old run complete merely to revise its live page. Preserve the verified current first-publication timestamp, source-bound quotations/code and original URL. Collection revisions use article-specific reader/register briefs under one guide and publish serially; approval or publication does not create new human voice evidence.

Use optional AI help for a concrete uncertainty: an argument rehearsal, one focused critic, reader simulation, or local alternatives. Keep one lead writer responsible for accepting/rejecting findings. Missing reasoning and supplied author perspective belong before claim locks; later prose editing preserves effective distinctive phrasing. Simulated readers are hypotheses. A fluent rewrite, successful gate or publication is not proof of author resemblance.

For feedback and weekly improvement, retain actual before/after and deliberately kept passages with the author's reason. Record the actual actor; inferred reasons and author judgments remain pending. Propose at most one scoped reusable change, check retained examples and a different form, then await actual human confirmation. Use maintenance source events on request; do not create schedules or publish merely because a source changed.

For visual review, inspect the actual rendered SVG relationships as well as the prose, plan, caption and alt text. Do not treat a renderer or QA PASS as proof that arrows represent the explanation. For a held editorial article, `amend RUN_ID --diagrams auto|off --reason "SPECIFIC FINDING"` reopens visual planning from EDITORIAL_QA, PACKAGE or PUBLISH_APPROVAL while preserving current prose and renewing downstream verification. The reason is a bound model input. Include a useful corrected diagram or record an article-specific omission; source inspection cannot prove browser appearance.

For a late missing-reasoning finding in a held editorial run, use `amend RUN_ID --reopen-development --reason "SPECIFIC FINDING"` to return to DRAFT and renew downstream checks. Preserve the current article and protected evidence; do not develop content by weakening final-edit locks.
