# An operational framework for AI-assisted problem solving

**The central question every AI practitioner faces is not "how do I use AI?" but "what class of solution does this problem demand, and where exactly should AI sit in it?"** This framework provides the granular decision logic to answer that question systematically. It synthesizes automation theory (Sheridan & Verplank, Parasuraman), decision theory, agent orchestration research (Anthropic, OpenAI, LangGraph), reliability engineering, and cognitive systems engineering into a unified operational model. The core insight: most AI failures stem not from poor prompting but from wrong method selection — using agents where workflows suffice, using AI where code belongs, or automating what should remain human-led. This framework replaces intuition with explicit decision surfaces.

---

## The seven decision surfaces practitioners actually face

Every AI-assisted task requires navigating seven distinct decision surfaces, each with its own variables and failure modes. Skipping any one produces the characteristic failures practitioners recognize: overengineered agents for simple tasks, hallucination-prone outputs where determinism was needed, or brittle automations that break on edge cases.

**Surface 1: AI suitability.** Should AI be involved at all? This is the gate most practitioners skip. The variables are output determinism requirements, error cost tolerance, verifiability of results, and whether the task reduces to known rules. If the task can be expressed as if/then logic with stable rules, traditional code is the correct answer — full stop.

**Surface 2: Problem type classification.** What is the fundamental nature of the work? Problems decompose into seven types: *reasoning* (deriving conclusions from premises), *retrieval* (finding and surfacing existing information), *transformation* (converting inputs between formats or representations), *search* (exploring solution spaces), *orchestration* (coordinating multiple steps or agents), *execution* (carrying out defined actions in external systems), and *generation* (producing novel content). Each type has a different optimal method. Reasoning problems favor chain-of-thought prompting. Retrieval problems favor RAG. Transformation problems often favor code generation. Search problems favor Tree-of-Thought or agent patterns. Orchestration problems favor workflow engines. Execution problems favor tool use with verification. Generation problems favor iterative prompting with evaluation loops.

**Surface 3: Automation level per cognitive stage.** Parasuraman, Sheridan, and Wickens's four-stage model — information acquisition, information analysis, decision selection, action implementation — reveals that tasks are not uniformly automatable. A single task may warrant **high automation for data gathering** (AI excels at search and retrieval), **medium automation for analysis** (AI synthesizes but human reviews), **low automation for decision-making** (human judges with AI advisory), and **medium automation for execution** (AI drafts, human finalizes). Treating the whole task as a single automation decision is the most common design error in production AI systems.

**Surface 4: Method selection.** Given the problem type and appropriate automation level, which specific approach — prompting, prompt chaining, code generation, RAG, agent, workflow automation, or hybrid — best fits? This is the decision surface most practitioners spend their time on, but it should come fourth, not first.

**Surface 5: Verification strategy.** How will you know the output is correct? Anthropic's research demonstrates that **the verification method must be defined before execution begins**, not after. The spectrum runs from fully deterministic verification (code with test suites) through rubric-based scoring (writing quality) to expert-judgment-only verification (strategic recommendations). The verification strategy constrains which methods are safe to use.

**Surface 6: Human-AI boundary design.** Where exactly does AI hand off to human, and vice versa? This is not a binary "human-in-the-loop or not" decision. It involves specifying checkpoints, veto windows, approval gates, and escalation triggers — calibrated to error cost at each step.

**Surface 7: Automation maturity positioning.** Is this a one-off task, a recurring process worth templating, a high-frequency workflow worth scripting, or a production system worth full automation? The answer determines investment level and architecture.

---

## When AI is the wrong answer: the suitability gate

The single highest-leverage decision in the framework is correctly identifying when AI should not be used. Practitioners operating at an advanced level need explicit exclusion criteria, not vague cautions.

**Hard exclusions — never use AI as the primary method when:**

The task requires **100% deterministic output reproducibility**. LLMs are inherently stochastic; even temperature=0 does not guarantee byte-identical outputs across inference calls. If regulatory or operational requirements demand identical outputs from identical inputs, use traditional code.

