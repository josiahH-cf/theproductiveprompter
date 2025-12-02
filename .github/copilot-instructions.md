# Copilot Instructions for Updating Documentation

This repository uses a client-side Markdown viewer to render articles. When adding new articles or updating links, follow these instructions.

## Adding a New Article

1.  **Upload the Markdown File:**
    *   Place your `.md` file in the `docs/` directory.
    *   Ensure the file name is URL-friendly (e.g., `my_new_article.md`).

2.  **Link to the Article:**
    *   To link to the article from `index.html` or any other HTML page, use the following format:
        ```html
        <a href="docs/article.html?post=your_filename.md">Link Text</a>
        ```
    *   **Note:** Do NOT link directly to `docs/your_filename.md`. Always route it through `article.html`.

## Updating the "Featured Article"

1.  Open `index.html`.
2.  Locate the `.article-card--featured` section.
3.  Update the `href` attribute of the title link:
    ```html
    <a href="docs/article.html?post=new_featured_article.md" class="article-card__link">Article Title</a>
    ```
4.  Update the date, reading time, and summary text in the HTML card.

## Updating the "Articles List"

1.  Open `index.html`.
2.  Locate the `.articles__list` container.
3.  Add a new article card using this template:
    ```html
    <article class="article-card">
        <div class="article-card__content">
            <div class="article-card__meta">
                <time class="article-card__date">Month Day, Year</time>
                <span class="article-card__separator">•</span>
                <span class="article-card__reading-time">X min read</span>
            </div>
            <h3 class="article-card__title">
                <a href="docs/article.html?post=filename.md" class="article-card__link">Article Title</a>
            </h3>
            <p class="article-card__summary">
                Brief summary of the article...
            </p>
        </div>
    </article>
    ```

## Copilot Prompt Shortcut

If you need to add a new article quickly, you can ask Copilot:
> "Update the docs links for the new article [filename.md]"

Copilot should then:
1.  Check `docs/` for the file.
2.  Generate the correct HTML link using the `article.html?post=` format.
3.  Insert it into the appropriate section of `index.html`.

## 31 Days of AI Campaign Workflow

For the "31 Days of AI" campaign, follow this specific workflow:

1.  **Topic & Brief**:
    *   Start with a topic or tool.
    *   Generate a brief if needed, or proceed directly to drafting if the concept is clear.

2.  **Drafting with Spec Standards**:
    *   Use the **Unified Article Spec** structure:
        *   **Opening Reality Check**: Ground the topic in a real frustration or problem.
        *   **Mental Models**: 2-3 utility-first concepts.
        *   **Workflow Blocks**: Concrete "When/Why", "Pattern" (prompt), and "Steps".
        *   **Caution Section**: What *not* to outsource.
        *   **Tri-Stage Checklist**: Before, During, After.
        *   **Closing Activation**: A concrete next step.
    *   **Methodology Note**: At the end of the article (before the disclosure), mention that the finalized article goes into a web-based AI model (GPT-5.1) using a tone instruction doc for the final polish.

3.  **Meta Requirements**:
    *   **Filename**: `docs/31-days-ai-day-XX.md` (e.g., `31-days-ai-day-01.md`).
    *   **AI Disclosure**: Append `(created with AI)` at the very end.
    *   **GitHub Link**: Append `View the source code on GitHub: [ProductivePrompter.com Repository](https://github.com/josiahH-cf/theproductiveprompter)`.

4.  **Publishing**:
    *   Save the file in `docs/`.
    *   Update `index.html` to include the new day in the "31 Days of AI" section.
    *   Update the progress counter (e.g., "Day 1 of 31").

---

## 🤖 Automated Copilot Commands

### Command: "Update today's article" / "Deploy today's article"

When the user says **"update today's article"**, **"deploy today"**, or similar:

**Step 1: Identify the next article to deploy**
1.  Calculate the current day number: `(current date - December 1, 2025) + 1`
    - Example: December 2 = Day 2, December 3 = Day 3, etc.
2.  Check `docs/` for the corresponding `31-days-ai-day-XX.md` file
3.  Check `docs/31-days-of-ai.html` to see if that day's card is already "Live" or still "Coming Soon"
4.  If the day is already live, report "Day XX is already deployed" and stop
5.  If the markdown file doesn't exist, report "Day XX article not found in docs/" and stop

