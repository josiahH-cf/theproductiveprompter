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
