# Evidence & IP Annex (APA + IP)

**Purpose**  
Guarantee that every factual claim, quotation, and intellectual property reference is accurate, current, legally compliant, and professionally formatted. This annex provides the **citation and rights framework** enforced during article production.

---

## 1. Citation Standards (Developer Articles)

### 1.1 Format Requirements

- Use **credible linkable citations by default** (descriptive anchors); apply **APA 7th** only when the Article Brief explicitly requires it.
- When APA is required: every in-text citation must have a corresponding full reference entry; references appear in a single, alphabetized list at article end.

### 1.2 Content Rules

**Facts and Statistics:**
- Cite credible, verifiable sources:
  - Peer-reviewed journals (preferred)
  - Major consulting firms (e.g., McKinsey, Gartner)
  - Reputable industry reports
  - Recognized media outlets with editorial standards
- Prefer **primary sources** over secondary when available (use version of record)

**Quotations:**
- Use direct quotes sparingly; prefer paraphrasing with citations
- If direct quote is essential, reproduce accurately and cite exact page or timestamp
- Format per APA 7 guidelines (short quotes in-text, long quotes as block quotes)

**Live Links:**
- Include clickable links where platform supports (Kindle/EPUB3, companion website)
- Prefer **DOIs** (Digital Object Identifiers) for permanence
- If no DOI, use stable URLs
- For web sources without stable URLs, add:
  - Archive link (e.g., perma.cc, Internet Archive)
  - Accessed date

### 1.3 Common Knowledge Exemption

Widely accepted facts require no citation:
- "The Earth orbits the Sun"
- "Alan Turing introduced the Turing Test in 1950"
- "Python is a programming language"

**Borderline cases:** Err on the side of citing.

### 1.4 When Data is Unavailable

If no credible source exists or data are incomplete:
- Prefer to generalize the claim or remove it
- If the Article Brief requires keeping the claim, **trigger Research Pass**
- Do not leak bracketed placeholders into public text

---

## 2. Dynamic Freshness Policy

### 2.1 Principle

**No fixed 12-month default.** Freshness is **dynamic** and determined by:
1. **Topic type** (rapidly evolving vs. stable foundational knowledge)
2. **Article Brief specifications** (topic-specific horizons)
3. **Best available information** at time of drafting

### 2.2 Freshness Horizons by Topic Type

**Rapidly Evolving Topics (require current sources):**
- Market sizes and adoption rates
- Technology capabilities and benchmarks
- Regulatory changes and legal frameworks
- Industry statistics and trends
- Product features and versions

**Recommended horizons:**
- Critical business data: 3–6 months
- Technical capabilities: 6–12 months
- Industry trends: 12–18 months

**Stable Foundational Topics (older sources acceptable):**
- Established theories and frameworks
- Historical events and context
- Foundational research and seminal papers
- Core concepts and definitions

**Acceptable horizons:**
- Seminal research: Any period (cite version of record)
- Foundational concepts: Focus on authority, not recency

### 2.3 Article Brief Controls

The **Article Brief** may specify custom freshness requirements:
- Override default horizons for specific topics
- Identify topics requiring extra-current sources
- Flag areas where sources may be scarce or evolving

**Precedence:** Article Brief freshness specifications override general guidance.

### 2.4 Freshness Gate Trigger

During **Critic Loop Evidence Check**, if a time-sensitive claim appears:

**If current source available:**
- Cite the source with a credible link (or APA if required by the Brief)
- Prefer DOI or stable URL
- Add companion-site callout only if requested by the Brief

**If no current source available:**
- Generalize or remove the claim, or trigger **Research Pass**
- Do not insert bracketed placeholders in public text

**If source is stale (beyond horizon):**
- Trigger **Research Pass** to find updated data
- If no update exists, generalize or remove the claim

---

## 3. Research Pass Protocol

### 3.1 When to Execute

