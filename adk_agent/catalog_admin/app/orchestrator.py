import os
import time
import logging
import json
from typing import Optional, Dict, Any, List
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import from app.libs (copied into app directory for deployment)
try:
    from app.libs.tools_firebase import FirebaseFunctionsClient  # type: ignore
except ImportError:
    try:
        # Fallback for local development
        from libs.tools_firebase import FirebaseFunctionsClient  # type: ignore
    except ImportError:
        FirebaseFunctionsClient = None  # type: ignore


logger = logging.getLogger("catalog_admin")
logger.setLevel(logging.INFO)

# Toggle very verbose payload logging to Cloud Logging
VERBOSE_LOG_PAYLOADS: bool = os.getenv("VERBOSE_LOG_PAYLOADS", "1").strip() != "0"


def _log_payload(label: str, obj: Any, max_chars: int = 5000) -> None:  # type: ignore[name-defined]
    if not VERBOSE_LOG_PAYLOADS:
        return
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        try:
            text = str(obj)
        except Exception:
            text = "<unserializable>"
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    logger.info({"orchestrator": "payload", "label": label, "truncated": truncated, "text": text})


def _client() -> "FirebaseFunctionsClient":  # type: ignore
    if FirebaseFunctionsClient is None:
        raise RuntimeError("FirebaseFunctionsClient not available")
    base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    api_key = os.getenv("FIREBASE_API_KEY")
    bearer = os.getenv("FIREBASE_ID_TOKEN")
    user_id = os.getenv("PIPELINE_USER_ID") or os.getenv("X_USER_ID") or "catalog_admin_engine"
    return FirebaseFunctionsClient(base_url=base_url, api_key=api_key, bearer_token=bearer, user_id=user_id)


# --- LLM sub-agents (imported from multi_agent_system) ---
try:
    from multi_agent_system.agents.triage_agent import TriageAgent  # type: ignore
    from multi_agent_system.agents.enrichment_agent import EnrichmentAgent  # type: ignore
    from multi_agent_system.agents.analyst_agent import AnalystAgent  # type: ignore
    from multi_agent_system.agents.scout_agent import ScoutAgent  # type: ignore
    from multi_agent_system.agents.specialist_agent import SpecialistAgent, SpecialistRole  # type: ignore
    from multi_agent_system.agents.schema_validator_agent import SchemaValidatorAgent as _SchemaValidator  # type: ignore
    from multi_agent_system.agents.approver_agent import ApproverAgent  # type: ignore
except Exception as e_first_import:
    try:
        logger.exception({"import": "multi_agent_system.agents", "error": str(e_first_import)})
        import sys as _sys  # type: ignore
        logger.info({"import": "sys.path", "paths": list(getattr(_sys, "path", []))[:20]})
    except Exception:
        pass
    try:
        from adk_agent.catalog_admin.multi_agent_system.agents.triage_agent import TriageAgent  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.enrichment_agent import EnrichmentAgent  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.analyst_agent import AnalystAgent  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.scout_agent import ScoutAgent  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.specialist_agent import SpecialistAgent, SpecialistRole  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.schema_validator_agent import SchemaValidatorAgent as _SchemaValidator  # type: ignore
        from adk_agent.catalog_admin.multi_agent_system.agents.approver_agent import ApproverAgent  # type: ignore
    except Exception as e_second_import:
        try:
            logger.exception({"import": "adk_agent.catalog_admin.multi_agent_system.agents", "error": str(e_second_import)})
        except Exception:
            pass
        TriageAgent = None  # type: ignore
        EnrichmentAgent = None  # type: ignore
        AnalystAgent = None  # type: ignore
        ScoutAgent = None  # type: ignore
        SpecialistAgent = None  # type: ignore
        SpecialistRole = None  # type: ignore
        _SchemaValidator = None  # type: ignore
        ApproverAgent = None  # type: ignore