The task is **fully expressible as known, stable rules**. If you can write the complete decision logic as a flowchart or state machine, AI adds cost, latency, and unpredictability with zero benefit. This includes data validation, format conversion between known schemas, arithmetic, sorting, filtering, and rule-based routing with known categories.

**Error cost is catastrophic and output is not independently verifiable.** This is the critical conjunction. High error cost alone doesn't exclude AI (medical image analysis uses AI with high-stakes but independently verifiable outputs). Unverifiable output alone doesn't exclude AI (creative writing is unverifiable but low-cost). The combination — where an error causes irreversible harm *and* you cannot reliably detect it before it causes harm — is the hard exclusion zone. Examples: autonomous medication dosing without pharmacist review, financial transaction execution without reconciliation, legal filing without attorney review.

**Sub-millisecond latency is required.** LLM inference operates on the order of hundreds of milliseconds to seconds. Real-time control systems, high-frequency trading, and game physics engines cannot tolerate this latency.

The task demands **complete explainability for regulatory compliance**. Where regulations require step-by-step auditable decision logic (certain financial lending decisions, some medical device classifications), LLM reasoning does not meet the bar. Traditional decision trees with logged paths do.

**Soft exclusions — AI is probably wrong here, reconsider carefully:**

The problem is a **well-understood algorithm** where optimal solutions exist (shortest path, optimal scheduling with known constraints, cryptographic operations). AI cannot improve on proven algorithms and will produce inferior, non-guaranteed results.

**Volume × cost economics don't work.** If the task executes millions of times daily and a $0.001/call inference cost compounds to thousands of dollars, but a one-time engineering investment in traditional code solves it permanently, AI is economically irrational.

The task requires **perfect mathematical precision**. LLMs make arithmetic errors. Use them to set up calculations, then execute with code.

---

## First principles: twelve axioms for AI method selection

These axioms emerge from automation theory, reliability engineering, and empirical AI practice. They serve as the foundational logic underlying every downstream decision in the framework.

**Axiom 1: Start with the simplest viable method.** Anthropic's core guidance is unambiguous: "Find the simplest solution possible, and only increase complexity when needed. This might mean not building agentic systems at all." A well-crafted single prompt with retrieval and in-context examples is sufficient for most applications. The burden of proof is on complexity, not simplicity.

**Axiom 2: Verification capability constrains delegation scope.** This is the framework's most important operational rule, drawn from DeepMind's "contract-first decomposition" principle. Before delegating any sub-task to AI, define the verification method. If verification is too costly, subjective, or unreliable, either decompose further until work units match available verification capabilities, or keep the task human-led. **The unit of safe delegation is the unit of reliable verification.**

**Axiom 3: Automate information stages before decision stages.** Parasuraman's model demonstrates that automating information acquisition and analysis at high levels carries lower risk than automating decision selection and action implementation. This maps directly to AI practice: let AI gather, filter, summarize, and analyze. Keep humans in authority for consequential decisions and irreversible actions. Violating this ordering is the root cause of most AI deployment failures in enterprise settings.

**Axiom 4: Context is a liability, not just an asset.** Every token of context introduces potential for distraction, contradiction, and hallucination. Anthropic documents that for long contexts (>20K tokens), LLMs exhibit "lost-in-the-middle" effects where information in the center of context is processed less reliably. The principle: provide minimum necessary context, structured with clear delineation (XML tags, headers), with the most critical information positioned at the boundaries.

**Axiom 5: Deterministic orchestration with bounded agent execution.** McKinsey/QuantumBlack's two-layer architecture captures the mature pattern: workflow sequencing and state management must be deterministic code. Agents operate within bounded execution scopes. Agents excel at generating content within constrained problems; they fail at meta-level decisions about workflow sequencing. Never let agents decide what to do next in production systems — let them decide *how* to do what deterministic orchestration has assigned them.

