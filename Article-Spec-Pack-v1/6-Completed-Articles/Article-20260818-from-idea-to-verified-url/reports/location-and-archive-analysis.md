# Publication Location and Archive Analysis

**Article:** From Idea to Verified URL: Build a Blog Workflow That Still Sounds Like You

**Decision date:** 2026-08-18

**Public URL:** `https://theproductiveprompter.com/docs/from-idea-to-verified-url.html`

## Decision

Publish the article at a dedicated, permanent HTML URL and make it the leading item on both the homepage and blog hub. Keep 31 Days of AI immediately visible as a completed series. Do not move, rename, delete, or redirect any of its 31 article URLs.

“Archive” is an information hierarchy here, not a storage operation. It tells readers that the series is complete while preserving the series landing page and every original entry.

## Reader hierarchy

```text
Homepage Blog section
├── Latest article: From Idea to Verified URL
└── Completed series: 31 Days of AI (31 entries · all visible)

Blog hub
├── Latest writing
│   └── From Idea to Verified URL
└── Completed series archive
    └── 31 Days of AI → all 31 original links

Article page
├── Back to all writing
└── Related completed series → 31 Days of AI
```

This gives the new article editorial priority without asking a reader to infer that the old project disappeared. The relationship is reciprocal: the blog hub leads to the series, and the new article closes with a visible route back to it.

## Look and feel

- Preserve the site's existing dark navy, mint-accent, card-based visual language.
- Present the latest article as a large feature card with date, reading time, topic labels, a simple workflow-node visual, and one direct reading action.
- Present the completed series as a shorter shelf-style banner so it remains prominent without competing with the latest post.
- Use explicit status copy—“Completed,” “31 entries,” and “all visible”—instead of relying on the word “archive” alone.
- Keep the series landing page celebratory and browsable, with a short note explaining that every entry remains at its original link.
- Preserve a one-column reading experience and a single-column mobile archive grid.

## URL and archive invariants

- The 31 Days landing page remains at `/docs/31-days-of-ai.html`.
- All 31 article links remain in the form `/docs/article.html?post=31-days-ai-day-NN.md`.
- All 31 Markdown source files remain in `docs/`.
- The legacy shared viewer remains available and now returns readers to the correct series landing page.
- The sitemap lists the series landing page and every existing article URL.
- No redirect layer is necessary because no public route changes.

## Why the new article gets a different page type

The legacy series viewer fetches Markdown in the browser after returning a generic HTML shell. Rebuilding all 31 entries was outside this publication's scope and would add migration risk. The new standalone article instead establishes the forward path: a server-visible body, unique title and description, canonical URL, BlogPosting structured data, and publication dates in the first response.

This is deliberately incremental. It improves the new-article contract while leaving a successful completed project intact.

## Discovery surfaces

The publication adds three small, inspectable surfaces:

- `sitemap.xml` points to the homepage, blog hub, new article, series landing page, and all 31 existing series URLs.
- `feed.xml` publishes the new article and keeps the completed series discoverable to feed readers.
- `robots.txt` allows crawling and names the sitemap.

These files improve consistency and discovery; they do not guarantee indexing.

## Verification and rollback

Verify the desktop and mobile layouts, local link graph, HTML structure, canonical metadata, JSON-LD, RSS, sitemap, raw response body, Pages deployment, and final HTTPS URLs. Record the merged revision and returned public URL in the publication report.

If publication fails, revert the scoped publication commit. Because the series URLs are unchanged and no content is deleted, rollback does not require rebuilding the 31 Days archive.