def _derive_variant_from_equipment(ex: Dict[str, Any]) -> Optional[str]:
    eq = ex.get("equipment") or []
    if isinstance(eq, list) and eq:
        first = str(eq[0]).strip().lower()
        if first:
            return f"equipment:{first}"
    return None


def tool_llm_fetch_catalog(limit: int = 200) -> Dict[str, Any]:
    """Fetcher tool: returns a lightweight snapshot of catalog state."""
    fb = _client()
    out: Dict[str, Any] = {"exercises": [], "families": []}
    try:
        ex_res = fb.get("getExercises", params={"limit": limit, "canonicalOnly": True})
        _log_payload("fetch_catalog.getExercises.response", ex_res)
        if ex_res and ex_res.get("data"):
            out["exercises"] = ex_res["data"].get("items", []) or []
        elif isinstance(ex_res.get("exercises"), list):
            out["exercises"] = ex_res["exercises"]
        logger.info({"orchestrator": "fetch_catalog", "exercises": len(out["exercises"])})

        # Repair pass: some items may be partial (missing name/description). Fetch details by id.
        repaired = 0
        exercises = out["exercises"]
        id_index: Dict[str, int] = {}
        for idx, ex in enumerate(exercises):
            ex_id = ex.get("id") if isinstance(ex, dict) else None
            if ex_id:
                id_index[ex_id] = idx
        def _suspicious_name(n: Any) -> bool:
            if not isinstance(n, str):
                return True
            s = n.strip().lower()
            return s in {"", "unknown", "unknown exercise"} or len(s) < 3
        def _suspicious_desc(d: Any) -> bool:
            if not isinstance(d, str):
                return True
            return len(d.strip()) < 20
        to_fix = [
            ex for ex in exercises
            if isinstance(ex, dict)
            and ex.get("id")
            and (_suspicious_name(ex.get("name")) or _suspicious_desc(ex.get("description")))
        ]
        for ex in to_fix[: min(50, len(to_fix))]:  # cap repair calls defensively
            try:
                detail = fb.post("getExercise", {"exerciseId": ex.get("id")})
                _log_payload("fetch_catalog.getExercise.response", {"id": ex.get("id"), "response": detail})
                data = detail.get("data") if isinstance(detail, dict) else None
                full = None
                if isinstance(data, dict):
                    full = data.get("exercise") or data
                if isinstance(full, dict) and (full.get("name") or full.get("description")):
                    idx = id_index.get(ex["id"])  # type: ignore[index]
                    if idx is not None:
                        exercises[idx] = full
                        repaired += 1
            except Exception as _:
                continue
        if repaired:
            logger.info({"orchestrator": "fetch_catalog", "repaired_missing_fields": repaired})

        # Micro name/variant fixer (non-destructive): fill variant_key from equipment for downstream logic
        fixed = 0
        for ex in exercises:
            if isinstance(ex, dict) and not ex.get("variant_key"):
                v = _derive_variant_from_equipment(ex)
                if v:
                    ex["variant_key"] = v
                    fixed += 1
        if fixed:
            logger.info({"orchestrator": "fetch_catalog", "variant_key_auto_filled": fixed})
    except Exception as e:
        logger.error({"tool": "llm_fetch_catalog", "stage": "exercises", "error": str(e)})
    try:
        fam_res = fb.list_families(minSize=1, limit=1000)  # type: ignore[attr-defined]
        _log_payload("fetch_catalog.list_families.response", fam_res)
        if fam_res and fam_res.get("data"):
            out["families"] = fam_res["data"].get("families", []) or []
        elif isinstance(fam_res.get("families"), list):
            out["families"] = fam_res["families"]
        logger.info({"orchestrator": "fetch_catalog", "families": len(out["families"])})
    except Exception as e:
        logger.error({"tool": "llm_fetch_catalog", "stage": "families", "error": str(e)})
    return {"ok": True, "data": out}