**Axiom 6: Error compounds exponentially in chains.** Each step in a multi-step AI pipeline multiplies uncertainty. A 95%-accurate step chained five times yields approximately 77% end-to-end accuracy. This means: minimize chain length, add validation gates between steps, and prefer parallel verification (voting/consensus) for critical paths. Anthropic's evaluator-optimizer pattern exists precisely to address this.

**Axiom 7: Output-test grounding is non-negotiable for agents.** Autonomous agents must receive "ground truth" from the environment at each step — tool call results, code execution outputs, test suite results, API responses. An agent reasoning purely from its own prior outputs without environmental feedback will drift into confabulation. This is why coding agents with automated test suites outperform agents in domains without objective feedback signals.

**Axiom 8: Capability should escalate on evidence, not assumption.** Sheridan and Verplank's 10-level scale implies that trust must be earned incrementally. Start at level 2-3 (AI offers alternatives, human decides) and advance toward level 6-7 (AI executes with human veto) only after measured reliability in the specific task domain exceeds your error cost threshold. Automation bias research shows that even experts over-rely on AI when it has been presented as capable — nearly half of errors in AI-assisted work are associated with automation bias.

**Axiom 9: Recurrence justifies investment; one-off tasks should be cheap.** A task executed once justifies at most a single well-crafted prompt. A task executed daily justifies a template. A task executed hundreds of times justifies a scripted workflow. A task executed thousands of times justifies full automation engineering. Match investment to recurrence frequency × error cost × volume.

**Axiom 10: The bottleneck shifts as AI capability increases.** At low AI capability, the bottleneck is production speed. At moderate capability, it's specification precision — how clearly you can define what you want. At high capability, **the bottleneck is verification rigor** — your ability to confirm that outputs are correct becomes the binding constraint and the primary intellectual asset.

**Axiom 11: Probabilistic generation creating deterministic execution.** The "rule maker" pattern: when a task will be repeated, use AI to *generate* deterministic artifacts (code, rules, configurations, templates) rather than running AI inference on every execution. This captures AI's pattern recognition while eliminating per-execution stochasticity and cost.

**Axiom 12: Neither human nor AI failure modes should be ignored.** Fitts' MABA-MABA list and its critiques reveal a fundamental truth: allocating a task to automation because humans do it poorly (e.g., sustained vigilance) may create the paradox that humans must now perform that exact task — monitoring the automation. Design for the failure modes of the *combined* system, not just the individual components.

---

## Core variables that determine method selection

The following variables, assessed for each task, drive the downstream decisions in the framework. Advanced practitioners should internalize this taxonomy and assess it rapidly, not sequentially — most variables can be evaluated in seconds by an experienced operator.

**Task clarity** measures how precisely the desired output can be specified. Ranges from "I'll know it when I see it" (low — requires iterative generation) to "here is the exact JSON schema and validation rules" (high — may not need AI at all). Low clarity tasks push toward iterative/exploratory methods; high clarity tasks push toward deterministic methods or single-shot prompting.

**Output verifiability** is the single most consequential variable. It has four levels: *deterministically verifiable* (code with test suites, calculations, data transformations — safe for full AI delegation with automated checks), *rubric-verifiable* (writing quality, translation accuracy — safe for AI delegation with sampling review), *expert-verifiable* (medical analysis, legal reasoning, strategic recommendations — requires qualified human review), and *effectively unverifiable* (novel creative vision, ethical judgments, predictions about unprecedented situations — human must lead).

**Error cost asymmetry** captures not just the magnitude of failure but its directionality. False positives and false negatives often have radically different costs. A spam filter's false positive (blocking a legitimate email) may cost a deal; its false negative (letting spam through) is an annoyance. Signal detection theory's optimal criterion β* = [P(noise)/P(signal)] × [(V(correct rejection) - V(false alarm))/(V(hit) - V(miss))] formalizes this: set your acceptance threshold for AI outputs based on the asymmetric costs of each error type.

