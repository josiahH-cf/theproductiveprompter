# Publication Adversarial Review

**Target:** Completed article package and public-site placement

**Review date:** 2026-08-18

**Posture:** Try to hide the old series, create link rot, publish a crawler-thin shell, let metadata drift from the manuscript, or declare success from a local file alone.

## Attack 1 — Does “archive” quietly mean “gone”?

### Checks

- The homepage places 31 Days directly below the latest article and labels it “31 entries · all visible.”
- The blog hub has a dedicated “Completed series archive” section with a plain-language explanation.
- The series landing page says that archiving did not hide the entries.
- The new article contains a related-series link back to the complete archive.
- All 31 legacy links retain their original `article.html?post=31-days-ai-day-NN.md` form.
- All 31 Markdown files remain in `docs/`.

### Verdict

Pass. The series changes presentation tier but not location or availability.

## Attack 2 — Can the new location create link rot or split identity?

### Checks

- One permanent public URL is used by the page canonical, Open Graph URL, JSON-LD URL, JSON-LD `mainEntityOfPage`, homepage, blog hub, RSS item, and sitemap entry.
- Local crawling returned HTTP 200 for 35 unique relative routes.
- The legacy viewer's back link now reaches the actual series landing page instead of a nonexistent homepage fragment.
- No redirect is introduced because no existing public URL changes.

### Verdict

Pass. The new article has one identity, and the series retains its existing identities.

## Attack 3 — Is this another generic JavaScript shell?

### Checks

- The dedicated article file contains the headline and complete body in raw HTML.
- It does not depend on Marked, DOMPurify, or a browser fetch to expose the manuscript.
- The first response contains a unique title, description, canonical link, author, publication date, BlogPosting JSON-LD, and RSS discovery link.
- The manuscript's 14 citations and project links returned HTTP 2xx/3xx during the final prepublication pass.

### Verdict

Pass for the new standalone path. The 31 legacy entries still use the shared client-rendered viewer; that known limitation is intentionally not disguised as repaired.

## Attack 4 — Can the public page drift from the approved article?

### Checks

- The HTML body was generated mechanically from the completed package's `article.md`.
- The approved Markdown remains the only top-level file in the completed article package.
- Metadata records the article and page checksums, word count, revision, and intended public URL.
- The publication-specific paragraph is time-bound and does not claim that sitemap submission guarantees indexing.

### Verdict

Pass. The package is traceable; live revision proof remains a post-merge check.

## Attack 5 — Does the hierarchy collapse on a small screen?

### Checks

- Desktop and 390-pixel browser renders were inspected for the blog hub, article, and complete series page.
- The latest feature card collapses to one column and reduces its padding and headline size.
- The article keeps one readable column; its longest diagram note is wrapped at source.
- Checklist markers render as visible empty boxes with plain text rather than duplicated list bullets.
- The 31-entry archive collapses to a single card column without removing content.

### Verdict

Pass after the mobile-card and diagram-wrap repairs.

## Attack 6 — Can discovery files create false confidence?

### Checks

- `sitemap.xml` is valid XML with 35 unique URLs: four primary pages plus all 31 series article URLs.
- `feed.xml` is valid RSS with the new article and completed series landing page.
- `robots.txt` permits crawling and points to the sitemap.
- Public copy says these surfaces improve discovery but do not guarantee indexing.

### Verdict

Pass with a deliberate limitation: the feed represents the completed series as one project rather than replaying 31 historical items.

## Residual risks accepted for this release

- The legacy series viewer still exposes generic initial metadata and client-rendered article bodies.
- The new article has no custom social-preview image; social platforms receive text metadata only.
- Search crawling, rendering, and indexing remain asynchronous and outside the deployer's guarantee.
- GitHub Pages must still build the merged revision, and the live HTTPS responses must be inspected before the publication loop is complete.

**Prepublication status:** Ready to commit, merge, deploy, and inspect live.