**Trigger conditions:**
- Freshness gate fires during Critic Loop
- Article Brief explicitly requests verification
- Time-sensitive claim lacks current citation
- Unverifiable claim needs validation

### 3.2 Execution Steps

**Step 1: Identify Claims Needing Verification**
- Review all factual claims in article
- Flag time-sensitive statistics, market data, regulations
- Note any bracketed research gaps

**Step 2: Search and Validate**
- Search for **most current credible sources**
- Prefer:
  1. Peer-reviewed journals with DOIs
  2. Industry reports from recognized firms
  3. Official government or organizational sources
  4. Reputable media with editorial standards
- Verify:
  - Source authority (author credentials, publication reputation)
  - Methodology (if applicable)
  - Relevance to claim
  - Currency relative to Article Brief horizons

**Step 3: Update Citations**
- Insert or update APA in-text citations
- Add full reference entries to consolidated list
- Include DOIs or stable URLs
- Add accessed dates for web sources

**Step 4: Add Companion-Site Callouts**
- For data likely to change, add in-text note:
  > "For the latest information on <topic>, visit https://theproductiveprompter.com."
- Place callout near the time-sensitive claim
- Include in consolidated references if appropriate

**Step 5: No-New-Claims Rule**
- **May** replace, update, or remove evidence
- **May** refine existing claims for accuracy
- **Must NOT** introduce new argumentative claims beyond what draft already asserts
- Research Pass is for verification and updating, not expansion

**Step 6: Re-Run Critic Loop**
- Silently apply Voice, Focus, Evidence checks
- Ensure research updates maintain consistency
- Verify no new voice drift or focus issues introduced
- Validate all new citations formatted correctly

### 3.3 Output

Return **only revised article text** with updated citations. Never output:
- Search process notes
- Source evaluation reasoning
- Research logs or metadata

---

## 4. Companion Website Integration

### 4.1 Purpose

Use **https://theproductiveprompter.com/** as the authoritative update hub for:
- Time-sensitive statistics that may change post-publication
- Evolving industry benchmarks
- Emerging research findings
- Extended source material not suitable for e-book format

### 4.2 When to Add Callouts

**Use only if requested by the Brief.** Common candidates include:
- Market adoption rates
- Technology capability benchmarks
- Regulatory changes
- Industry statistics and trends

**Format (in-text):**
> "For the latest information on global AI adoption statistics, visit theproductiveprompter.com."

**Format (in references):**
If companion site hosts extended data:
```
The Productive Prompter. (n.d.). AI adoption statistics [Extended data set]. 
    Retrieved November 3, 2025, from https://theproductiveprompter.com/resources/ai-adoption
```

### 4.3 Placement

- Add callout **within main text** where statistic/claim is introduced
- Optionally repeat in consolidated references
- Ensure readers know exactly where to find current data

---

## 5. Attribution of Third-Party Content

### 5.1 Intellectual Property

**Trademarks and Franchises:**
- Use **neutral descriptive language** when referencing trademarks or fictional works
- Always **attribute ownership** where appropriate:
  > "As illustrated by _Terminator_ (a property of StudioCanal and Skydance Media)…"
- Avoid implying endorsement, partnership, or affiliation with rights holders
- First mention: Full attribution
- Subsequent mentions: Abbreviated form acceptable

**Product Names:**
- Use proper capitalization (e.g., ChatGPT, not chatgpt)
- Include version numbers when relevant to claim
- No trademark symbols needed in body text

### 5.2 Figures, Tables, and Diagrams

**If using third-party visuals:**
- Confirm public domain, compatible license, or explicit permission
- Always credit source with full citation
- Include "Adapted from" or "Reprinted from" as appropriate
- For proprietary content, obtain written permission

**Preferred approach:**
- Create original tables/diagrams based on source data
- Cite the underlying data source, not the original visualization
- This avoids licensing issues while maintaining attribution

### 5.3 Data Sets

**If referencing specific datasets:**
- Name the dataset and version
- Provide access details or URLs if legally permissible
- Cite dataset creators per APA 7 guidelines
- Note any usage restrictions or licenses

