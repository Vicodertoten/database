from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable


class PostgresInspectionStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    # ------------------------------------------------------------------
    # Qualification metrics
    # ------------------------------------------------------------------

    def fetch_qualification_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        with self._connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM qualified_resources_history
                    WHERE run_id = %s
                    """,
                    (run_id,),
                ).fetchall()
                payloads = [
                    json.loads(str(row["payload_json"]))
                    for row in rows
                ]
            else:
                rows = connection.execute(
                    """
                    SELECT
                        qualification_status,
                        provenance_summary_json,
                        qualification_flags_json,
                        license_safety_result,
                        export_eligible
                    FROM qualified_resources
                    """
                ).fetchall()
                payloads = [
                    {
                        "qualification_status": row["qualification_status"],
                        "provenance_summary": json.loads(str(row["provenance_summary_json"])),
                        "qualification_flags": json.loads(str(row["qualification_flags_json"])),
                        "license_safety_result": row["license_safety_result"],
                        "export_eligible": bool(row["export_eligible"]),
                    }
                    for row in rows
                ]
            accepted_resources = 0
            rejected_resources = 0
            review_required_resources = 0
            ai_qualified_images = 0
            exportable_resources = 0
            flag_counts: Counter[str] = Counter()
            license_distribution: Counter[str] = Counter()
            ai_model_distribution: Counter[str] = Counter()
            for payload in payloads:
                qualification_status = str(payload.get("qualification_status", ""))
                if qualification_status == "accepted":
                    accepted_resources += 1
                elif qualification_status == "rejected":
                    rejected_resources += 1
                elif qualification_status == "review_required":
                    review_required_resources += 1
                provenance = payload.get("provenance_summary")
                if not isinstance(provenance, dict):
                    provenance = {}
                if provenance.get("ai_model"):
                    ai_qualified_images += 1
                    ai_model_distribution[str(provenance["ai_model"])] += 1
                if bool(payload.get("export_eligible")):
                    exportable_resources += 1
                license_distribution[str(payload.get("license_safety_result", "unknown"))] += 1
                qualification_flags = payload.get("qualification_flags")
                if not isinstance(qualification_flags, list):
                    qualification_flags = []
                for flag in qualification_flags:
                    flag_counts[flag] += 1

            if run_id:
                review_queue_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM review_queue_history
                    WHERE run_id = %s
                    """,
                    (run_id,),
                ).fetchone()["count"]
            else:
                review_queue_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM review_queue"
                ).fetchone()["count"]
            return {
                "accepted_resources": accepted_resources,
                "rejected_resources": rejected_resources,
                "review_required_resources": review_required_resources,
                "ai_qualified_images": ai_qualified_images,
                "exportable_resources": exportable_resources,
                "review_queue_count": review_queue_count,
                "top_rejection_flags": dict(flag_counts.most_common(5)),
                "license_distribution": dict(sorted(license_distribution.items())),
                "ai_model_distribution": dict(sorted(ai_model_distribution.items())),
            }
