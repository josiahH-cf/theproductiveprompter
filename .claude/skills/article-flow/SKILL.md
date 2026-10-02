---
name: article-flow
description: Start, resume, revise, or inspect The Productive Prompter article workflow, including automatic model-release articles and their preserved experiments. Use for $article-flow, /article-flow, or a request to use the named Article Flow workflow.
---

Run the installed article-flow command with no arguments and follow its returned protocol and exact command arrays. The controller owns task packets, decisions, publication, and live verification.

For ordinary new articles, preserve the supplied seed verbatim in the returned start_command. If no idea was supplied, present the returned question and wait. For an existing run, preserve its stored seed and inspect or resume its run ID. Inspection does not start an article.

For a new-model article or automatic model-release campaign, use the returned model_release_command. It publishes a researched article in the author's approved voice, verifies it, runs only missing frozen-prompt model/settings trials, and republishes the linked model cards and immutable run pages. This author explicitly authorized automatic approved-voice reuse for model-release articles; ordinary articles retain their voice choice. Supply an exact --model ID only when the user specifies one; never substitute a successor. A custom article seed can be supplied as a UTF-8 --seed-file. Read the final controller report; no live URL is established until verified.

If the command does not resolve, use article-flow.cmd on native Windows or /home/josiah/.local/bin/article-flow in WSL. In Git Bash use article-flow.cmd, including in returned arrays. If local command execution is unavailable, report that limitation. Read article-flow --help for inspection or revision commands.

For perform_task, read only the task_packet, create the expected_output, then execute submission_command. Wait for an ongoing stage before resuming or retrying. For a normal human_decision, present all three exact passages through the host's selectable-question tool and wait for the author's actual answer; elapsed time and a preselected option are not answers. Continue with the returned command after selection.

Honor explicit holds and blockers. Keep publication and verification inside the controller. The retired start-article adapters stay retired; article-flow is the surviving entry point.

For a model-release campaign's routine source, citation, or formatting repair that the authorized inputs resolve, follow the returned repair command, obtain its new task packet, submit the repaired current artifact, and resume the campaign. Preserve unaffected content and original experiment records. Ask only for a genuinely missing material decision or source; never invent a gate PASS.