def tool_llm_schema_validate(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if _SchemaValidator is None:
        raise RuntimeError("SchemaValidatorAgent unavailable")
    agent = _SchemaValidator(_client())
    logger.info(f"[Orchestrator Agent] passing {len(items) if isinstance(items, list) else 0} items to Schema Validator.")
    res = agent.process_batch(items)
    logger.info({"orchestrator": "schema_validate", "ok": bool(res)})
    _log_payload("schema_validate.response", res)
    return res


def tool_llm_triage(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if TriageAgent is None:
        raise RuntimeError("TriageAgent unavailable")
    agent = TriageAgent(_client())
    try:
        count = len(items) if isinstance(items, list) else 0
        logger.info(f"[Orchestrator Agent] passing {count} exercises to Triage Agent.")
    except Exception:
        pass
    _log_payload("triage.request", items)
    res = agent.process_batch(items)
    logger.info({"orchestrator": "triage", "normalized": res.get("exercises_normalized", 0)})
    try:
        logger.info(f"[Triage Agent] triage completed. Normalized {res.get('exercises_normalized', 0)} exercises; skipped {res.get('exercises_skipped', 0)}.")
    except Exception:
        pass
    _log_payload("triage.response", res)
    return res


def tool_llm_enrichment(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if EnrichmentAgent is None:
        raise RuntimeError("EnrichmentAgent unavailable")
    agent = EnrichmentAgent(_client())
    try:
        count = len(items) if isinstance(items, list) else 0
        logger.info(f"[Orchestrator Agent] passing {count} exercises to Enrichment Agent.")
    except Exception:
        pass
    _log_payload("enrichment.request", items)
    res = agent.process_batch(items)
    logger.info({"orchestrator": "enrichment", "aliases_added": res.get("total_aliases_added", 0)})
    try:
        logger.info(f"[Enrichment Agent] enrichment completed. Added {res.get('total_aliases_added', 0)} aliases across {res.get('exercises_enriched', 0)} exercises.")
    except Exception:
        pass
    _log_payload("enrichment.response", res)
    return res


def tool_llm_analyst(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if AnalystAgent is None:
        raise RuntimeError("AnalystAgent unavailable")
    agent = AnalystAgent(_client())
    try:
        count = len(items) if isinstance(items, list) else 0
        logger.info(f"[Orchestrator Agent] passing {count} exercises to Analyst Agent.")
    except Exception:
        pass
    _log_payload("analyst.request", items)
    res = agent.process_batch(items)
    logger.info({"orchestrator": "analyst", "analyzed": res.get("exercises_analyzed", 0), "issues": res.get("total_issues", 0)})
    try:
        logger.info(f"[Analyst Agent] analysed {res.get('exercises_analyzed', 0)} exercises, found {res.get('total_issues', 0)} issues.")
    except Exception:
        pass
    _log_payload("analyst.response", res)
    # Auto-route issues to specialists if present
    try:
        reports = res.get("reports") or []
        if reports and isinstance(reports, list):
            # Build role-specific selections: content/biomechanics/anatomy/programming
            role_fields = {
                "content": {"description", "execution_notes", "common_mistakes", "coaching_cues"},
                "biomechanics": {"movement", "metadata", "category", "equipment", "variant_key"},
                "anatomy": {"muscles"},
                "programming": {"programming_use_cases", "suitability_notes", "stimulus_tags"},
            }
            exercise_by_id = {}
            for ex in items or []:
                if isinstance(ex, dict) and ex.get("id"):
                    exercise_by_id[ex["id"]] = ex
            routed_any = False
            def _field_root(field_name: Any) -> str:
                try:
                    s = str(field_name)
                    return s.split(".")[0] if "." in s else s
                except Exception:
                    return ""
            def _belongs_to_role(field_name: Any, role_fields_for_match: set[str]) -> bool:  # type: ignore[name-defined]
                root = _field_root(field_name)
                return (str(field_name) in role_fields_for_match) or (root in role_fields_for_match)

            # Build role -> items map
            role_to_items: Dict[str, List[Dict[str, Any]]] = {}
            for role, fields in role_fields.items():
                shaped: List[Dict[str, Any]] = []
                for rep in reports:
                    ex_id = rep.get("exercise_id")
                    if not ex_id or ex_id not in exercise_by_id:
                        continue
                    role_issues: List[Dict[str, Any]] = []
                    for issue in (rep.get("issues") or []):
                        sev = (issue.get("severity") or "").lower()
                        if sev not in {"critical", "high"}:
                            continue
                        if _belongs_to_role(issue.get("field"), fields):
                            role_issues.append(issue)
                    if role_issues:
                        shaped.append({"exercise": exercise_by_id[ex_id], "target_issues": role_issues})
                logger.info({"orchestrator": "route_to_specialist_scan", "role": role, "matched_items": len(shaped)})
                if shaped:
                    routed_any = True
                    role_to_items[role] = shaped
            if not routed_any:
                logger.info({"orchestrator": "route_to_specialist", "note": "no routing triggered", "reports": len(reports or [])})
            else:
                # Run all specialists in parallel per role
                try:
                    t0 = time.time()
                    with ThreadPoolExecutor(max_workers=len(role_to_items)) as pool:
                        future_map = {}
                        for role, items in role_to_items.items():
                            logger.info({"orchestrator": "route_to_specialist", "role": role, "items": len(items), "mode": "parallel_start"})
                            future = pool.submit(tool_llm_specialist, role=role, items=items)
                            future_map[future] = role
                        for fut in as_completed(future_map):
                            role = future_map[fut]
                            try:
                                _ = fut.result()
                                logger.info({"orchestrator": "route_to_specialist", "role": role, "status": "completed"})
                            except Exception as e:
                                logger.error({"orchestrator": "route_to_specialist", "role": role, "status": "failed", "error": str(e)})
                    logger.info({"orchestrator": "route_to_specialist", "mode": "parallel_all_done", "ms": int((time.time()-t0)*1000)})
                except Exception as e:
                    logger.error({"orchestrator": "route_to_specialist", "mode": "parallel_error", "error": str(e)})
            # After specialists, re-run analyst for verification (switch to reasoning model)
            try:
                agent.switch_to_reasoning_model()  # deeper pass only on verification
            except Exception:
                pass
            # Refresh details for re-analysis to avoid stale names (e.g., 'Unknown Exercise')
            refreshed: List[Dict[str, Any]] = []
            fb = _client()
            for ex in exercise_by_id.values():
                try:
                    det = fb.post("getExercise", {"exerciseId": ex.get("id")})
                    data = det.get("data") if isinstance(det, dict) else None
                    full = data.get("exercise") if isinstance(data, dict) else None
                    refreshed.append(full if isinstance(full, dict) else ex)
                except Exception:
                    refreshed.append(ex)
            verify = agent.process_batch(refreshed)
            logger.info({"orchestrator": "post_specialist_analyst", "issues": verify.get("total_issues", 0)})
            _log_payload("analyst.post_specialist.response", verify)
            # Approver
            try:
                tool_llm_approver_decide(exercises=list(exercise_by_id.values()), reports=verify.get("reports") or [], auto_apply=True)
            except Exception as _:
                pass
    except Exception as _:
        pass
    return res


def tool_llm_scout(search_logs: Optional[List[Dict[str, Any]]] = None, create_drafts: bool = False) -> Dict[str, Any]:
    if ScoutAgent is None:
        raise RuntimeError("ScoutAgent unavailable")
    agent = ScoutAgent(_client())
    logs = search_logs or []
    try:
        logger.info(f"[Orchestrator Agent] passing {len(logs)} search logs to Scout Agent (create_drafts={create_drafts}).")
    except Exception:
        pass
    _log_payload("scout.request", {"logs": logs, "create_drafts": create_drafts})
    res = agent.process_batch(logs, create_drafts=create_drafts)
    logger.info({"orchestrator": "scout", "gaps": res.get("gaps_identified", 0), "drafts": res.get("drafts_created", 0)})
    try:
        logger.info(f"[Scout Agent] completed. Identified {res.get('gaps_identified', 0)} gaps; created {res.get('drafts_created', 0)} drafts.")
    except Exception:
        pass
    _log_payload("scout.response", res)
    return res


def tool_llm_specialist(role: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if SpecialistAgent is None or SpecialistRole is None:
        raise RuntimeError("SpecialistAgent unavailable")
    role_map = {
        "creator": SpecialistRole.CREATOR,
        "biomechanics": SpecialistRole.BIOMECHANICS,
        "anatomy": SpecialistRole.ANATOMY,
        "content": SpecialistRole.CONTENT,
        "programming": SpecialistRole.PROGRAMMING,
    }
    r = role_map.get(role.lower())
    if not r:
        raise ValueError(f"Unknown specialist role: {role}")
    agent = SpecialistAgent(_client(), r)
    _log_payload("specialist.request", {"role": role, "items": items})
    # Ensure payload shape: list of { exercise, target_issues }
    shaped: List[Dict[str, Any]] = []
    for it in items or []:
        if isinstance(it, dict) and "exercise" in it and isinstance(it.get("exercise"), dict):
            shaped.append({"exercise": it["exercise"], "target_issues": it.get("target_issues", []) or []})
        elif isinstance(it, dict):
            # Treat as bare exercise
            shaped.append({"exercise": it, "target_issues": []})
    if not shaped and items:
        shaped = [{"exercise": items[0], "target_issues": []}] if isinstance(items[0], dict) else []
    try:
        logger.info(f"[Orchestrator Agent] passing {len(shaped)} exercises to Specialist Agent ({role}).")
    except Exception:
        pass
    _log_payload("specialist.shaped_request", {"role": role, "items": shaped})
    res = agent.process_batch(shaped)
    logger.info({"orchestrator": "specialist", "role": role, "improved": res.get("exercises_improved", 0)})
    try:
        logger.info(f"[Specialist Agent:{role}] completed. Improved {res.get('exercises_improved', 0)}; skipped {res.get('exercises_skipped', 0)}.")
    except Exception:
        pass
    _log_payload("specialist.response", res)
    return res


def tool_llm_approver_decide(exercises: List[Dict[str, Any]], reports: List[Dict[str, Any]], auto_apply: bool = True) -> Dict[str, Any]:
    """Evaluate approval for exercises using ApproverAgent and optionally mark approved."""
    if ApproverAgent is None:
        raise RuntimeError("ApproverAgent unavailable")
    fb = _client()
    agent = ApproverAgent(fb)
    id_to_ex = {ex.get("id"): ex for ex in exercises if isinstance(ex, dict)}
    decisions: List[Dict[str, Any]] = []
    approved_count = 0
    try:
        logger.info(f"[Orchestrator Agent] passing {len(reports or [])} reports for {len(exercises or [])} exercises to Approver Agent (auto_apply={auto_apply}).")
    except Exception:
        pass
    _log_payload("approver.request", {"exercises": exercises, "reports": reports, "auto_apply": auto_apply})
    for r in reports or []:
        ex_id = r.get("exercise_id")
        if not ex_id or ex_id not in id_to_ex:
            continue
        decision = agent.evaluate(r, id_to_ex[ex_id])
        if decision.get("approve") and auto_apply:
            try:
                resp = fb.post("approveExercise", {"exercise_id": ex_id})
                _log_payload("approver.approveExercise.response", {"exercise_id": ex_id, "response": resp})
                approved_count += 1
            except Exception as e:
                decision["error"] = str(e)
        decisions.append({"exercise_id": ex_id, **decision})
    logger.info({"orchestrator": "approver", "approved": approved_count, "checked": len(decisions)})
    try:
        logger.info(f"[Approver Agent] completed. Approved {approved_count} of {len(decisions)} exercises.")
    except Exception:
        pass
    _log_payload("approver.response", {"decisions": decisions, "approved": approved_count})
    return {"decisions": decisions, "approved": approved_count}


def tool_get_exercise(name: Optional[str] = None, slug: Optional[str] = None, exerciseId: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().get_exercise(exerciseId=exerciseId, name=name, slug=slug)
        logger.info({"tool": "get_exercise", "args": {"name": name, "slug": slug, "exerciseId": exerciseId}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("get_exercise.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "get_exercise", "args": {"name": name, "slug": slug, "exerciseId": exerciseId}, "ok": False, "error": str(e)})
        raise


def tool_upsert_exercise(exercise: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    try:
        _log_payload("upsert_exercise.request", exercise)
        res = _client().upsert_exercise(exercise)
        logger.info({"tool": "upsert_exercise", "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("upsert_exercise.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "upsert_exercise", "ok": False, "error": str(e)})
        raise


def tool_ensure_exercise_exists(name: str) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().ensure_exercise_exists(name)
        logger.info({"tool": "ensure_exercise_exists", "args": {"name": name}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("ensure_exercise_exists.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "ensure_exercise_exists", "args": {"name": name}, "ok": False, "error": str(e)})
        raise


def tool_upsert_alias(alias_slug: str, exercise_id: str, family_slug: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.time()
    try:
        _log_payload("upsert_alias.request", {"alias_slug": alias_slug, "exercise_id": exercise_id, "family_slug": family_slug})
        res = _client().upsert_alias(alias_slug, exercise_id, family_slug)
        logger.info({"tool": "upsert_alias", "args": {"alias_slug": alias_slug, "exercise_id": exercise_id}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("upsert_alias.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "upsert_alias", "args": {"alias_slug": alias_slug, "exercise_id": exercise_id}, "ok": False, "error": str(e)})
        raise


def tool_delete_alias(alias_slug: str) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().delete_alias(alias_slug)
        logger.info({"tool": "delete_alias", "args": {"alias_slug": alias_slug}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("delete_alias.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "delete_alias", "args": {"alias_slug": alias_slug}, "ok": False, "error": str(e)})
        raise


def tool_search_aliases(q: str) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().search_aliases(q)
        logger.info({"tool": "search_aliases", "args": {"q": q}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("search_aliases.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "search_aliases", "args": {"q": q}, "ok": False, "error": str(e)})
        raise


def tool_list_families(minSize: int = 1, limit: int = 1000) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().list_families(minSize=minSize, limit=limit)
        logger.info({"tool": "list_families", "args": {"minSize": minSize, "limit": limit}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("list_families.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "list_families", "args": {"minSize": minSize, "limit": limit}, "ok": False, "error": str(e)})
        raise


def tool_normalize_catalog_page(pageSize: int = 50, startAfterName: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.time()
    try:
        res = _client().normalize_catalog_page(pageSize=pageSize, startAfterName=startAfterName)
        logger.info({"tool": "normalize_catalog_page", "args": {"pageSize": pageSize}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("normalize_catalog_page.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "normalize_catalog_page", "args": {"pageSize": pageSize}, "ok": False, "error": str(e)})
        raise


def tool_get_exercises(limit: int = 200) -> Dict[str, Any]:
    """Get all exercises from the catalog."""
    t0 = time.time()
    try:
        res = _client().get("getExercises", params={"limit": limit, "canonicalOnly": True})
        logger.info({"tool": "get_exercises", "args": {"limit": limit}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("get_exercises.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "get_exercises", "args": {"limit": limit}, "ok": False, "error": str(e)})
        raise


def tool_search_exercises(
    query: Optional[str] = None,
    equipment: Optional[str] = None,
    muscleGroup: Optional[str] = None,
    movementType: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Search exercises with flexible filters."""
    t0 = time.time()
    try:
        params = {"limit": limit, "canonicalOnly": True}
        if query:
            params["query"] = query
        if equipment:
            params["equipment"] = equipment
        if muscleGroup:
            params["muscleGroup"] = muscleGroup
        if movementType:
            params["movementType"] = movementType
        res = _client().get("searchExercises", params=params)
        logger.info({"tool": "search_exercises", "args": params, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("search_exercises.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "search_exercises", "args": params, "ok": False, "error": str(e)})
        raise


def tool_resolve_exercise(q: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve the best exercise match for a query."""
    t0 = time.time()
    try:
        body = {"q": q}
        if context:
            body["context"] = context
        res = _client().post("resolveExercise", body)
        logger.info({"tool": "resolve_exercise", "args": {"q": q}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("resolve_exercise.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "resolve_exercise", "args": {"q": q}, "ok": False, "error": str(e)})
        raise


def tool_approve_exercise(exercise_id: str) -> Dict[str, Any]:
    """Mark an exercise as approved."""
    t0 = time.time()
    try:
        res = _client().post("approveExercise", {"exercise_id": exercise_id})
        logger.info({"tool": "approve_exercise", "args": {"exercise_id": exercise_id}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("approve_exercise.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "approve_exercise", "args": {"exercise_id": exercise_id}, "ok": False, "error": str(e)})
        raise


def tool_refine_exercise(exercise_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Refine exercise metadata."""
    t0 = time.time()
    try:
        _log_payload("refine_exercise.request", {"exercise_id": exercise_id, "updates": updates})
        res = _client().post("refineExercise", {"exercise_id": exercise_id, "updates": updates})
        logger.info({"tool": "refine_exercise", "args": {"exercise_id": exercise_id}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("refine_exercise.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "refine_exercise", "args": {"exercise_id": exercise_id}, "ok": False, "error": str(e)})
        raise


def tool_merge_exercises(source_id: str, target_id: str) -> Dict[str, Any]:
    """Merge duplicate exercises."""
    t0 = time.time()
    try:
        res = _client().post("mergeExercises", {"source_id": source_id, "target_id": target_id})
        logger.info({"tool": "merge_exercises", "args": {"source_id": source_id, "target_id": target_id}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("merge_exercises.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "merge_exercises", "args": {"source_id": source_id, "target_id": target_id}, "ok": False, "error": str(e)})
        raise


def tool_suggest_family_variant(name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Suggest family_slug and variant_key for an exercise."""
    t0 = time.time()
    try:
        body = {"name": name}
        if metadata:
            body["metadata"] = metadata
        res = _client().post("suggestFamilyVariant", body)
        logger.info({"tool": "suggest_family_variant", "args": {"name": name}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("suggest_family_variant.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "suggest_family_variant", "args": {"name": name}, "ok": False, "error": str(e)})
        raise


def tool_suggest_aliases(exercise: Dict[str, Any]) -> Dict[str, Any]:
    """Suggest alias candidates for an exercise."""
    t0 = time.time()
    try:
        res = _client().post("suggestAliases", {"exercise": exercise})
        logger.info({"tool": "suggest_aliases", "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("suggest_aliases.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "suggest_aliases", "ok": False, "error": str(e)})
        raise


def tool_backfill_normalize_family(family: str, apply: bool = False, limit: int = 1000) -> Dict[str, Any]:
    """Normalize and optionally merge duplicates within a family."""
    t0 = time.time()
    try:
        res = _client().post("backfillNormalizeFamily", {"family": family, "apply": apply, "limit": limit})
        logger.info({"tool": "backfill_normalize_family", "args": {"family": family, "apply": apply}, "ok": True, "ms": int((time.time()-t0)*1000)})
        _log_payload("backfill_normalize_family.response", res)
        return res
    except Exception as e:
        logger.error({"tool": "backfill_normalize_family", "args": {"family": family, "apply": apply}, "ok": False, "error": str(e)})
        raise


catalog_admin_instruction = (
    "You are the Exercise Catalog Orchestrator (LLM), responsible for maintaining a high-quality exercise database.\n"
    "Your capabilities include:\n"
    "- Browse and search the entire exercise catalog\n"
    "- Create, update, and refine exercise metadata\n"
    "- Manage the alias registry for exercise name resolution\n"
    "- Detect and merge duplicate exercises within the same family/variant\n"
    "- Normalize exercise names, families, and variants\n"
    "- Approve exercises after quality review\n"
    "\n"
    "Mandatory execution plan (do not stop early):\n"
    "1) Call tool_llm_fetch_catalog (canonical-only).\n"
    "2) Immediately call tool_llm_analyst on the fetched exercises (respect the limit).\n"
    "3) If the Analyst reports issues, route to Specialists by role: for each of {content, biomechanics, anatomy, programming},\n"
    "   build items as [{ 'exercise': <exercise JSON>, 'target_issues': [ { 'field': str, 'issue_type': str, 'severity': str, 'description': str } ] }]\n"
    "   selecting issues relevant to that role (prefer critical/high first), then call tool_llm_specialist(role=<role>, items=<items>).\n"
    "4) After specialists complete, call tool_llm_analyst again on the refreshed exercises to verify improvements.\n"
    "5) Call tool_llm_approver_decide(exercises=<current set>, reports=<latest analyst reports>, auto_apply=True).\n"
    "Only skip a step if there are zero exercises, otherwise execute all steps above in order.\n"
    "\n"
    "Key principles:\n"
    "- Use tool_get_exercises or tool_search_exercises to explore the catalog (pass canonicalOnly=true)\n"
    "- Use tool_resolve_exercise to find best matches for queries\n"
    "- Use tool_ensure_exercise_exists before upsert when uncertain\n"
    "- Keep canonical names verbose (e.g., 'Barbell Back Squat' not 'BB Squat')\n"
    "- Shorthands belong only as alias slugs (e.g., 'bb-squat', 'ohp', 'rdl')\n"
    "- Use tool_suggest_family_variant and tool_suggest_aliases for consistency\n"
    "- Never merge exercises across different family_slug::variant_key combinations\n"
    "- Use tool_backfill_normalize_family to clean up entire families at once\n"
    "- Use tool_llm_approver_decide to evaluate and apply approvals; do not call tool_approve_exercise directly unless explicitly required.\n"
)


catalog_admin_tools = [
    FunctionTool(func=tool_get_exercise),
    FunctionTool(func=tool_get_exercises),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_resolve_exercise),
    FunctionTool(func=tool_upsert_exercise),
    FunctionTool(func=tool_ensure_exercise_exists),
    FunctionTool(func=tool_approve_exercise),
    FunctionTool(func=tool_refine_exercise),
    FunctionTool(func=tool_merge_exercises),
    FunctionTool(func=tool_suggest_family_variant),
    FunctionTool(func=tool_suggest_aliases),
    FunctionTool(func=tool_upsert_alias),
    FunctionTool(func=tool_delete_alias),
    FunctionTool(func=tool_search_aliases),
    FunctionTool(func=tool_list_families),
    FunctionTool(func=tool_normalize_catalog_page),
    FunctionTool(func=tool_backfill_normalize_family),
    # LLM sub-agent orchestration
    FunctionTool(func=tool_llm_fetch_catalog),
    FunctionTool(func=tool_llm_schema_validate),
    FunctionTool(func=tool_llm_triage),
    FunctionTool(func=tool_llm_enrichment),
    FunctionTool(func=tool_llm_analyst),
    FunctionTool(func=tool_llm_scout),
    FunctionTool(func=tool_llm_specialist),
    FunctionTool(func=tool_llm_approver_decide),
]


root_agent = Agent(
    name="CatalogAdmin",
    model=os.getenv("CATALOG_ADMIN_MODEL", "gemini-2.5-pro"),
    instruction=catalog_admin_instruction,
    tools=catalog_admin_tools,
)


