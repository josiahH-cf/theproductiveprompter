"""On-demand article dependencies and bounded maintenance, without a scheduler."""
from __future__ import annotations

import re
from typing import Any

from editorial_context import digest


def index_article(af: Any, directory: Any, run: dict) -> dict:
    article_path = af.artifact_path(directory, run, "article") or af.artifact_path(directory, run, "draft")
    text = article_path.read_text(encoding="utf-8") if article_path else ""
    ledger = af.json_artifact(directory, run, "post-edit-claim-ledger") or af.json_artifact(directory, run, "verified-claim-ledger") or af.json_artifact(directory, run, "claim-ledger") or {}
    brief = af.json_artifact(directory, run, "brief") or {}
    plan = af.json_artifact(directory, run, "visual-plan") or {}
    metadata_path = directory / "package/public/metadata.json"
    metadata = af.load_json(metadata_path) if metadata_path.is_file() else {}
    paragraphs = re.split(r"\n\s*\n", text)
    return {"schema_version": "1.0.0", "run_id": run["run_id"], "article_sha256": af.sha256_path(article_path) if article_path else None,
            "canonical_url": (run.get("revision") or {}).get("canonical_url", (run.get("publication") or {}).get("canonical_url")),
            "first_publication_date": metadata.get("date"), "indexed_at": af.utc_now(),
            "author_evidence_kind": "generated_article", "human_resemblance": "pending",
            "title": brief.get("title"), "description": brief.get("description"),
            "sources": [{"claim_id": c.get("claim_id"), "source": c.get("source_url_or_local_id"),
                         "claim": c.get("exact_claim"), "qualification": c.get("allowed_wording"),
                         "reviewed_at": c.get("checked_at"), "freshness_horizon": c.get("freshness_horizon"),
                         "body_passages": [{"paragraph": i + 1, "sha256": digest(p), "excerpt": p[:650]}
                                           for i, p in enumerate(paragraphs) if c.get("source_url_or_local_id") and c["source_url_or_local_id"] in p],
                         "dependent_surfaces": ["article", "description", "cards", "feed"] +
                                               ["visual:" + str(v.get("visual_id")) for v in plan.get("visuals", []) if c.get("claim_id") in v.get("claim_ids", [])]}
                        for c in ledger.get("claims", [])],
            "recent_moves": {"opening": next((p[:650] for p in paragraphs if not p.startswith("#") and len(p) > 60), ""),
                             "ending": paragraphs[-1][:650] if paragraphs else "", "headings": re.findall(r"(?m)^##+ (.+)$", text)},
            "maintenance_policy": "A source event is a review signal, not a rewrite order. Distinguish cosmetic changes from changed claims; preserve URL, first publication date, author position and immutable experiments."}


def source_event(index: dict, event: dict) -> dict:
    if not event.get("source") or not event.get("before") or not event.get("after"):
        raise ValueError("Supply the source locator and actual before/after source passages")
    matched = [s for s in index["sources"] if s.get("source") == event["source"]]
    cosmetic = re.sub(r"\s+", " ", event["before"]).strip() == re.sub(r"\s+", " ", event["after"]).strip()
    return {"schema_version": "1.0.0", "run_id": index["run_id"], "source_event": event,
            "status": "cosmetic_no_revision" if cosmetic else "semantic_review_pending",
            "affected_claims": matched, "required_surfaces": sorted({v for s in matched for v in s["dependent_surfaces"]}),
            "revision_required": False, "human_decision": "pending",
            "continuity": {"canonical_url": index["canonical_url"], "first_publication_date": index["first_publication_date"]}}
