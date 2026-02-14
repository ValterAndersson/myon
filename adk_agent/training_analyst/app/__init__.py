"""
Training Analyst Service
========================

Automated training analysis system for Povver.

Components:
- Job queue (Firestore-backed, user-scoped jobs)
- Three analyzers: post-workout, daily brief, weekly review
- Cloud Run workers for bounded execution
- Watchdog for job recovery
"""
