"""Firestore client singleton."""

from typing import Optional
from google.cloud import firestore

_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db
