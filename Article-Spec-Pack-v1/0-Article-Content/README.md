# 0 — Article Content Intake

Drop your general content here. The "write the next article" command will read the most recent file and generate an expert blog.

Keep this folder clean
- Keep the **root** of `0-Article-Content/` for real intake drafts only.
- Planning docs (queue, indexes) live in `0-Article-Content/_meta/`.
- Campaign-specific sources and queues should be archived under `9-Archive/` when the campaign is complete.

How it selects content
- Picks the newest file by last modified timestamp.
- If files start with a date prefix `YYYYMMDD-`, that is used to break ties and determine recency.
- Supported: `.md`, `.txt`. You can paste from PDFs by saving as `.md`/`.txt` here.

What to include
- Working title (optional)
- Notes, bullets, or pasted excerpts
- Audience nuance (optional)
- Any must-include points or links

Tips
- Keep one intake file per post. Name like: `20251113-beyond-the-hype.md`.
- Link to sources you want cited; model will default to link-based citations.
- Once an article is packaged, the corresponding intake file is moved into `6-Completed-Articles/.../sources/` so only unfinished inputs remain here.

Next step
- After adding your file, say: "write the next article".
