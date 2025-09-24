#!/usr/bin/env python3
import argparse
import os
from typing import Any

from google.cloud import firestore


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a canvas snapshot (state, up_next, recent cards)")
    parser.add_argument("--user-id", default=os.getenv("USER_ID", os.getenv("PIPELINE_USER_ID", "canvas_orchestrator_engine")))
    parser.add_argument("--canvas-id", default=os.getenv("CANVAS_ID", os.getenv("TEST_CANVAS_ID", "")))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    uid = args.user_id
    cid = args.canvas_id
    if not cid:
        # Try local file
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, os.pardir))
        candidate_files = [os.path.join(root, ".canvas_id"), os.path.join(os.getcwd(), ".canvas_id")]
        for p in candidate_files:
            if os.path.exists(p):
                try:
                    cid = open(p, "r").read().strip()
                    break
                except Exception:
                    pass
    if not cid:
        print("Missing --canvas-id / CANVAS_ID / TEST_CANVAS_ID and no .canvas_id file found.")
        return 1

    db = firestore.Client()
    base = db.collection("users").document(uid).collection("canvases").document(cid)

    # State
    state = base.collection("state").document("current").get()
    print("\nState:")
    if state.exists:
        print(state.to_dict())
    else:
        print("(no state doc)")

    # Up-next
    print("\nUp-Next (top 20):")
    try:
        up_next = base.collection("up_next").order_by("priority", direction=firestore.Query.DESCENDING).limit(20).stream()
        for doc in up_next:
            d = doc.to_dict()
            print({k: d.get(k) for k in ["card_id", "priority", "inserted_at"]})
    except Exception as e:
        print(f"(failed to list up_next: {e})")

    # Cards
    print(f"\nRecent cards (limit {args.limit}):")
    try:
        cards = base.collection("cards").order_by("created_at", direction=firestore.Query.DESCENDING).limit(args.limit).stream()
        for doc in cards:
            d = doc.to_dict()
            summary = {
                "id": doc.id,
                "type": d.get("type"),
                "status": d.get("status"),
                "lane": d.get("lane"),
            }
            print(summary)
    except Exception as e:
        # Fallback: list without ordering
        try:
            cards = base.collection("cards").limit(args.limit).stream()
            for doc in cards:
                d = doc.to_dict()
                print({"id": doc.id, "type": d.get("type"), "status": d.get("status")})
        except Exception as e2:
            print(f"(failed to list cards: {e2})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


