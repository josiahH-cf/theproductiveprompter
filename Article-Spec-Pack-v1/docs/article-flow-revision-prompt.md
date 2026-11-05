# Optional GPT revision handoff

An ordinary publication remains COMPLETE. The later revision is optional and
has its own identity, checks and publication. Espansr supplies the prompt; GPT
edits; Article Flow validates, renders, publishes and verifies. Operational
handoff instructions stay outside the published article.

## Reusable Espansr prompt

```text
Help me revise an article on The Productive Prompter:
https://theproductiveprompter.com/docs/blog.html

First contextualize; do not edit yet. Unless I name another article, find the
most recently published article. Read its full body and inspect its existing
visuals where your tools allow. Open its "Article revision source (Markdown)"
link and retain the COMPLETE retrieved JSON, unchanged, as the source object
for the later return. Its article_markdown is the editing source; its optional
visuals describe the published diagrams. I should not have to upload or paste
source.json or article.md.

If the site or its source link cannot be read, use its public repository mirror:
https://raw.githubusercontent.com/josiahH-cf/theproductiveprompter/main/docs/blog.html
Select the same article, then fetch docs/SLUG.revision.json from that same
repository base. Add a fresh unique ?article-flow=REQUEST_TAG to mirror requests
to avoid a stale cached index or source. Keep the canonical article URL from
the source identity. Never invent identity fields, calculate source hashes
from browser-rendered text, or use an older article because retrieval failed.
If required source material is still missing, identify it; do not ask me to
supply backend files or claim you have everything.

After I give my thoughts, revise the complete article body in Markdown.
Preserve effective wording, factual qualifications, citations, quotations,
code, URL, original publication date and undeclared image assets. Keep my
actual feedback separate from generated text. Do not invent my experience,
opinions, facts, approval, or an exact model identity. Keep handoff instructions,
source metadata, navigation and commentary outside the article.

Improve or add a diagram when it helps explain my feedback or the article.
Keep existing image references unchanged unless explicitly replacing a diagram.
Use a semantic visual_plan for any new or replaced diagram; Article Flow renders
and checks it. Do not import SVG/HTML markup, arbitrary image URLs or Mermaid
code as a published image. You may show a separate readable diagram preview;
the returned semantic definitions are the publication input.

For each planned diagram supply visual_id (lowercase letters/digits/hyphens),
kind, title (at most 52 characters), purpose, design_rationale (at least 40
characters), placement (one exact after_heading or full after_paragraph from
the candidate), alt_text (20–320 characters), caption (10–320 characters),
claim_ids: [], and labels (2–8 distinct strings, each at most 90 characters).
For a general workflow use kind "workflow" and explicit edges:
[{"from":0,"to":1,"label":"optional"}], indexing labels from zero. Connect every
label; use at most 12 edges and four nonconsecutive branch/return edges.
An arrow exists only when you supply it; do not add an implicit return loop.
Fixed supported kinds are delivery_loop (2–8 steps, includes a return),
branching_effects (premise, two effects, combined implication), parallel_review
(eight roles), console_reconstruction (4–7 labels, disclose reconstruction),
and trend_gap (two labels). Use a fixed kind only when its topology is truthful.

visual_plan has exactly {"visuals":[...],"replace_assets":[...]}.
Leave replace_assets empty for additions. For replacement, list each existing
/assets/articles/SLUG/VISUAL_ID.svg path explicitly, use that same visual_id
in the new plan, and remove its old image/title/caption block from the candidate.
The controller inserts the revised diagram at its bound placement. Retain other
assets unchanged. Omit visual_plan entirely if no diagram changes are needed.
Describe unsupported changes or material conflicts separately; do not hide them.

Once we have finished the revision, show the readable revised article, then end
with ONE code block named article-flow-revision containing valid JSON:
{"article_flow_revision_version":"1.0.0","source":COMPLETE_RETRIEVED_SOURCE_JSON,
"candidate_markdown":"COMPLETE_REVISED_BODY","author_feedback":"MY_EXACT_FEEDBACK"}
Include visual_plan only when needed. Use the actual full values, no placeholders
or ellipses; escape Markdown newlines inside JSON strings. Copy the complete
retrieved source JSON as an object, including its original article_markdown.
Keep my feedback verbatim, joining multiple feedback messages in order with
two newlines. I can paste that single block, or the whole response, back into
Article Flow. The backend unpacks it, validates it, and automatically republishes
within my revision authorization. Failed checks retain the candidate for
resolution rather than silently rewriting it.

For your first reply, after contextualization, confirm you have everything you
need to get started, give the article's title, canonical link, original date and
a brief account of what it says, then ask for my thoughts. Stop and wait for my
reply before drafting or producing the return block.
```

