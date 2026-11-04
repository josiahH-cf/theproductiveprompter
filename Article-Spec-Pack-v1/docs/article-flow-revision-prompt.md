# Optional GPT revision handoff

Espansr owns only the reusable `:article-flow-revision` prompt. GPT reads the
published article and applies the author's free-form feedback. Article Flow
validates the returned candidate, publishes the same page and verifies the live
result. Expanding the prompt does not start an Article Flow run, publish an
article or leave the original publication waiting for edits.

## Reusable Espansr prompt

```text
Help me revise an article on The Productive Prompter:
https://theproductiveprompter.com/docs/blog.html

Unless I name another article, find the most recently published article. Open
and read the full article, including its links and visuals. Before editing,
confirm that you found and read it by giving its title, canonical link and
original publication date, followed by a brief account of what it says. If you
cannot read the full article or the target is ambiguous, say exactly what is
missing instead of guessing.

After that confirmation, open its "Article revision source (Markdown)" link.
Keep the complete JSON unchanged as source.json and use its article_markdown
as the editing source. If the link is unavailable, use the matching Article
Flow revision-export source.json and article.md when supplied. Never invent
source identity or calculate a hash from browser-rendered text.

Then use my stream-of-consciousness feedback as the editing direction. If I
have not provided it yet, invite me to give it in my own words. Keep my exact
feedback separate from your proposed article. Do not turn generated wording
into evidence that I wrote it or silently invent experiences, opinions or facts.

Revise the complete article in Markdown, preserving effective wording, factual
qualifications, citations, quotations, code and existing asset links. Preserve
the article's URL and original publication date. Do not return a full HTML
page or include navigation, page chrome or an explanatory cover note in the
article. Keep its body format; Article Flow supplies the page title and metadata. Describe any material conflict or unsupported addition separately.

Return three separate UTF-8 files: source.json unchanged, candidate.md with the
complete revised Markdown, and feedback.md with my exact feedback. If source
identity is unavailable, still complete the read confirmation and editing draft,
then explain that the matching revision-export is needed for an importable
return. Once I submit the requested revision to Article Flow, it should validate
and republish automatically. Failed checks or material conflicts must retain my
candidate and stop for resolution, not silently substitute another rewrite.
```

The initial confirmation establishes that GPT actually read the selected
article. It is not a second publication approval. Feedback already supplied in
the conversation may be used after the confirmation; otherwise GPT waits for
the author's feedback. Naming an older article overrides the newest-article
default and requires a handoff bound to that older page.

## Format and source binding

Markdown is the article format. Article Flow already checks Markdown and
renders it through its publication template. The public handoff omits every
renderer-hidden frontmatter field and binds its body digest separately in HTML. Its renderer escapes arbitrary
HTML, with narrow existing exceptions for source-bound evidence and
controller-owned panels. Returning a full HTML page would mix article content
with page structure and make round-tripping unreliable.

The handoff must be obtained from Article Flow's verified publication source.
It identifies one canonical URL, slug and exact source HTML hash. A matching
browser title or publication date alone is insufficient: neither detects an
intervening edit. GPT copies the controller's identity and supplies the
complete revised Markdown and exact author feedback in their separate files.
The importer checks the baseline again against committed, working-tree and
live bytes before creating or publishing a revision.

New publications include an `Article revision source (Markdown)` footer link
to `docs/<slug>.revision.json`. The JSON contains `source` and
`article_markdown`. Save this entire wrapper unchanged as `source.json`; the
importer accepts that public handoff directly. Its identity uses
`revision_source_version`, `canonical_url`, `slug`, `title`,
`original_published_timestamp`, `source_html_sha256`, `source_commit`,
`source_observed_at` and `source_markdown_sha256`. These are copied from the
controller, not authored by GPT. The public wrapper contains the public
article's body Markdown, never renderer-hidden frontmatter, private feedback or authorization.

For an older page without that footer, obtain a private export:

```text
article-flow revision-export --output-dir PRIVATE_EXPORT_DIR --json
```

This selects the newest published article from the verified live blog index.
For an explicit older article, add `--published-slug EXACT_SLUG`. The read-only
export writes `source.json` and `article.md`, using intact accepted source
Markdown or a supported lossless conversion of the verified HTML body. It
starts no run and publishes nothing. An unsupported or ambiguous source fails
for recovery rather than producing a guessed Markdown article. Supply both
files to GPT. Reading and editing may still proceed while an unavailable
handoff is resolved, but the result is a draft until it has a matching source
identity.

Keep the return files distinct:

- `source.json`: the unchanged public wrapper or private export identity.
- `candidate.md`: the complete revised article body, retaining citations and
  existing image references. It contains no feedback or identity envelope.
- `feedback.md`: the author's exact stream-of-consciousness feedback, retained
  verbatim and separately from generated prose and model commentary.

Submit the requested revision through the normal controller:

```text
article-flow revise --source-file source.json --candidate-file candidate.md --request-file feedback.md --unattended-editorial --authorization "ACTUAL AUTHOR INSTRUCTION" --auto
```

Replace the example authorization with the author's real instruction and use
the actual file paths. Do not manufacture approval text. The source-file
variant supplies the article identity; do not combine it with a source run ID,
`--published-slug` or `--expected-source-sha256`. A stale or conflicting source
is rejected before a revision run is created. Start from a fresh handoff and
deliberately reconcile the candidate when the published baseline changes.

The candidate is external generated prose. The author's verbatim feedback is
author-supplied direction. Review models and controller checks retain their
own provenance; importing the candidate does not make those models its
authors or establish a human voice choice. Existing citations and assets
remain subject to preservation and normal factual, editorial, rendering and
live checks. DRAFT and EDIT carry the supplied candidate's exact bytes through
their controller-owned path; review models do not receive permission to
replace it. A failure preserves the candidate for explicit resolution. The
public revision attribution states that text was supplied in GPT and its exact
model is unverified; accepting the file does not invent a model identity.

## Publication behavior

An ordinary successful publication reaches `COMPLETE` and may offer the
optional revision handoff. Declining or ignoring it requires no action and
creates no waiting revision. A later explicit revision submission creates its
own source-bound revision. Successful validation continues automatically to
the existing publication and live-verification owners, preserving the original
URL and first-publication timestamp. An explicit Stop, hold, failed check,
stale source, material conflict or uncertain effect retains its existing owner
and recovery rules.

This document is the source for the reusable prompt. Install or update it
through the active Espansr owner; do not write competing Espansr checkouts or
claim that a saved prompt file proves installed expansion.