---

## 6. Reference List Requirements

### 6.1 Structure

- **Single consolidated section** at article end
- Heading: "References" (not "Bibliography" or "Works Cited")
- **Alphabetize** by author surname (or first significant word if no author)
- Use **hanging indent** (first line flush left, subsequent lines indented)

### 6.2 APA 7 Formatting

**Journal Article:**
```
Author, A. A., & Author, B. B. (Year). Title of article. Title of Periodical, 
    volume(issue), page–page. https://doi.org/xxxxx
```

**Book:**
```
Author, A. A. (Year). Title of book (Edition). Publisher. 
    https://doi.org/xxxxx
```

**Website/Online Source:**
```
Author, A. A., or Organization. (Year, Month Day). Title of webpage. 
    Site Name. Retrieved Month Day, Year, from https://url
```

**Report:**
```
Organization. (Year). Title of report (Report No. xxx). Publisher. 
    https://doi.org/xxxxx or URL
```

### 6.3 DOIs and URLs

- **Always include DOI** if available (preferred over URL)
- Format DOIs as links: `https://doi.org/10.xxxx/xxxxx`
- If no DOI, provide stable URL
- For unstable URLs:
  - Add archive link (perma.cc, Internet Archive)
  - Include accessed date: `Retrieved November 3, 2025, from`

### 6.4 Quality Checks

Before finalizing references:
- [ ] Every in-text citation has corresponding reference entry
- [ ] Every reference entry is cited in-text
- [ ] Alphabetical order maintained
- [ ] Hanging indent applied
- [ ] DOIs included where available
- [ ] URLs tested (no broken links)
- [ ] Accessed dates included for web sources
- [ ] Formatting consistent throughout

---

## 7. Citation Guidance for Models Without Real-Time Web Search

### 7.1 When Web Search is Unavailable

Many execution environments (web GUIs, API-only access, sandboxed models) do not provide real-time web search. In these cases:

**Use training data knowledge:**
- Cite sources from your training data cutoff
- Be explicit about the knowledge date: "As of [training cutoff], the most recent data showed..."
- Prefer authoritative sources that are likely to remain stable

**Example:**
> "According to OpenAI's GPT-4 technical report (OpenAI, 2023), models with 8K context windows demonstrated 15% higher coherence scores in multi-turn dialogues."

### 7.2 Handling Uncertainty

When you cannot verify a fact or find a current source:

**Option 1: Mark internally for human verification** (do not leak to public text)

**Option 2: State what you know with date qualifier**
> "As of October 2024 (model training cutoff), the largest publicly available context window was 128K tokens (Anthropic, 2024). Current sizes may have increased; see theproductiveprompter.com for updates."

**Option 3: Focus on principles over statistics**
Instead of:
> "73% of enterprises use AI for customer service (citation needed)"

Use:
> "Organizations increasingly deploy AI for customer service, with adoption driven by reduced response times and 24/7 availability—benefits that remain consistent regardless of specific adoption rates."

### 7.3 Best Practices for No-Search Environments

**DO:**
- ✅ Cite seminal papers and foundational research (stable over time)
- ✅ Use your training data knowledge with clear dating
- ✅ Bracket uncertain claims for human verification
- ✅ Prefer timeless principles over rapidly changing statistics
- ✅ Direct readers to companion site for current data
- ✅ State your knowledge cutoff explicitly when citing recent claims

**DON'T:**
- ❌ Fabricate citations or statistics
- ❌ Cite sources as if they're more recent than your training data
- ❌ Pretend to have real-time information
- ❌ Use vague phrases like "recent studies show" without specifics
- ❌ Guess at current numbers (bracket instead)

### 7.4 Source Hierarchy for No-Search Contexts

When selecting what to cite from training data:

