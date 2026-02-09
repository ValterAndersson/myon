#!/usr/bin/env python3
"""Comprehensive analysis of the exercises catalog dump."""

import json
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher


def load_data(path):
    with open(path, "r") as f:
        data = json.load(f)
    return data


def is_populated(value):
    """Check if a value is meaningfully populated (non-null, non-empty)."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    return bool(value)


def analyze_catalog(path):
    data = load_data(path)
    meta = data.get("_export_metadata", {})
    exercises = data.get("exercises", [])
    total = len(exercises)

    print("=" * 80)
    print("EXERCISES CATALOG ANALYSIS")
    print("=" * 80)

    # 1. Overview
    print(f"\n## 1. OVERVIEW")
    print(f"  Export date:     {meta.get('exported_at', 'unknown')}")
    print(f"  Metadata total:  {meta.get('total_exercises', 'unknown')}")
    print(f"  Actual count:    {total}")

    # 2. Discover all fields (flat and nested)
    print(f"\n## 2. SCHEMA DISCOVERY")
    field_counter = Counter()
    all_fields = set()

    def count_fields(obj, prefix=""):
        for k, v in obj.items():
            full_key = f"{prefix}{k}" if prefix else k
            all_fields.add(full_key)
            field_counter[full_key] += 1
            if isinstance(v, dict) and full_key not in ("review_metadata",):
                count_fields(v, f"{full_key}.")

    for ex in exercises:
        count_fields(ex)

    sorted_fields = sorted(all_fields)
    print(f"  Total unique field paths: {len(sorted_fields)}")
    print(f"\n  Field                                    Count    %")
    print(f"  {'─' * 55}")
    for f in sorted_fields:
        cnt = field_counter[f]
        pct = cnt / total * 100
        print(f"  {f:<40} {cnt:>5}  {pct:>6.1f}%")

    # 3. Field completeness (populated = non-null, non-empty)
    print(f"\n## 3. FIELD COMPLETENESS (populated values)")
    expected_fields = [
        "name", "name_slug", "family_slug", "_doc_id",
        "equipment", "category", "description",
        "muscles", "muscles.primary", "muscles.secondary",
        "muscles.category", "muscles.contribution",
        "metadata", "metadata.level", "metadata.plane_of_motion",
        "metadata.unilateral",
        "movement", "movement.type", "movement.split",
        "execution_notes", "common_mistakes", "coaching_cues",
        "suitability_notes", "programming_use_cases", "stimulus_tags",
        "instructions", "tips",
        "review_metadata", "updated_at", "created_at", "created_by",
        "status", "version",
    ]

    populated_counts = Counter()
    for ex in exercises:
        for field in expected_fields:
            parts = field.split(".")
            val = ex
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if is_populated(val):
                populated_counts[field] += 1

    print(f"\n  Field                                  Populated    %     Missing    %")
    print(f"  {'─' * 72}")
    for f in expected_fields:
        pop = populated_counts[f]
        miss = total - pop
        pop_pct = pop / total * 100
        miss_pct = miss / total * 100
        print(f"  {f:<38} {pop:>5}  {pop_pct:>6.1f}%   {miss:>5}  {miss_pct:>6.1f}%")

    # 4. Data quality issues
    print(f"\n## 4. DATA QUALITY ISSUES")

    # 4a. Missing names
    missing_names = [ex for ex in exercises if not is_populated(ex.get("name"))]
    print(f"\n  ### 4a. Missing names: {len(missing_names)}")
    for ex in missing_names[:10]:
        print(f"    - doc_id={ex.get('_doc_id', '?')}")

    # 4b. Duplicate names
    name_counts = Counter(ex.get("name", "").strip().lower() for ex in exercises if ex.get("name"))
    dupes = {name: cnt for name, cnt in name_counts.items() if cnt > 1}
    print(f"\n  ### 4b. Duplicate names (exact, case-insensitive): {len(dupes)} names")
    for name, cnt in sorted(dupes.items(), key=lambda x: -x[1]):
        ids = [ex.get("_doc_id", "?") for ex in exercises
               if ex.get("name", "").strip().lower() == name]
        print(f"    - \"{name}\" x{cnt}: {ids}")

    # 4c. Category values
    print(f"\n  ### 4c. Category values distribution")
    valid_categories = {"compound", "isolation", "cardio", "mobility", "core"}
    cat_counts = Counter(ex.get("category", "<missing>") for ex in exercises)
    for cat, cnt in cat_counts.most_common():
        flag = "" if cat in valid_categories else " *** UNEXPECTED ***"
        print(f"    - {cat!r:20} {cnt:>5}  ({cnt/total*100:.1f}%){flag}")

    invalid_cat_exercises = [
        ex for ex in exercises
        if ex.get("category") and ex.get("category") not in valid_categories
    ]
    if invalid_cat_exercises:
        print(f"    Exercises with invalid category: {len(invalid_cat_exercises)}")
        for ex in invalid_cat_exercises[:10]:
            print(f"      - {ex.get('name', '?')} -> category={ex.get('category')!r}  "
                  f"doc_id={ex.get('_doc_id', '?')}")

    # 4d. Equipment analysis
    print(f"\n  ### 4d. Equipment values distribution")
    equip_counter = Counter()
    empty_equip = 0
    null_equip = 0
    missing_equip = 0
    for ex in exercises:
        eq = ex.get("equipment")
        if eq is None:
            null_equip += 1
        elif isinstance(eq, list):
            if len(eq) == 0:
                empty_equip += 1
            for e in eq:
                equip_counter[e] += 1
        else:
            missing_equip += 1
    print(f"    Null equipment: {null_equip}")
    print(f"    Empty array []: {empty_equip}")
    print(f"    Non-list type:  {missing_equip}")
    print(f"\n    Equipment values (top 30):")
    for eq, cnt in equip_counter.most_common(30):
        print(f"      {eq!r:35} {cnt:>5}")

    # 4e. Status values
    print(f"\n  ### 4e. Status values distribution")
    valid_statuses = {"approved", "deprecated", "merged", "draft"}
    status_counts = Counter(ex.get("status", "<missing>") for ex in exercises)
    for status, cnt in status_counts.most_common():
        flag = "" if status in valid_statuses else " *** UNEXPECTED ***"
        print(f"    - {status!r:20} {cnt:>5}  ({cnt/total*100:.1f}%){flag}")

    # 4f. Array fields: null vs empty vs missing
    print(f"\n  ### 4f. Array fields: null vs empty [] vs missing vs populated")
    array_fields = [
        "equipment", "execution_notes", "common_mistakes", "coaching_cues",
        "suitability_notes", "programming_use_cases", "stimulus_tags", "tips",
    ]
    print(f"    {'Field':<30} {'Populated':>10} {'Empty []':>10} {'Null':>10} {'Missing':>10}")
    print(f"    {'─' * 70}")
    for af in array_fields:
        populated = 0
        empty = 0
        null = 0
        missing = 0
        for ex in exercises:
            val = ex.get(af, "__MISSING__")
            if val == "__MISSING__":
                missing += 1
            elif val is None:
                null += 1
            elif isinstance(val, list) and len(val) == 0:
                empty += 1
            else:
                populated += 1
        print(f"    {af:<30} {populated:>10} {empty:>10} {null:>10} {missing:>10}")

    # 5. Enrichment/review status
    print(f"\n## 5. ENRICHMENT & REVIEW STATUS")

    # 5a. review_metadata
    has_review = sum(1 for ex in exercises if is_populated(ex.get("review_metadata")))
    print(f"\n  ### 5a. review_metadata presence: {has_review}/{total} ({has_review/total*100:.1f}%)")

    if has_review > 0:
        needs_review_true = 0
        needs_review_false = 0
        needs_full_review_true = 0
        needs_full_review_false = 0
        quality_scores = []
        review_versions = Counter()
        for ex in exercises:
            rm = ex.get("review_metadata")
            if not rm:
                continue
            if rm.get("needs_review") is True:
                needs_review_true += 1
            elif rm.get("needs_review") is False:
                needs_review_false += 1
            if rm.get("needs_full_review") is True:
                needs_full_review_true += 1
            elif rm.get("needs_full_review") is False:
                needs_full_review_false += 1
            qs = rm.get("quality_score")
            if qs is not None:
                quality_scores.append(qs)
            rv = rm.get("review_version")
            if rv:
                review_versions[rv] += 1

        print(f"    needs_review=true:      {needs_review_true}")
        print(f"    needs_review=false:     {needs_review_false}")
        print(f"    needs_full_review=true: {needs_full_review_true}")
        print(f"    needs_full_review=false:{needs_full_review_false}")
        if quality_scores:
            avg_qs = sum(quality_scores) / len(quality_scores)
            min_qs = min(quality_scores)
            max_qs = max(quality_scores)
            print(f"    quality_score: avg={avg_qs:.3f}, min={min_qs:.3f}, max={max_qs:.3f}, n={len(quality_scores)}")
            # Distribution buckets
            buckets = Counter()
            for qs in quality_scores:
                if qs >= 0.9:
                    buckets["0.9-1.0"] += 1
                elif qs >= 0.8:
                    buckets["0.8-0.9"] += 1
                elif qs >= 0.7:
                    buckets["0.7-0.8"] += 1
                elif qs >= 0.5:
                    buckets["0.5-0.7"] += 1
                else:
                    buckets["<0.5"] += 1
            print(f"    quality_score distribution:")
            for bucket in ["<0.5", "0.5-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]:
                print(f"      {bucket:>8}: {buckets.get(bucket, 0):>5}")
        print(f"    review_version distribution:")
        for rv, cnt in review_versions.most_common():
            print(f"      {rv!r:>8}: {cnt:>5}")

    # 5b. created_by / source
    print(f"\n  ### 5b. Source / created_by distribution")
    created_by_counts = Counter(ex.get("created_by", "<missing>") for ex in exercises)
    for cb, cnt in created_by_counts.most_common():
        print(f"    - {cb!r:40} {cnt:>5}  ({cnt/total*100:.1f}%)")

    # Check for other source-related fields
    source_counts = Counter()
    for ex in exercises:
        src = ex.get("source")
        if src is not None:
            source_counts[str(src)] += 1
    if source_counts:
        print(f"\n    'source' field distribution:")
        for s, cnt in source_counts.most_common():
            print(f"      {s!r:40} {cnt:>5}")
    else:
        print(f"    'source' field: not present in any exercise")

    # 5c. enrichment-specific fields
    print(f"\n  ### 5c. Enrichment-related fields")
    enrich_fields = ["enrichment_status", "enriched_at", "enriched_by",
                     "enrichment_version", "last_enriched_at"]
    for ef in enrich_fields:
        cnt = sum(1 for ex in exercises if ex.get(ef) is not None)
        print(f"    {ef}: {cnt}/{total}")

    # 6. Family grouping
    print(f"\n## 6. FAMILY GROUPING (family_slug)")
    family_slugs = Counter()
    missing_family = 0
    for ex in exercises:
        fs = ex.get("family_slug")
        if not fs:
            missing_family += 1
        else:
            family_slugs[fs] += 1
    print(f"  Total unique families: {len(family_slugs)}")
    print(f"  Exercises with family_slug: {total - missing_family}/{total} ({(total-missing_family)/total*100:.1f}%)")
    print(f"  Missing family_slug: {missing_family}")

    # Family size distribution
    family_sizes = Counter(cnt for cnt in family_slugs.values())
    print(f"\n  Family size distribution:")
    print(f"    {'Size':>6}  {'Families':>10}  {'Total exercises':>16}")
    print(f"    {'─' * 36}")
    for size in sorted(family_sizes.keys()):
        print(f"    {size:>6}  {family_sizes[size]:>10}  {size * family_sizes[size]:>16}")

    # Largest families
    print(f"\n  Top 20 largest families:")
    for slug, cnt in family_slugs.most_common(20):
        names = [ex.get("name", "?") for ex in exercises if ex.get("family_slug") == slug][:5]
        print(f"    {slug:<40} {cnt:>3} exercises")
        for n in names:
            print(f"      - {n}")

    # Single-word family slugs that might be truncated
    print(f"\n  Potentially truncated family_slugs (very short, 1-3 chars):")
    short_slugs = [(slug, cnt) for slug, cnt in family_slugs.items() if len(slug) <= 3]
    if short_slugs:
        for slug, cnt in sorted(short_slugs):
            names = [ex.get("name", "?") for ex in exercises if ex.get("family_slug") == slug]
            print(f"    {slug!r}: {cnt} exercises -> {names}")
    else:
        print(f"    None found")

    # 7. Muscles analysis
    print(f"\n## 7. MUSCLES ANALYSIS")
    primary_muscles = Counter()
    secondary_muscles = Counter()
    muscle_categories = Counter()

    has_muscles_obj = 0
    has_primary = 0
    has_secondary = 0
    has_category = 0
    has_contribution = 0
    empty_primary = 0
    empty_secondary = 0

    for ex in exercises:
        m = ex.get("muscles")
        if m and isinstance(m, dict):
            has_muscles_obj += 1
            pm = m.get("primary", [])
            sm = m.get("secondary", [])
            cat = m.get("category", [])
            contrib = m.get("contribution", {})

            if isinstance(pm, list):
                if len(pm) > 0:
                    has_primary += 1
                    for muscle in pm:
                        primary_muscles[muscle] += 1
                else:
                    empty_primary += 1

            if isinstance(sm, list):
                if len(sm) > 0:
                    has_secondary += 1
                    for muscle in sm:
                        secondary_muscles[muscle] += 1
                else:
                    empty_secondary += 1

            if isinstance(cat, list) and len(cat) > 0:
                has_category += 1
                for c in cat:
                    muscle_categories[c] += 1

            if isinstance(contrib, dict) and len(contrib) > 0:
                has_contribution += 1

    print(f"  Has muscles object:     {has_muscles_obj}/{total} ({has_muscles_obj/total*100:.1f}%)")
    print(f"  Has muscles.primary:    {has_primary}/{total} ({has_primary/total*100:.1f}%)")
    print(f"  Empty muscles.primary:  {empty_primary}/{total}")
    print(f"  Has muscles.secondary:  {has_secondary}/{total} ({has_secondary/total*100:.1f}%)")
    print(f"  Empty muscles.secondary:{empty_secondary}/{total}")
    print(f"  Has muscles.category:   {has_category}/{total} ({has_category/total*100:.1f}%)")
    print(f"  Has muscles.contribution:{has_contribution}/{total} ({has_contribution/total*100:.1f}%)")

    # Check for casing inconsistencies in muscle names
    print(f"\n  Primary muscle values (all):")
    for m, cnt in primary_muscles.most_common():
        print(f"    {m!r:40} {cnt:>5}")

    print(f"\n  Muscle category values:")
    for c, cnt in muscle_categories.most_common():
        print(f"    {c!r:30} {cnt:>5}")

    # Check casing consistency
    muscle_casing = defaultdict(set)
    for ex in exercises:
        m = ex.get("muscles", {})
        if not isinstance(m, dict):
            continue
        for muscle in m.get("primary", []):
            muscle_casing[muscle.lower()].add(muscle)
        for muscle in m.get("secondary", []):
            muscle_casing[muscle.lower()].add(muscle)

    casing_issues = {k: v for k, v in muscle_casing.items() if len(v) > 1}
    print(f"\n  Muscle name casing inconsistencies: {len(casing_issues)}")
    for lower, variants in sorted(casing_issues.items()):
        print(f"    {lower}: {sorted(variants)}")

    # 8. Movement pattern analysis
    print(f"\n## 8. MOVEMENT PATTERN ANALYSIS")
    valid_move_types = {"push", "pull", "hinge", "squat", "carry", "rotation",
                        "flexion", "extension", "abduction", "adduction", "other"}
    valid_splits = {"upper", "lower", "full_body", "core"}

    move_type_counts = Counter()
    move_split_counts = Counter()
    for ex in exercises:
        mv = ex.get("movement")
        if isinstance(mv, dict):
            mt = mv.get("type", "<missing>")
            ms = mv.get("split", "<missing>")
            # Handle cases where type or split is a list instead of string
            if isinstance(mt, list):
                mt = str(mt)
            if isinstance(ms, list):
                ms = str(ms)
            move_type_counts[mt] += 1
            move_split_counts[ms] += 1

    print(f"\n  movement.type distribution:")
    for mt, cnt in move_type_counts.most_common():
        flag = "" if mt in valid_move_types else " *** UNEXPECTED ***"
        print(f"    {mt!r:20} {cnt:>5}{flag}")

    print(f"\n  movement.split distribution:")
    for ms, cnt in move_split_counts.most_common():
        flag = "" if ms in valid_splits else " *** UNEXPECTED ***"
        print(f"    {ms!r:20} {cnt:>5}{flag}")

    # 9. Metadata analysis
    print(f"\n## 9. METADATA ANALYSIS")
    valid_levels = {"beginner", "intermediate", "advanced"}
    valid_pom = {"sagittal", "frontal", "transverse", "multi-plane"}

    level_counts = Counter()
    pom_counts = Counter()
    uni_counts = Counter()
    for ex in exercises:
        md = ex.get("metadata")
        if isinstance(md, dict):
            lv = md.get("level", "<missing>")
            pom = md.get("plane_of_motion", "<missing>")
            uni = md.get("unilateral", "<missing>")
            # Handle list values
            if isinstance(lv, list):
                lv = str(lv)
            if isinstance(pom, list):
                pom = str(pom)
            level_counts[lv] += 1
            pom_counts[pom] += 1
            uni_counts[str(uni)] += 1

    print(f"\n  metadata.level distribution:")
    for lv, cnt in level_counts.most_common():
        flag = "" if lv in valid_levels else " *** UNEXPECTED ***"
        print(f"    {lv!r:20} {cnt:>5}{flag}")

    print(f"\n  metadata.plane_of_motion distribution:")
    for p, cnt in pom_counts.most_common():
        flag = "" if p in valid_pom else " *** UNEXPECTED ***"
        print(f"    {p!r:20} {cnt:>5}{flag}")

    print(f"\n  metadata.unilateral distribution:")
    for u, cnt in uni_counts.most_common():
        print(f"    {u!r:20} {cnt:>5}")

    # 10. Description/instructions quality sampling
    print(f"\n## 10. DESCRIPTION & INSTRUCTIONS QUALITY")

    # Description stats
    has_desc = sum(1 for ex in exercises if is_populated(ex.get("description")))
    desc_lengths = [len(ex.get("description", "")) for ex in exercises if is_populated(ex.get("description"))]
    print(f"\n  Descriptions: {has_desc}/{total} ({has_desc/total*100:.1f}%)")
    if desc_lengths:
        print(f"    Length: min={min(desc_lengths)}, max={max(desc_lengths)}, "
              f"avg={sum(desc_lengths)/len(desc_lengths):.0f}")

    # Check for placeholder/low quality descriptions
    placeholder_patterns = [
        "todo", "placeholder", "tbd", "fill in", "lorem", "test",
        "description here", "add description",
    ]
    placeholder_descs = []
    for ex in exercises:
        desc = ex.get("description", "")
        if desc and any(p in desc.lower() for p in placeholder_patterns):
            placeholder_descs.append((ex.get("name", "?"), desc[:100]))
    print(f"    Potentially placeholder descriptions: {len(placeholder_descs)}")
    for name, desc in placeholder_descs[:10]:
        print(f"      - {name}: \"{desc}...\"")

    # Very short descriptions
    short_descs = [(ex.get("name", "?"), ex.get("description", ""))
                   for ex in exercises
                   if is_populated(ex.get("description")) and len(ex.get("description", "")) < 30]
    print(f"    Very short descriptions (<30 chars): {len(short_descs)}")
    for name, desc in short_descs[:10]:
        print(f"      - {name}: \"{desc}\"")

    # Instructions stats
    has_instr = sum(1 for ex in exercises if is_populated(ex.get("instructions")))
    print(f"\n  Instructions (legacy field): {has_instr}/{total} ({has_instr/total*100:.1f}%)")

    # Execution notes stats
    has_exec = sum(1 for ex in exercises if is_populated(ex.get("execution_notes")))
    exec_note_counts = [len(ex.get("execution_notes", [])) for ex in exercises
                        if is_populated(ex.get("execution_notes"))]
    print(f"  Execution notes: {has_exec}/{total} ({has_exec/total*100:.1f}%)")
    if exec_note_counts:
        print(f"    Count per exercise: min={min(exec_note_counts)}, max={max(exec_note_counts)}, "
              f"avg={sum(exec_note_counts)/len(exec_note_counts):.1f}")

    # 11. Near-duplicate detection (basic)
    print(f"\n## 11. NEAR-DUPLICATE DETECTION")
    names_for_dedup = [(ex.get("name", ""), ex.get("_doc_id", ""), ex.get("family_slug", ""))
                       for ex in exercises if ex.get("name")]

    # Group by family_slug and check within families for near-dupes
    family_groups = defaultdict(list)
    for name, doc_id, family in names_for_dedup:
        family_groups[family].append((name, doc_id))

    near_dupes = []
    for family, members in family_groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                name_a, id_a = members[i]
                name_b, id_b = members[j]
                # Normalize for comparison
                norm_a = name_a.lower().replace("(", "").replace(")", "").strip()
                norm_b = name_b.lower().replace("(", "").replace(")", "").strip()
                ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
                if ratio > 0.85 and name_a.lower() != name_b.lower():
                    near_dupes.append((ratio, name_a, id_a, name_b, id_b, family))

    near_dupes.sort(key=lambda x: -x[0])
    print(f"  Near-duplicates found (similarity > 0.85): {len(near_dupes)}")
    for ratio, na, ida, nb, idb, fam in near_dupes[:30]:
        print(f"    [{ratio:.2f}] \"{na}\" ({ida}) <-> \"{nb}\" ({idb}) [family: {fam}]")

    # 12. Contribution map analysis
    print(f"\n## 12. MUSCLE CONTRIBUTION MAP ANALYSIS")
    bad_contribution_sums = []
    for ex in exercises:
        m = ex.get("muscles", {})
        if not isinstance(m, dict):
            continue
        contrib = m.get("contribution", {})
        if isinstance(contrib, dict) and len(contrib) > 0:
            total_contrib = sum(contrib.values())
            if abs(total_contrib - 1.0) > 0.05:
                bad_contribution_sums.append((
                    ex.get("name", "?"),
                    ex.get("_doc_id", "?"),
                    total_contrib,
                    contrib
                ))

    print(f"  Exercises with contribution sum deviating > 5% from 1.0: {len(bad_contribution_sums)}")
    for name, doc_id, total_c, contrib in bad_contribution_sums[:15]:
        print(f"    - {name} (sum={total_c:.3f}): {contrib}")

    # 13. Naming convention check
    print(f"\n## 13. NAMING CONVENTION CHECK")
    # Expected: "Exercise Name (Equipment)" or just "Exercise Name"
    no_equipment_in_name = []
    has_equipment_in_name = 0
    for ex in exercises:
        name = ex.get("name", "")
        eq = ex.get("equipment", [])
        if "(" in name and ")" in name:
            has_equipment_in_name += 1
        else:
            if isinstance(eq, list) and len(eq) > 0:
                no_equipment_in_name.append((name, eq, ex.get("_doc_id", "?")))

    print(f"  Exercises with equipment qualifier in name: {has_equipment_in_name}/{total}")
    print(f"  Exercises with equipment but NO qualifier in name: {len(no_equipment_in_name)}")
    if no_equipment_in_name:
        for name, eq, did in no_equipment_in_name[:20]:
            print(f"    - \"{name}\" equipment={eq} (doc_id={did})")

    # 14. doc_id format check
    print(f"\n## 14. DOC_ID FORMAT CHECK")
    # Expected: family_slug__name-slug
    bad_doc_ids = []
    for ex in exercises:
        doc_id = ex.get("_doc_id", "")
        family = ex.get("family_slug", "")
        name_slug = ex.get("name_slug", "")
        if doc_id and family and name_slug:
            expected = f"{family}__{name_slug}"
            if doc_id != expected:
                bad_doc_ids.append((doc_id, expected, ex.get("name", "?")))

    print(f"  Doc IDs not matching family__name-slug pattern: {len(bad_doc_ids)}/{total}")
    if bad_doc_ids:
        for actual, expected, name in bad_doc_ids[:15]:
            print(f"    - actual: {actual!r}")
            print(f"      expected: {expected!r}  (name: {name})")

    # 15. Summary scorecard
    print(f"\n{'=' * 80}")
    print(f"## SUMMARY SCORECARD")
    print(f"{'=' * 80}")

    core_fields_populated = {
        "name": populated_counts.get("name", 0),
        "family_slug": populated_counts.get("family_slug", 0),
        "equipment": populated_counts.get("equipment", 0),
        "category": populated_counts.get("category", 0),
        "muscles.primary": has_primary,
        "muscles.contribution": has_contribution,
        "description": has_desc,
        "execution_notes": has_exec,
        "movement.type": sum(1 for ex in exercises
                             if isinstance(ex.get("movement"), dict) and
                             is_populated(ex["movement"].get("type"))),
    }

    print(f"\n  Core field coverage:")
    for field, cnt in core_fields_populated.items():
        pct = cnt / total * 100
        status = "OK" if pct > 90 else "WARN" if pct > 70 else "BAD"
        print(f"    [{status:>4}] {field:<30} {cnt:>5}/{total} ({pct:.1f}%)")

    print(f"\n  Data quality summary:")
    print(f"    Total exercises:           {total}")
    print(f"    Unique families:           {len(family_slugs)}")
    print(f"    Exact duplicate names:     {sum(cnt - 1 for cnt in dupes.values()) if dupes else 0} extra")
    print(f"    Near-duplicates:           {len(near_dupes)}")
    print(f"    Invalid categories:        {len(invalid_cat_exercises)}")
    print(f"    Bad contribution sums:     {len(bad_contribution_sums)}")
    print(f"    Missing equip qualifier:   {len(no_equipment_in_name)}")
    print(f"    Doc ID format mismatches:  {len(bad_doc_ids)}")
    print(f"    Muscle casing issues:      {len(casing_issues)}")
    print(f"    Reviewed exercises:        {has_review}/{total} ({has_review/total*100:.1f}%)")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else (
        "/Users/valterandersson/Documents/Povver/adk_agent/catalog_orchestrator/"
        "exercises_dump_20260209.json"
    )
    analyze_catalog(path)
