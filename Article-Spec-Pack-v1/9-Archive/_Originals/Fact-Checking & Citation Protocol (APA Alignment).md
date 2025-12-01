**Purpose**  
Provide a **dedicated research and verification phase** that guarantees every fact, statistic, and quotation meets the book’s legal and scholarly standards, and that the consolidated APA references are complete and current.

---

### 1. Function

- Activated only when you or the model identify a need for fresh data or citation verification **or when the Freshness Gate is triggered**.
- Supplies **live, APA-formatted sources** and integrates them seamlessly into the draft.
- **No-new-claims rule**: This pass may replace, update, or remove evidence, but must not introduce new argumentative claims beyond what the draft already asserts.

---

### 2. Execution Steps

When the Chapter or Sub-chapter draft is complete **and** a Research Pass is requested:

0. **Freshness Gate**  
   During the Critic Loop or drafting, if any **time-sensitive claim** (e.g., market size, adoption rate, regulation) appears and lacks a current source,  
   **immediately trigger a Research Pass** or insert a bracketed note:  
   > “[Writer to research latest topic]”  
   **Horizon**: Use the freshness horizon specified by the brief; if none is provided, treat sources older than **12 months** for time-sensitive claims as stale and update or flag.

1. **Identify all claims** needing verification or updates (including “What the Papers Say” boxes and time-sensitive stats). **Also cross-check the section’s movement structure to ensure any new or updated citations remain correctly scoped and do not break context-window integrity.**

2. **Search and validate** using the most current credible sources (peer-reviewed journals, industry reports, reputable media).  
   - **Primary over secondary** where feasible (use the version of record).  
   - Prefer **DOIs**; otherwise use stable URLs. If stability is uncertain, add an **archive link** (e.g., perma.cc) and record **accessed date**.

3. **Insert or update in-text APA citations** and expand the running reference list.

4. **Add explicit companion-site references** where data is likely to change:  
   > “For the latest information on <topic, visit https://theproductiveprompter.com.”

5. **Re-run the Critic Loop** silently to ensure new content still matches voice and intent and that **no-new-claims** is preserved.

6. Return **only the revised section or final consolidated references list**.

---

### 3. Citation Rules

- Strictly follow **APA 7th edition**.
- Provide **DOIs** when available; otherwise stable URLs (plus archived link and **accessed date** for web sources).
- If no credible source exists, **flag clearly**:  
  > “[Writer to research topic]”

---

### 4. Relationship to Other Documents

- **Upstream:** Citations & IP Note (the core rules for APA and IP).
- **Side-by-Side:** Critic Loop for evidence verification and voice consistency.
- **Downstream:** Consolidated APA references at chapter end.

---

**Workflow Placement**

- **Invoked:** When you choose option **(B) Research Pass** at the end of any section draft, when the **Freshness Gate** fires, or just before the final consolidated reference step.
- **Used:** In the Kickoff Meta-Prompt sequence right after a section is written or at the chapter-wide reference stage.
