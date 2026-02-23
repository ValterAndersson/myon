"""
Training Analyst Service
========================

Automated training analysis system for Povver.

Components:
- Job queue (Firestore-backed, user-scoped jobs)
- Two analyzers: post-workout, weekly review
- Cloud Run workers for bounded execution
- Watchdog for job recovery
"""