**Tier 1 (Preferred):**
- Peer-reviewed journal articles with DOIs
- Official technical reports from organizations (e.g., OpenAI, Anthropic)
- Government or academic institution publications
- Well-documented industry standards

**Tier 2 (Acceptable):**
- Reputable industry reports (Gartner, McKinsey, etc.)
- Technical documentation from major platforms
- Recognized conference proceedings
- Established media with editorial standards

**Tier 3 (Use with caution):**
- Blog posts from recognized experts (cite author credentials)
- Company case studies (note potential bias)
- Industry surveys (note methodology if available)

**Tier 4 (Avoid):**
- Undated web content
- Sources without clear authorship
- Marketing materials presented as research
- Anecdotal claims without backing

### 7.5 Template for No-Search Citations

```markdown
According to [Author/Organization], [Year], [claim with specific details]. 
[If from training data: Note training cutoff]
[If uncertain: Bracket for verification]
[If time-sensitive: Add companion site reference]

Example:
According to Chen et al. (2024), structured prompts reduced ambiguous 
outputs by 40–60% in a study of 10,000 enterprise interactions. 
[Writer to verify: any more recent studies as of late 2025] 
For the latest research on prompt engineering effectiveness, 
visit theproductiveprompter.com.
```

### 7.6 Execution Mode Flag

When executing in no-search mode, the model should:

1. **Declare mode at Phase 0:** "Executing in NO-SEARCH mode (using training data only)"
2. **Apply conservative citation strategy:** Focus on foundational sources
3. **Increase bracketing:** Flag more items for human verification
4. **Add companion site callouts:** Direct readers to current data
5. **Document in metadata:** Note "Sources: Training data (cutoff: [date])"

---

## 8. Integration with Drafting Process

### 8.1 During Drafting

**Draft phase:**
- Insert citations as claims are written (APA only if required by Brief)
- Note source details for reference list
- Track research gaps internally (no public bracketed placeholders)

**Critic Loop Evidence Check:**
- Verify all non-common-knowledge claims cited
- Check APA format correctness
- Validate freshness against Article Brief horizons
- Trigger Research Pass if needed

### 8.2 During Research Pass

- Find current sources per Section 3 protocol
- Update citations and references
- Add companion-site callouts
- Re-run Critic Loop

### 8.3 Final QA (Gate C)

- APA compliance verified
- Dynamic freshness satisfied or gaps bracketed
- Research Pass executed if triggered
- Companion-site callouts added where appropriate
- Consolidated reference list complete and formatted

---

## 9. Error Handling

### 9.1 Conflicting Sources

If sources disagree on a fact:
- Cite the most authoritative/recent source
- Note the disagreement if material to argument:
  > "Estimates vary; Smith (2025) reports 40%, while Jones (2024) found 35%."
- Prefer peer-reviewed over industry reports over media

### 9.2 Unverifiable Claims

If claim cannot be verified:
- Remove claim, or
- Insert **[Writer to research latest <topic>]** and continue
- Do not fabricate citations
- Do not cite unreliable sources to fill gaps

### 9.3 Paywalled or Inaccessible Sources

- Cite source normally per APA 7
- Note access restrictions only if relevant to readers
- Prefer open-access sources when available
- If critical source is paywalled, provide alternative accessible sources or summary

---

## Quick Reference: Evidence Checklist

Before finalizing any article:

- [ ] All factual claims cited (or common knowledge)
- [ ] Citations present (APA only if required by Brief)
- [ ] Freshness verified per Article Brief horizons
- [ ] Research gaps tracked internally or researched (no public bracket placeholders)
- [ ] Companion-site callouts added for time-sensitive data
- [ ] Third-party IP attributed neutrally
- [ ] Consolidated reference list complete
- [ ] All DOIs and URLs tested and working
- [ ] No-new-claims rule followed during Research Pass
- [ ] Critic Loop re-run after research updates

---

**Version:** 1.0  
**Date:** November 3, 2025  
**Status:** Normative Annex — Defines citation, freshness, and IP standards for articles.
