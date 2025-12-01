# Superseded: Meta-Prompt Instruction

**Original File:** `Meta-Prompt Instruction.md`  
**Superseded Date:** November 3, 2025  
**Replacements:** 
- `Article-Master-Spec.md` (in `1-Master/`)
- `Article-Process-Map.md` (in `1-Master/`)

---

## Reason for Superseding

This meta-prompt was designed for the **chapter-oriented workflow** with the following mechanics that don't apply to single-pass articles:

**Removed mechanics:**
- Multi-section stop-and-confirm behaviors ("Ready for next section?")
- Chapter and sub-chapter architecture
- Movement-level drafting (700–1,200 word segments)
- Transitional bridges between movements
- Chapter closing steps
- Numeric length bands for movements and chapters

**Chapter-specific elements:**
- OUTPUT 1: Robust Process & Section Map (movement planning)
- OUTPUT 2..N: Movement-level drafts with stop-points
- OUTPUT N+1: Chapter closing transitional bridge
- Final OUTPUT: Chapter-wide consolidated references

---

## What Replaced This

### Article-Master-Spec.md
**Covers:** All normative requirements for article production
- Voice & narrative standards
- Dynamic length policy (content-driven, not fixed bands)
- Structural requirements (hard shape, anti-redundancy, final-line rule)
- Device activation & gating
- Evidence & citation standards
- Quality gates (A: Baseline & Shape, B: Critic Loop, C: Evidence & Freshness)
- Compliance checklist

### Article-Process-Map.md
**Covers:** The single-pass workflow sequence
- Plan → Draft → Critic Loop → Research Pass (if triggered) → Final QA → References
- No stop-points or movement-level planning
- Continuous draft of complete article
- Control document loading order
- Precedence chain for conflict resolution

---

## Key Differences: Chapter vs. Article Workflow

| Element | Chapter Workflow (Original) | Article Workflow (New) |
|---------|---------------------------|----------------------|
| **Planning** | Chapter Brief + Sub-chapter Briefs + Movement Map | Article Brief only |
| **Drafting** | Movement-by-movement with stop-points | Single continuous draft |
| **Length** | 700–1,200 words/movement, 4,500–9,000 words/chapter | Dynamic, content-driven (~2,000–5,000 typical) |
| **Review** | After each movement (user confirmation) | After complete draft (silent Critic Loop) |
| **Transitions** | Bridges between movements/sub-chapters | Natural flow, no bridges |
| **Output Sequence** | OUTPUT 1 (map) → OUTPUT 2..N (movements) → OUTPUT N+1 (bridge) → FINAL (refs) | Single complete article → References |

---

## Historical Use

This meta-prompt orchestrated the **full book chapter production** process:
1. Load 9 directive documents in specific order
2. Generate high-resolution chapter architecture (movement map)
3. Draft each movement individually with user confirmation
4. Integrate devices as specified in chapter/sub-chapter briefs
5. Draft transitional bridge for chapter closing
6. Compile chapter-wide APA references

It included:
- **Search & fact policy** (no browsing during first-pass)
- **Device handling** (activation via Chapter/Sub-chapter Briefs)
- **Two-pass micro-workflow** (skeleton → compose → compress)
- **Hard-form & final-line rules**
- **Quality gates** enforcement

All of these elements are now integrated into the Article Master Spec and Process Map, adapted for single-pass article production.

---

## Archive Status

- **Original file location:** `Meta-Prompt Instruction.md` (workspace root)
- **Original file copy:** `9-Archive/_Originals/Meta-Prompt Instruction.md`
- **Do not use for new work:** Use Article-Master-Spec.md + Article-Process-Map.md instead

---

## Migration Notes

**Preserved in Article Pack:**
- Quality gates (adapted to article scope)
- Critic Loop enforcement
- Device gating (Article Brief as activation authority)
- APA citation requirements
- Hard shape and final-line rules
- Anti-redundancy checks
- Research Pass protocol
- No-new-claims rule

**Removed from Article Pack:**
- Movement planning and coordination
- Multi-section stop-points
- Chapter/sub-chapter architecture
- Fixed numeric length targets
- Transitional bridge requirements

---

**Reference:** See [CHANGELOG.md](../../CHANGELOG.md) for complete migration details.