**Step 2: Plan the deployment**
1.  Read the article's title from the first `# Heading` in the markdown file
2.  Generate a short summary (1 sentence) from the article's opening
3.  Confirm the plan with the user: "Ready to deploy Day XX: [Title]. Proceed?"

**Step 3: Update the website**
1.  **Update `docs/31-days-of-ai.html`:**
    - Change `days-page__counter` to "Day XX of 31"
    - Convert the Day XX locked card to a live `<a>` card with title and summary
2.  **Update `index.html`:**
    - Change `campaign-banner__counter` to "Day XX of 31"
    - Update `campaign-banner__latest` link text and href to Day XX
    - Update "Read Today's Entry" href to Day XX

**Step 4: Git workflow**
1.  Create branch: `feature/day-XX`
2.  Commit changes: `"Reveal Day XX: [Title] - update campaign banners and day cards"`
3.  Push branch to remote
4.  Merge to main
5.  Push main
6.  Delete local and remote feature branch

**Step 5: Generate social post**
1.  Draft a simple LinkedIn post with emoji in the Day 2 voice style
2.  Include link to `https://theproductiveprompter.com/docs/31-days-of-ai.html`

---

### Command: "Scope a new article" / "Plan next article"

When the user says **"scope a new article"**, **"plan next article"**, or similar:

**Step 1: Identify non-deployed articles**
1.  Scan `Article-Spec-Pack-v1/0-Article-Content/` for available source articles
2.  Check `docs/` to see which `31-days-ai-day-XX.md` files already exist
3.  Cross-reference with `ARTICLE-INDEX.md` to identify completed articles not yet converted

**Step 2: Present options and ask 2 follow-up questions**
1.  List available source articles that haven't been deployed yet
2.  Ask: **"Which article should be converted for Day XX?"**
3.  Ask: **"Any specific angle or focus for this day's version?"**

**Step 3: Run the article spec workflow**
1.  Use the **Unified Article Spec** structure to draft the article
2.  Apply the meta requirements (filename, disclosure, GitHub link)
3.  Save to `docs/31-days-ai-day-XX.md`
4.  Optionally: Run through GPT-5.1 with tone instruction doc for final polish

---

### Day-to-Article Mapping Reference

The campaign runs December 1-31, 2025. Use this mapping for planning:

| Day | Date | Source Article (from 0-Article-Content) | Status |
|-----|------|----------------------------------------|--------|
| 01 | Dec 1 | (Custom: Automating the Editor) | ✅ Deployed |
| 02 | Dec 2 | 01-beyond-the-hype (→ `31-days-ai-day-02.md`) | ✅ Deployed |
| 03 | Dec 3 | 03-from-logic-to-prediction.md | 📄 Ready |
| 04 | Dec 4 | 02-the-professionals-playbook-early-win.md | 📄 Ready |
| 05 | Dec 5 | 04-how-ai-learns-training-bias-hallucinations.md | 📝 In 0-Article-Content |
| 06 | Dec 6 | 05-tokens-and-context-windows.md | 📝 In 0-Article-Content |
| 07 | Dec 7 | 06-from-mess-to-plan-maya-case-study.md | 📝 In 0-Article-Content |
| 08 | Dec 8 | 07-advanced-patterns-cot-rag-react.md | 📝 In 0-Article-Content |
| 09 | Dec 9 | 08-choosing-your-ai-tool.md | 📝 In 0-Article-Content |
| 10 | Dec 10 | 09-critical-thinking-with-alex.md | 📝 In 0-Article-Content |
| 11 | Dec 11 | 10-the-professionals-compass-principles.md | 📝 In 0-Article-Content |
| 12-31 | Dec 12-31 | TBD - scope as needed | ⏳ Pending |

**Legend:**
- ✅ Deployed: Live on website
- 📄 Ready: Converted to `docs/31-days-ai-day-XX.md`, not yet deployed
- 📝 In 0-Article-Content: Source exists, needs conversion to 31-days format
- ⏳ Pending: Not yet planned

---

### Quick Reference: File Locations

| Purpose | Location |
|---------|----------|
| Source articles | `Article-Spec-Pack-v1/0-Article-Content/` |
| Deployed articles | `docs/31-days-ai-day-XX.md` |
| Campaign index page | `docs/31-days-of-ai.html` |
| Homepage banner | `index.html` (section `#31-days-of-ai`) |
| Article viewer | `docs/article.html?post=filename.md` |
| Article spec templates | `Article-Spec-Pack-v1/1-Master/` |
