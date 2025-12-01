# Device Catalog (Annex)

**Purpose**  
Define all approved narrative devices, their purposes, structural rules, and formatting requirements. This catalog is the authoritative reference for device mechanics; the **Article Brief** is the sole activation authority.

---

## Core Principles

1. **Devices are planning aids** — Use devices to plan and structure content. Render them as natural prose, lists, tables, or code in the public article.
2. **No activation headers in public text** — Never print labels like “Device: …” or any activation metadata in reader-facing content.
3. **Reflowable formatting only** — All device outputs must use semantic text (lists, tables, callouts), never images.
4. **Content-agnostic mechanics** — Device rules apply regardless of article topic or length.

---

## Activation Guidance (Internal)

If a brief requests specific device behaviors, capture them in planning notes (device name, purpose, placement). Do not print any activation headers in the public article. Instead, render the intended behavior naturally (e.g., a short scenario, a Q&A styled subheading, a comparison table).

---

## Device Definitions

### 1. Prompt Plate

**Purpose:**  
Demonstrate principle-first prompting in action. Show "before/after" contrasts to prove claims about better outputs and reduced prompt counts.

**When to Use:**
- To illustrate a specific prompting principle, troubleshooting pattern, or repeatable workflow
- To provide a concrete, reusable template readers can adapt
- To show measurable improvement from applying a technique

**Format:**  
Reflowable table or code block (never an image)

**Typical Structure:**

| **Scenario** | **Prompt (Before)** | **Prompt (After)** | **Outcome** |
|--------------|---------------------|-------------------|-------------|
| [Context] | [Initial prompt] | [Improved prompt] | [Result/improvement] |

Alternative format (code block):
```
BEFORE:
[Initial prompt text]

AFTER:
[Improved prompt text]

OUTCOME:
[Measurable improvement or result]
```

**Integration Requirements:**
- Include brief lead-in sentence explaining the principle this plate demonstrates
- Keep examples real or clearly labeled as representative tests
- Cite sources or workflow data if relevant (APA format)
- Ensure table/code block reflows properly on e-readers

Do not include activation headers in public output.

---

### 2. Decision Tree / Checklist

**Purpose:**  
Provide structured, repeatable guidance for complex tasks. Help readers troubleshoot or plan through logical, branching sequences.

**When to Use:**
- To guide readers through multi-step reasoning (e.g., diagnosing poor model outputs)
- To illustrate workflows or conditional sequences (e.g., "If X, then Y")
- To provide systematic troubleshooting paths

**Format:**  
Semantic nested lists (bullets or numbered outlines) for e-reader reflow

**Typical Structure:**

**Decision Tree Format:**
```
1. First decision point
   - If condition A → Action 1
   - If condition B → Action 2
     - If sub-condition B1 → Action 2a
     - If sub-condition B2 → Action 2b
   - If condition C → Action 3

2. Second decision point
   [continues...]
```

**Checklist Format:**
```
□ Step 1: [Action with brief explanation]
□ Step 2: [Action with brief explanation]
  □ Sub-step 2a: [Detail]
  □ Sub-step 2b: [Detail]
□ Step 3: [Action with brief explanation]
```

**Integration Requirements:**
- Introduce with 1–2 sentences explaining purpose and scope
- Keep branch labels short and imperative (e.g., "Check context length → Revise prompt → Test again")
- Provide APA citations if derived from external research or best practices
- Use clear visual hierarchy (indentation, numbering) for branches

Do not include activation headers in public output.

---

### 3. What the Papers Say

**Purpose:**  
Distill key academic or industry findings that validate or challenge the article's arguments. Offer authoritative evidence in a digestible format.

**When to Use:**
- To highlight pivotal whitepapers, peer-reviewed studies, or market reports
- To keep fast-moving research accessible without derailing narrative flow
- To provide scholarly backing for claims

**Format:**  
Short, clearly labeled callout box (semantic text, not graphic)

**Typical Structure:**

```
📄 What the Papers Say

**Paper/Source:** [Full citation in APA format]
**Authors:** [Author names]
**Key Finding:** [One-paragraph summary of the finding]

**Relevance:** [One sentence linking finding back to article's argument]

[Include DOI or stable URL as live link]
```

Alternative compact format:
```
📄 What the Papers Say: [Paper Title]

[Author(s), Year] found that [key finding in one paragraph]. This [validates/challenges/extends] the article's argument that [connection to thesis].

Full citation: [APA format with DOI/URL]
```

**Integration Requirements:**
- Include full APA citation and live link (DOI or official source)
- One-paragraph summary maximum (80–120 words)
- Conclude with one sentence linking finding to article's thesis
- **Freshness gate:** If finding contains time-sensitive statistics, verify currency per Article Brief horizons; add companion-site callout if data may evolve
- If source is stale or unverifiable, insert **[Writer to research latest <topic>]**

Do not include activation headers in public output.

---

### 4. Code Example Block

**Purpose:**  
Show executable code, API calls, or prompt syntax that readers can copy and adapt.

**When to Use:**
- To demonstrate technical implementation
- To provide copy-paste templates
- To illustrate syntax or formatting requirements

**Format:**  
Code block with language identifier for syntax highlighting

**Typical Structure:**

````
```python
# Example: API call with structured prompt
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ]
)
print(response.choices[0].message.content)
```
````

**Integration Requirements:**
- Include brief lead-in explaining what the code demonstrates
- Add inline comments for clarity
- Specify language/framework version if relevant
- Test code before inclusion (or label as "conceptual example")
- Provide context about where/how readers would use this code

Do not include activation headers in public output.

---

## Formatting Standards (All Devices)

### Reflowability Requirements

All devices must support Kindle/EPUB3 reflowability:

- **No images for core information** — Use semantic text structures
- **Tables:** Markdown or HTML tables with proper headers
- **Lists:** Use bullets, numbers, or nested indentation
- **Callouts:** Format as text blocks with clear labels/headings
- **Code blocks:** Use triple-backtick fencing with language identifiers

### Accessibility

- Provide **alt text** if publisher adds diagrams later
- Use semantic HTML/Markdown so screen readers can navigate
- Ensure sufficient contrast and clear hierarchy

### Visual Hierarchy

- Use **headings** to introduce devices
- Use **bold** for labels and key terms
- Use *italics* sparingly for emphasis
- Use `code formatting` for technical terms, file names, commands

---

## Device Review (Silent)

During self-review, verify that device-like content serves the article’s argument, follows reflowable formatting, and never exposes internal labels or activation metadata. If a brief requested a device behavior, ensure the intent is achieved naturally (e.g., scenario vignette, table, or checklist) with no public labeling.

---

## Future Device Extensions

If a new device type is needed:

1. Define its purpose, use cases, and format in this catalog
2. Update Article Brief Template to support activation
3. Add enforcement checks to Critic Loop
4. Version-control this catalog with changelog entry

**Pending devices (not yet approved):**
- Illustrative Analogies (structured comparison boxes)
- Cross-Reference Boxes (links to related articles/chapters)
- Live Experiment Results (reproducible test data)

---

## Quick Reference: Device Checklist

Before finalizing any article with devices:

- [ ] Every device is explicitly activated in Article Brief
- [ ] Activation header present immediately before each device
- [ ] Device format follows catalog specifications
- [ ] All tables/lists/callouts use reflowable semantic text
- [ ] Citations included where devices reference sources
- [ ] Freshness verified for time-sensitive device content
- [ ] Device serves the article's argument (not decorative)

---

**Version:** 1.0  
**Date:** November 3, 2025  
**Status:** Normative Annex — Defines approved devices and formatting rules.
