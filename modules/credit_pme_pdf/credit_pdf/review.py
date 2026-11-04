"""Validation humaine séparée des valeurs brutes, sans certification des pièces."""
import copy
from datetime import datetime, timezone


def apply_review(extraction, decisions, reviewer):
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("reviewer_required")
    if not isinstance(decisions, dict) or not decisions:
        raise ValueError("nonempty_decisions_required")
    evidence = {v["id"] for v in extraction["evidence"] + extraction["tables"] + extraction["form_fields"]}
    result = copy.deepcopy(extraction)
    records = []
    for key, decision in decisions.items():
        if key not in result["fields"]:
            raise ValueError("unknown_field:" + key)
        if not isinstance(decision, dict):
            raise ValueError("invalid_decision")
        ids = decision.get("evidence_ids", [])
        if not isinstance(ids, list) or any(not isinstance(e, str) for e in ids):
            raise ValueError("invalid_evidence_ids")
        if not ids or not set(ids).issubset(evidence):
            raise ValueError("valid_evidence_required:" + key)
        if "value" not in decision or not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
            raise ValueError("value_and_reason_required:" + key)
        record = {"field": key, "value": decision["value"], "evidence_ids": ids,
                  "reason": decision["reason"], "reviewer": reviewer.strip(),
                  "reviewed_at": datetime.now(timezone.utc).isoformat(),
                  "status": "human_transcription_reviewed_not_authenticity_verified"}
        records.append(record)
    result.setdefault("review_history", []).extend(records)
    result["review_status"] = "partially_reviewed"
    # Aucun passage automatique à ready_for_scoring : règles du noyau absentes.
    result["ready_for_scoring"] = False
    return result
