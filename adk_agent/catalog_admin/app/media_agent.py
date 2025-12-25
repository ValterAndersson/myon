from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Iterable, Optional

from .action_schema import Lane
from .libs.tools_firebase.client import FirebaseFunctionsClient


class MotionGifAgent:
    """Deterministically request motion GIF assets for exercises.

    This agent keeps the generation surface area small: a fixed style tag, a
    deterministic seed per exercise, and a stable prompt scaffold. It delegates
    the heavy lifting (Google image LLM call + storage) to Firebase Functions so
    the client only needs to attach the resulting asset metadata to the
    exercise document via the existing upsert path.
    """

    def __init__(
        self,
        client: FirebaseFunctionsClient,
        *,
        style_tag: str = "studio-motion",
        storage_prefix: str = "catalog/motion_gif",
        allowed_lanes: Iterable[Lane] = (Lane.batch,),
    ) -> None:
        self.client = client
        self.style_tag = style_tag
        self.storage_prefix = storage_prefix
        self.allowed_lanes = tuple(allowed_lanes)

    def is_lane_allowed(self, lane: Lane) -> bool:
        return lane in self.allowed_lanes

    @staticmethod
    def _seed_for_exercise(exercise: Dict[str, Any], style_tag: str) -> str:
        material = f"{exercise.get('id') or exercise.get('name')}::{style_tag}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _current_media(exercise: Dict[str, Any]) -> Dict[str, Any]:
        media = exercise.get("media") if isinstance(exercise, dict) else None
        return media or {}

    def _prompt(self, exercise: Dict[str, Any]) -> str:
        name = str(exercise.get("name") or "exercise").strip()
        cues = exercise.get("coaching_cues") or []
        cue_text = "; ".join(cues) if isinstance(cues, list) else str(cues)
        movement = exercise.get("movement") or {}
        movement_type = movement.get("type") if isinstance(movement, dict) else None
        return (
            "Cinematic 3D human performing the full range of motion for "
            f"{name}. Show start to finish in a smooth looping GIF. Style: {self.style_tag}. "
            "Consistent camera angle, neutral background, clear joint positions, no overlays. "
            f"Movement type: {movement_type or 'compound'}. Coaching cues: {cue_text}."
        )

    def generate_motion_gif(self, exercise: Dict[str, Any], *, lane: Lane) -> Optional[Dict[str, Any]]:
        if not self.is_lane_allowed(lane):
            return None
        media = self._current_media(exercise)
        existing = media.get("motion_gif") if isinstance(media, dict) else None
        if isinstance(existing, dict) and existing.get("url"):
            return None
        prompt = self._prompt(exercise)
        seed = self._seed_for_exercise(exercise, self.style_tag)
        resp = self.client.generate_motion_gif(
            exercise_id=str(exercise.get("id") or exercise.get("name")),
            prompt=prompt,
            style_tag=self.style_tag,
            seed=seed,
            storage_prefix=self.storage_prefix,
            lane=lane.value,
            idempotency_key=seed,
        )
        data = resp.get("data") if isinstance(resp, dict) else resp
        asset_url = (data or {}).get("asset_url") or (data or {}).get("url")
        if not asset_url:
            return None
        return {
            "url": asset_url,
            "thumbnail_url": (data or {}).get("thumbnail_url"),
            "prompt": prompt,
            "seed": seed,
            "style_tag": self.style_tag,
            "generator": "google_image_llm",
            "generated_at": (data or {}).get("generated_at") or int(time.time()),
        }
