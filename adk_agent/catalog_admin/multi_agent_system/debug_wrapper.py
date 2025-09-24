#!/usr/bin/env python3
"""Debug wrapper to diagnose startup issues"""
import os
import sys
import traceback
from datetime import datetime

print(f"[DEBUG] Starting at {datetime.now()}", flush=True)
print(f"[DEBUG] Python: {sys.version}", flush=True)
print(f"[DEBUG] Working dir: {os.getcwd()}", flush=True)
print(f"[DEBUG] Directory contents:", flush=True)
for item in os.listdir('.'):
    print(f"  - {item}", flush=True)

print(f"[DEBUG] Environment:", flush=True)
for key in sorted(os.environ.keys()):
    if any(x in key for x in ['FIREBASE', 'GOOGLE', 'LOG', 'TRACE', 'PYTHON']):
        print(f"  {key}={os.environ[key]}", flush=True)

print(f"[DEBUG] sys.path:", flush=True)
for p in sys.path:
    print(f"  - {p}", flush=True)

print(f"[DEBUG] Testing imports...", flush=True)
try:
    from utils.firebase_client import FirebaseFunctionsClient
    print(f"[DEBUG] ✓ firebase_client imports", flush=True)
except Exception as e:
    print(f"[DEBUG] ✗ firebase_client failed: {e}", flush=True)
    traceback.print_exc()

try:
    from orchestrator.orchestrator import CatalogOrchestrator
    print(f"[DEBUG] ✓ orchestrator imports", flush=True)
except Exception as e:
    print(f"[DEBUG] ✗ orchestrator failed: {e}", flush=True)
    traceback.print_exc()

print(f"[DEBUG] Starting pipeline script...", flush=True)
sys.exit(os.system(f"python scripts/run_pipeline.py {' '.join(sys.argv[1:])}"))