**Decomposability** assesses whether the task can be broken into independent subtasks. Three categories from Continue.dev's framework: *Type 1* tasks are narrow and straightforward (remove feature flags, write unit tests) — excellent for AI with minimal context. *Type 2* tasks are specific but context-dependent (debug this error, refactor to this pattern) — good for AI with provided context. *Type 3* tasks are large and open-ended (build authentication system, design data architecture) — must be decomposed into Type 1/2 before AI can contribute effectively. **Never assign Type 3 tasks directly to AI.** Always decompose first.

**State and side effects** captures whether the task reads from or writes to external systems. Pure transformations (text in → text out) are safe to retry and parallelize. Tasks that modify external state (database writes, API calls, file system changes) require idempotency design, rollback capability, and stricter verification before execution.

**Recurrence frequency** directly determines appropriate investment level: one-off (ad hoc prompt), weekly (prompt template), daily (scripted workflow), hourly or higher (fully automated pipeline). This is not just an efficiency consideration — it's a reliability consideration. A process executed once can tolerate manual verification. A process executed 10,000 times daily requires automated verification or it will silently accumulate errors.

Additional variables to assess rapidly: *input quality* (structured vs. messy), *latency tolerance* (seconds vs. minutes vs. hours), *domain stability* (stable rules vs. rapidly evolving), *tool dependence* (can be done with text alone vs. requires external API calls), *required memory/state* (stateless vs. needs cross-session persistence), and *exploration vs. exploitation orientation* (searching for the right approach vs. executing a known approach).

---

## The method selection model: eight methods and their decision criteria

This section provides explicit selection criteria for the eight primary methods available to AI practitioners, ordered from simplest to most complex. The first method that meets the task requirements is the correct choice — per Axiom 1, the burden of proof is on complexity.

**Method 1: Single-shot prompting.** A single LLM call with well-crafted instructions, optional few-shot examples, and structured output format. *Minimum conditions*: task fits in one context window, no external data or tools required, output format is specifiable, and acceptable quality achievable without iteration. *Problem shapes that fit*: classification, summarization, translation, simple generation, format conversion, question-answering from provided text. *Failure signals that indicate escalation needed*: output quality inconsistent across runs, task requires information not in context, multiple distinct reasoning steps produce cascading errors, output requires verification against external state. *Verification profile*: human review or rubric-based scoring. **This method handles approximately 60-70% of knowledge work AI tasks.**

**Method 2: Structured/chained prompting (workflows).** Multiple LLM calls in a predefined sequence with validation gates between steps. Includes prompt chaining, routing, and parallelization patterns. *Minimum conditions*: task decomposes into 2-7 predictable sequential or parallel steps, intermediate outputs are verifiable, routing logic is known in advance. *Problem shapes that fit*: research-then-write, extract-then-validate-then-format, classify-then-route-to-specialist-prompt, multi-criteria evaluation with aggregation. *Failure signals*: subtasks can't be predicted in advance (need orchestrator-worker), quality degrades and iteration is needed (need evaluator-optimizer), routing categories aren't stable (need adaptive routing). *Verification profile*: automated intermediate checks plus final human review. *Key implementation detail*: validation gates between steps are not optional — they are the mechanism that prevents error compounding (Axiom 6).

**Method 3: Code generation (AI at build time).** Use AI to generate deterministic artifacts — code, rules, configurations, templates — that then execute without AI inference. *Minimum conditions*: the transformation logic, once identified, is stable and will be reused; output must be deterministic; performance or cost requires eliminating per-call inference. *Problem shapes that fit*: data pipeline transformations, repeated format conversions, business rule implementation, test generation, infrastructure-as-code, regex/pattern generation. *Key decision*: if you find yourself running the same prompt repeatedly with different inputs, this is a signal to switch from Method 1 to Method 3 — have AI generate the code once, then run the code. *Failure signals*: generated code doesn't handle edge cases (need human review of generated code), rules evolve faster than code update cycle (stay with runtime AI). *This is the most underused method by practitioners* — the "rule maker" pattern of probabilistic generation creating deterministic execution.

