"""
Schema Validator Agent
Normalizes exercise objects to the canonical model and applies safe merges.
"""

from typing import Any, Dict, List


class SchemaValidatorAgent:
    """
    Lightweight normalizer for exercises before analysis.
    - Maps legacy/alternate fields into canonical ones (e.g., refined_execution_notes → execution_notes)
    - Coerces basic types on canonical fields
    - Applies upsert merges (no deletions) when a change improves canonical fields
    """

    CANONICAL_FIELDS = {
        "id",
        "name",
        "family_slug",
        "variant_key",
        "category",
        "equipment",
        "movement",
        "metadata",
        "muscles",
        "description",
        "execution_notes",
        "common_mistakes",
        "programming_use_cases",
        "suitability_notes",
        "stimulus_tags",
        "status",
        "version",
        "aliases",
    }

    LEGACY_MAPPINGS = {
        # legacy_key -> canonical_key
        "refined_execution_notes": "execution_notes",
    }

    def __init__(self, firebase_client):
        self.firebase_client = firebase_client

    def process_batch(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        changed = 0
        merged = 0
        skipped = 0
        details: List[Dict[str, Any]] = []

        for ex in exercises:
            if not ex or not isinstance(ex, dict):
                skipped += 1
                continue

            exercise_id = ex.get("id")
            name = ex.get("name")
            if not name:
                skipped += 1
                continue

            clean_updates: Dict[str, Any] = {"name": name}

            # Map legacy fields into canonical
            legacy_applied = False
            # refined_execution_notes → execution_notes (merge unique)
            if isinstance(ex.get("refined_execution_notes"), list):
                legacy_applied = True
                merged_notes = list({
                    *(ex.get("execution_notes") or []),
                    *[str(s).strip() for s in ex.get("refined_execution_notes") if str(s).strip()],
                })
                # keep stable order by sorting on lowercase then length
                merged_notes = sorted(set(merged_notes), key=lambda s: (s.lower(), len(s)))[:10]
                clean_updates["execution_notes"] = merged_notes

            # Coerce arrays and split single long strings into arrays for content fields
            def _clean_str_list(arr):
                return [str(s).strip() for s in arr if str(s).strip()]

            def _split_bullets(text: str) -> List[str]:
                import re
                t = str(text)
                # remove markdown emphasis and bullets
                t = re.sub(r"[*_`]+", "", t)
                # split on newlines or sentence boundaries and bullets
                parts = re.split(r"\n+|\s*\*\s+|\s*•\s+|\s*\-\s+|(?<=[.!?])\s+", t)
                parts = [p.strip() for p in parts if p and len(p.strip()) > 2]
                # dedupe and cap
                out = []
                seen = set()
                for p in parts:
                    key = p.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
                    if len(out) >= 7:
                        break
                return out

            # common_mistakes
            if isinstance(ex.get("common_mistakes"), list):
                clean_updates["common_mistakes"] = _clean_str_list(ex["common_mistakes"])[:10]
            # programming_use_cases: split if single long string present
            puc = ex.get("programming_use_cases")
            if isinstance(puc, list):
                if len(puc) == 1 and isinstance(puc[0], str) and len(puc[0]) > 80:
                    clean_updates["programming_use_cases"] = _split_bullets(puc[0])[:7]
                else:
                    clean_updates["programming_use_cases"] = _clean_str_list(puc)[:10]
            # suitability_notes: split if single long string present
            sn = ex.get("suitability_notes")
            if isinstance(sn, list):
                if len(sn) == 1 and isinstance(sn[0], str) and len(sn[0]) > 80:
                    clean_updates["suitability_notes"] = _split_bullets(sn[0])[:7]
                else:
                    clean_updates["suitability_notes"] = _clean_str_list(sn)[:10]
            # stimulus tags
            if isinstance(ex.get("stimulus_tags"), list):
                clean_updates["stimulus_tags"] = _clean_str_list(ex["stimulus_tags"])[:10]

            # Only write when we actually have useful canonical improvements beyond name
            updates_to_write = {k: v for k, v in clean_updates.items() if k != "name"}
            if updates_to_write:
                if exercise_id:
                    updates_to_write["id"] = exercise_id
                updates_to_write["name"] = name
                try:
                    self.firebase_client.post("upsertExercise", {"exercise": updates_to_write})
                    changed += 1
                    if legacy_applied:
                        merged += 1
                    details.append({"id": exercise_id, "name": name, "updated_fields": list(updates_to_write.keys())})
                except Exception as e:
                    details.append({"id": exercise_id, "name": name, "error": str(e)})
            else:
                skipped += 1

        return {
            "exercises_processed": len(exercises),
            "exercises_changed": changed,
            "legacy_merged": merged,
            "skipped": skipped,
            "details": details,
        }


