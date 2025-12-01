
```
This document has been archived.

See: `9-Archive/_Superseded/Article-Execution-Meta-Prompt.md`

---

 

Each run proceeds through the following controlled phases:

 

---

## 🧱 Anti-Degradation Controls

To prevent semantic drift, degradation, or silent overwrites:

- **Checksum Registry:** Maintain hashlist of all normative files (`manifest.json` or `hashlist.md`).  
- **Diff Enforcement:** All modifications must be shown as unified diffs with a one-line reason.  
- **Rollback on Failure:** Any failed gate restores previous approved version.  
- **Lock/Unlock Mechanism:** `Brand Pack` and `Style Baseline` remain read-only unless user issues `UNLOCK:<filename>`.  
- **Echo-Validation:** Before every major phase, restate the controlling rule from the source spec to confirm compliance.  
- **No Compression:** Never reword or condense original specification text. Preserve formatting and section structure exactly.

---

## 🧩 Control Protocol (Human-in-the-Loop)

The user manages the process via three command tokens:

| Command | Effect |
|----------|---------|
| **APPROVE** | Accepts current phase outputs and proceeds to next. |
| **REVISE:[instruction]** | Returns phase for AI revision; show diffs. |
| **PROCEED** | Confirms readiness to begin Draft Generation after all approvals. |

**You must pause after every approval gate** (Brief, Pack Updates, Draft Delivery).  
Do not skip or combine stages.

---

## 🗂️ Required Inputs

When executing this prompt, the model must have read access to the following folder:

```
/Article-Spec-Pack-v1/
├── 0-Article-Content/                 ← Intake files for "write the next article"
├── 1-Master/
│   ├── Article-Master-Spec.md
│   └── Article-Process-Map.md
├── 2-Templates/
│   └── Article-Brief-Template.md
├── 3-Annexes/
│   ├── Device-Catalog.md
│   └── Evidence-and-IP-Annex.md
├── 4-Carryover-Updated/
│   ├── Brand-Pack-(Author-Compass).md
│   └── Style-Baseline-(Directive).md
├── 7-Intake-Mode/                     ← Intake workflow and autofill templates
└── 9-Archive/
```

If any file is missing, halt immediately and output a **blocking report** naming the missing files.

---

## 🔁 Operational Flow (Detailed)

1. **Startup Integrity Scan** – Confirm required documents, hash and store manifest, verify gates.  
2. **Topic/Content Intake & Brief Creation** – Use inline content if provided; otherwise read newest intake file from `0-Article-Content/`. Auto-generate the brief via `7-Intake-Mode/Intake-Brief-Autofill-Template.md`, fill required fields, output checklist, wait for `APPROVE`.  
3. **Pack Adaptation** – Compare topic vs. Brand Pack & Annex, propose diffs, await approval.  
4. **Readiness Check** – Ensure Gates A–C and devices are defined, wait for `PROCEED`.  
5. **Draft Generation** – Run Process Map and Critic Loop (silent), optional Research Pass, insert link-based citations by default (APA only if required), finalize references.  
6. **Gate Validation & Correction** – Report failures, re-run Critic Loop after fixes.  
7. **Finalization** – Write approved files, update `CHANGELOG.md`, archive previous versions, record hashes.

---

## 🧩 Output Requirements per Phase

| Phase | Outputs |
|--------|----------|
| 1 | `Article-Brief-[topic].md` + checklist of undefined fields. |
| 2 | Diffs for proposed Brand Pack/Annex edits + reason lines. |
| 3 | Confirmation message “Ready to proceed.” |
| 4 | Complete article draft + citations/links per Evidence & IP Annex. |
| 5 | Gate report: Pass/Fail for A, B, C (internal; do not print in article). |
| 6 | `CHANGELOG.md` entry (date, file paths, Run-ID, reason summary). |

---

## 🔒 Anti-Degradation Manifest Rules

**Manifest File:** `/Article-Spec-Pack-v1/manifest.json`  
Each run updates hashes for changed files.  
Never delete a hash; append new entries with timestamps.  
Verify all hashes at startup; abort on mismatch.

Example:

```json
{
  "Brand-Pack-(Author-Compass).md": "d41d8cd98f00b204e9800998ecf8427e",
  "Style-Baseline-(Directive).md": "5f4dcc3b5aa765d61d8327deb882cf99"
}
```

---

## 🧠 Behavior Requirements

- Never invent rules not found in the Article-Spec-Pack.  
- Never alter precedence hierarchy.  
- Never modify normative files without explicit diffs.  
- Always restate the governing rule before applying it (“Echo Validation”).  
- Always log: `Phase`, `Action`, `File`, `Reason`, `Checksum`, `Approval Status`.

---

## 🧩 End-State Goals

When this meta-prompt completes a run successfully:

- Verified `Article-Brief-[topic].md` exists.  
- All pack components remain intact and checksum-verified.  
- Complete, APA-compliant article passes Gates A–C.  
- All approvals, diffs, and file operations logged in `CHANGELOG.md`.  
- No normative degradation or broken references.