**Method 4: RAG (retrieval-augmented generation).** LLM generation grounded in dynamically retrieved context from external knowledge bases. *Minimum conditions*: task requires knowledge not in the model's training data or that changes frequently, corpus exceeds context window size, source attribution is needed. *Problem shapes that fit*: enterprise Q&A over internal documents, customer support with product knowledge bases, research synthesis over large corpora, compliance checking against current regulations. *Failure modes to monitor*: retrieval failures (correct document not in top-K — use hybrid search with reranking), lost-in-the-middle (critical info in center of long context — use strategic context ordering), context poisoning (too many near-duplicate fragments — use contextual compression and deduplication), scattered evidence (answer requires synthesis across many documents — use multi-query decomposition). **80% of enterprise RAG projects end in failure**, primarily due to poor data quality (42% of failures), naive chunking strategies, and inadequate evaluation. Advanced RAG with hybrid search and reranking reduces irrelevant passages from 30-40% to under 10%. *When NOT to use RAG*: information fits in context window and is static, domain is well-covered by training data, simple prompting achieves acceptable results, real-time latency requirements preclude retrieval overhead.

**Method 5: Tool-augmented generation.** LLM with access to external tools (APIs, databases, code execution, web search) for retrieving real-time information or taking actions. *Minimum conditions*: task requires interaction with external systems, real-time or dynamic data, or operations with side effects. *Distinction from RAG*: RAG retrieves from a prepared knowledge base; tool use interacts with live systems. *Problem shapes that fit*: tasks requiring current data (weather, stock prices, live status), multi-system coordination (CRM + calendar + email), any task requiring computation (execute code rather than having LLM calculate). *Key constraint*: below **100 tools and 20 arguments per tool** is the reliable operating envelope; beyond this, use tool search for dynamic tool discovery. *Failure signals*: tool errors derail reasoning chain (add error handling and retry logic), tool call latency dominates end-to-end time (consider caching, batching, or precomputation), model selects wrong tool (improve tool descriptions, add explicit priority in system prompt).