## Copy-back intake

Save the received response verbatim to a private UTF-8 file. No separate source,
candidate or feedback attachments are required. Run:

```text
article-flow revise --handoff-file RETURNED_RESPONSE.md --unattended-editorial --authorization "ACTUAL AUTHOR INSTRUCTION" --auto --json
```

Use the author's actual authorization. The JSON return cannot authorize itself.
A raw JSON object is accepted too. A Markdown response must contain exactly one
closed `article-flow-revision` fence (backticks or tildes). Preview prose and
other code blocks are outside the intake. Duplicate fields, unsupported versions,
unknown fields, empty feedback, control characters and payloads over 2 MiB fail.
The backend separates immutable source, generated candidate, exact feedback and
optional diagram plan under its private runtime before source validation.

The required fields are `article_flow_revision_version: "1.0.0"`, `source`,
`candidate_markdown` and `author_feedback`. `source` is the complete retrieved
public wrapper: its unchanged identity, original body Markdown and optional
public diagram definitions. A legacy private export identity is also accepted.
Only `visual_plan` is optional. The legacy separate-file import remains supported.

Canonical input hashes, including any diagram plan, identify one intake across
Windows and WSL. Equivalent JSON formatting and a raw/fenced presentation unpack
to the same inputs. Exact retries return their owner and never resume a Stop.
An interrupted intake requires reconciliation of its reserved owner.

## Source and publication evidence

The source identity binds the canonical URL, slug, title, original timestamp,
source HTML and body Markdown digests, commit when known and observation time.
The importer checks committed, worktree and live HTML, supported original prose,
protected quotation/code evidence, citations and source images before any Run.
Stale or conflicting candidates are rejected. Never replace an identity or
weaken a check to accept a stale return.

The public `.revision.json` contains only public body text and diagram
definitions. It excludes feedback, authorization, hidden frontmatter, run paths,
private claim IDs and design rationale. The HTML binds its Markdown and, when
present, diagram-definition digests. A repository mirror is a retrieval fallback;
the backend still requires the current live page to match. A cache-busting
request tag is not source identity. Legacy pages without a public source need
their backend source made available; do not make the user paste internal files.

DRAFT retains the supplied candidate. Controller-owned visual materialization
may insert precisely the submitted image blocks; EDIT carries that result
without a new writer task. Factual, editorial, packaging, approval and exact
live checks still apply. A failed candidate stays held with its actual findings.
The public attribution says the revision was supplied in GPT and the exact
model is unverified. It establishes neither human-original writing nor a new
human voice preference.

## Diagrams

Diagrams use the existing visual-plan and manifest gates. An import's optional
plan has exactly `visuals` and `replace_assets`. Each visual follows
`schemas/visual-plan.schema.json`, includes its design rationale and uses
empty `claim_ids`: local claim IDs cannot be invented by an external chat.
Its content enters the ordinary research and verification boundary.

New `workflow` diagrams specify each directed edge explicitly. They can show
one-way steps, branches, joins and returns without forcing a loop. Labels are
laid out in order; arrows determine connectivity. The bounded renderer rejects
missing or disconnected nodes, self/duplicate/out-of-range edges and more than
four routed branch/return edges rather than dropping content. Fixed templates
remain available and preserve their established topologies. Supplied explicit
edges on a fixed template are rejected rather than ignored.

Replacing an image requires naming an existing verified controller SVG path
with a matching visual ID. The candidate omits that old diagram block; the
renderer inserts its replacement at the new exact anchor. Other images and
their alt text remain unchanged. Old replaced bytes are checked for drift until
publication, but only the new manifest asset is packaged and live-verified at
that path. No external markup, script, URL download or new dependency is added.

Public diagram definitions round-trip only visible text, placement, kind and
explicit edges. Retained source definitions survive a prose-only revision.
Inspect rendered arrows as well as text, caption and alt text. Source/manifest
checks cannot establish browser appearance; record that observation separately.

A pre-3.2.19 empty visual plan incorrectly claimed to preserve illustrations
when none existed. The controller can repair that exact metadata-only defect
under its bound editorial finding without rewriting accepted prose. Other
external-candidate failures keep their existing stop behavior.