**Method 6: Evaluator-optimizer loop.** One LLM generates output; another evaluates against defined criteria; iteration continues until criteria are met. *Minimum conditions*: clear evaluation criteria exist, iterative refinement produces measurable improvement, and the additional cost of multiple generations is justified by quality requirements. *Problem shapes that fit*: translation quality refinement, code optimization, writing to specific style guides, any task where "good enough" on first attempt is insufficient but "better" is objectively measurable. *Failure signals*: evaluation criteria are subjective or unstable (loop won't converge), quality plateaus after 1-2 iterations (simpler method with better prompting would suffice), cost of N iterations exceeds value of quality improvement.

**Method 7: Autonomous agents.** LLMs dynamically directing their own process and tool usage in a feedback loop, gaining ground truth from the environment at each step. *Minimum conditions*: the problem is genuinely open-ended, required steps cannot be predicted in advance, environmental feedback is available at each step, cost and latency tolerance is high, and the task operates in a trusted environment. *Problem shapes that fit*: software engineering with test suites (agent writes code, runs tests, iterates), open-ended research with web access, complex debugging requiring exploratory investigation. *Failure modes*: repetitive action loops (add step limits and loop detection), compounding errors without ground truth (Axiom 7 — agent must get environmental feedback), cost explosion on complex tasks (set token/cost budgets), "agents' autonomy means higher costs, and the potential for compounding errors" (Anthropic). *When agents are wrong*: if the steps are predictable, use a workflow. If the task doesn't have objective environmental feedback, the agent will confabulate progress. **Agents are the method of last resort, not first resort.**

**Method 8: Scheduled automation with AI components.** Fully automated pipelines that run on triggers or schedules, incorporating AI at specific bounded steps within deterministic orchestration. *Minimum conditions*: task recurs at high frequency, end-to-end workflow is stable, error handling and fallback paths are designed, monitoring and alerting are in place. *Problem shapes that fit*: daily report generation, automated content moderation, scheduled data enrichment, triggered customer response drafting. *Key architecture*: deterministic workflow engine (n8n, Temporal, Prefect) handles orchestration, state, retries, and monitoring. AI is invoked at specific nodes for generation, classification, or analysis — bounded and verified before the next step proceeds. *Failure signals*: edge cases accumulate silently (add sampling-based human review), model behavior drifts over time (implement semantic drift detection), error handling is insufficient (design circuit breakers and dead letter queues).

---

## The operational process: eight steps from goal to production

This step-by-step process applies to any AI-assisted task, from a single prompt to a production automation. Steps 1-4 are planning; steps 5-8 are execution. Advanced practitioners often compress steps 1-4 into seconds for familiar task types, but should expand them deliberately for novel or high-stakes tasks.

**Step 1: Define the goal as a verifiable outcome statement.** Not "summarize this document" but "produce a 200-word summary that includes all action items, named entities, and deadlines, verified by checking each item against the source." The outcome statement must include success criteria. If you cannot articulate success criteria, you are not ready to delegate to AI — you are still in the problem definition phase (a human activity).

**Step 2: Classify the problem and assess core variables.** Apply the problem type taxonomy (reasoning/retrieval/transformation/search/orchestration/execution/generation). Assess the five critical variables: output verifiability, error cost asymmetry, decomposability, state/side effects, and recurrence frequency. This assessment takes 15-60 seconds for an experienced practitioner and determines everything downstream.

**Step 3: Run the suitability gate.** Check hard and soft exclusions. If the task is rule-based with stable logic, stop and use code. If error cost is catastrophic and output is unverifiable, stop and keep human-led. If deterministic reproducibility is required, stop and use traditional engineering. This step has an asymmetric payoff: catching a misfit early saves hours; missing it costs the same hours plus debugging time.

**Step 4: Select method and design verification.** Use the eight-method model above. Select the simplest method that satisfies the task requirements. Simultaneously design the verification strategy — these must be co-determined. For deterministically verifiable outputs, design automated tests. For rubric-verifiable outputs, define the rubric. For expert-verifiable outputs, identify the reviewer and allocate their time. The verification design often reveals that the initially selected method is wrong — this is a feature, not a bug.

**Step 5: Assemble context and constraints.** Build the minimum necessary context package: relevant data, examples, format specifications, constraint boundaries, and persona/role instructions. Apply Axiom 4: less context is better, provided it's complete. Structure with clear delineation. For documents over 20K tokens, instruct the model to extract relevant quotes before reasoning. Place the core question after the reference material.

**Step 6: Execute with monitoring.** Run the selected method. For single-shot prompting, this is one call. For workflows, execute the chain with gate checks. For agents, monitor trajectory and cost. Key operational habit: read the full output before accepting. Automation bias research shows that even experts stop scrutinizing outputs after AI establishes a track record — which is precisely when subtle errors begin accumulating undetected.

**Step 7: Verify against success criteria.** Apply the pre-designed verification strategy from Step 4. For code outputs, run the test suite. For written outputs, apply the rubric. For analytical outputs, check key claims against sources. **If verification reveals systematic failures, diagnose whether the problem is in the method (escalate complexity) or the specification (refine the prompt/instructions)**. Most failures are specification failures, not method failures.

**Step 8: Decide on iteration, productization, or termination.** If the output is satisfactory and the task is one-off, stop. If the task recurs, invest in the next maturity level: save the prompt as a template, build a workflow, or engineer an automation. Apply the recurrence threshold from Axiom 9. Each productization step should be justified by frequency × value.

---

## Decision tree: branching logic for common scenarios

Rather than a single monolithic tree, experienced practitioners use a series of rapid binary-branch assessments. Here are the critical branching sequences:

**Branch 1 — Is AI appropriate at all?** If the task has stable, expressible rules AND requires deterministic output → use traditional code. If the task requires sub-millisecond latency → use traditional code. If the task involves unstructured input, judgment, or pattern recognition → proceed to Branch 2.

**Branch 2 — Can a single prompt solve it?** If all necessary information fits in context AND the task is a single reasoning step AND output quality is acceptable on first attempt → use Method 1 (single-shot prompting). If not → proceed to Branch 3.

**Branch 3 — Is the task decomposable into predictable steps?** If yes AND steps are sequential → use Method 2 (prompt chaining). If yes AND steps are independent → use Method 2 (parallelization). If the task requires different handling for different input types → use routing. If steps are not predictable → proceed to Branch 5.

**Branch 4 — Does the task require external knowledge?** If knowledge is in a prepared corpus → use Method 4 (RAG). If knowledge requires real-time system interaction → use Method 5 (tool-augmented generation). If both → use agentic RAG (Method 5 with retrieval tools).

**Branch 5 — Can the output be objectively evaluated?** If yes AND iteration improves quality → use Method 6 (evaluator-optimizer). If the problem is open-ended AND environmental feedback is available at each step → use Method 7 (agent). If environmental feedback is not available → decompose the task further until verification is possible at each sub-step, then use Method 2 or 6.

**Branch 6 — Build-time or runtime AI?** If the transformation will be repeated many times with different inputs → use Method 3 (code generation) — have AI create the code, then run the code. If every invocation is genuinely unique → use AI at runtime (Methods 1, 4, 5, or 7).

**Branch 7 — What level of human involvement?** If error cost is negligible → AI autonomous with periodic sampling review. If error cost is medium → AI generates, automated checks run, human spot-checks samples. If error cost is high → AI generates, human reviews every output before action. If error cost is catastrophic → human decides, AI provides information and options only (Sheridan-Verplank levels 2-4).

---

## Automation maturity: the five-level progression

The path from manual to autonomous follows a consistent maturity model. Each level has threshold criteria that must be met before advancement is safe. Advancing prematurely is worse than staying at a lower level — the failure modes of premature automation (silent errors, undetected drift, cascading failures) are more costly than the inefficiency of manual processes.

**Level 1: Manual with ad hoc AI.** The practitioner uses AI conversationally, copying and pasting between tools, writing prompts from scratch each time. No templates, no saved workflows, no systematic verification. *This level is appropriate for*: exploration, one-off tasks, tasks still being understood. *Advancement criteria to Level 2*: you've performed the task 3+ times with AI, output quality is predictable, and you can articulate the prompt pattern that works.

**Level 2: Templated prompts with documented patterns.** Reusable prompt templates are saved, version-controlled, and shared. Input variables are clearly separated from fixed instructions. Output format is standardized. *This level is appropriate for*: recurring tasks with consistent structure, team-shared processes, any task worth doing more than weekly. *Advancement criteria to Level 3*: the task runs daily or more, the template is stable (hasn't changed in 2+ weeks), intermediate steps are well-understood, and you've documented failure modes and their fixes.

**Level 3: Scripted workflows with automated execution.** Deterministic workflow engines (n8n, Zapier, Make, or custom code) handle the orchestration. AI is invoked at specific nodes. Error handling, retry logic, and logging are implemented. *This level is appropriate for*: high-frequency tasks with stable workflows, multi-system integration, any task where manual execution introduces unacceptable delay or error. *Advancement criteria to Level 4*: workflow has been stable for 1+ month, error rate is measured and below threshold, edge cases are catalogued and handled, monitoring and alerting are in place.

**Level 4: Intelligent automation with adaptive routing.** AI-driven classification determines routing and processing paths. Confidence-based human-in-the-loop: low-confidence outputs are automatically routed for human review. Feedback loops from human corrections improve routing accuracy over time. *This level is appropriate for*: high-volume processes where input variability requires adaptive handling, where human review capacity is the binding constraint, and where the system has accumulated sufficient data for reliable confidence scoring. *Advancement criteria to Level 5*: false positive rate below organizational threshold, human review confirms AI decisions >95% of the time for routed cases, monitoring detects drift within hours.

**Level 5: Autonomous with human-on-the-loop oversight.** Self-optimizing workflows with continuous evaluation, automatic error detection, and human intervention only on exceptions or scheduled audits. *This level requires*: comprehensive monitoring dashboards, semantic drift detection, automated regression testing suites, clear escalation paths, and organizational trust built through demonstrated reliability at Level 4. *Warning from reliability engineering*: this level creates the automation complacency paradox — the more reliable the system, the less vigilantly humans monitor it, creating vulnerability to rare failures. Countermeasures include mandatory periodic manual review (even when unnecessary), rotation of reviewers to maintain engagement, and deliberate injection of test cases that should trigger human intervention.

---

## Verification-first architecture: the framework's load-bearing principle

If there is one operational principle that separates production-grade AI systems from demonstrations, it is this: **design the verification architecture before designing the generation architecture.** This principle, drawn from DeepMind's intelligent delegation research and Anthropic's eval-driven development approach, inverts the common workflow where practitioners build the AI pipeline first and add evaluation as an afterthought.

The practical implementation follows Anthropic's three-grader taxonomy. **Code-based graders** (string matching, binary tests, schema validation, outcome verification) are fast, cheap, and reproducible — use them everywhere possible. **Model-based graders** (rubric scoring, pairwise comparison, natural language assertion checking) are flexible and capture nuance — use them for open-ended outputs where code-based grading would be brittle. **Human graders** (expert review, A/B testing) are the gold standard — reserve them for calibrating the other graders and for high-stakes decisions where the cost is justified.

The "Swiss cheese model" from reliability engineering applies: no single evaluation layer catches every issue. Production systems need **automated evals for every run**, **production monitoring for drift detection**, **user feedback integration for real-world signal**, and **periodic human transcript review to verify that graders themselves remain accurate**. Anthropic reports that evaluation bugs are more common than agent bugs — their Opus 4.5 model jumped from 42% to 95% on CORE-Bench after fixing grading issues, not model issues.

Start with **20-50 simple evaluation tasks drawn from real failures** — this is sufficient for initial eval-driven development. Convert every bug report and manual correction into a test case. Build balanced problem sets testing both "should-trigger" and "shouldn't-trigger" conditions. Grade what the agent produced, not the path it took. Track **pass@k** (probability of at least one success in k attempts) for tasks where any success matters, and **pass^k** (probability all k trials succeed) for customer-facing agents needing consistency.

---

## Conclusion: what this framework changes

The conventional approach to AI-assisted work treats method selection as a skill learned through trial and error — practitioners develop intuition about what works through repeated experiments. This framework replaces intuition with explicit decision logic, not to eliminate judgment but to ensure that judgment is applied at the right decision surfaces.

Three non-obvious implications emerge from the synthesis. First, **the verification architecture is the durable asset, not the generation pipeline.** As AI models improve, generation methods will change. But the evaluation suites, test cases, and quality rubrics that define "correct" for your domain persist across model generations. Invest accordingly.

Second, **most practitioners are under-using code generation (Method 3) and over-using agents (Method 7).** The "rule maker" pattern — using AI once to generate deterministic code, then running the code repeatedly — eliminates the cost, latency, and stochasticity of runtime AI for the large class of problems where the transformation logic is stable once identified. Meanwhile, agents are deployed for tasks with predictable steps where a simple workflow would be faster, cheaper, and more reliable.

Third, **the bottleneck migration effect means that AI proficiency increasingly depends on specification and verification skills, not prompting skills.** As AI handles production, the binding constraint shifts to the practitioner's ability to precisely articulate what "correct" means and rigorously verify that outputs meet that standard. The framework's emphasis on defining verifiable outcome statements (Step 1) and designing verification before generation reflects this shift. The practitioners who thrive will be those who can write excellent test suites and evaluation rubrics — the same skills that distinguish senior from junior software engineers, now applied to a much broader class of knowledge work.