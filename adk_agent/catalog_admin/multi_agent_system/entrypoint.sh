#!/bin/sh
set -e

echo "[ENTRYPOINT] Starting container at $(date)"
echo "[ENTRYPOINT] Python version: $(python --version)"
echo "[ENTRYPOINT] Working directory: $(pwd)"
echo "[ENTRYPOINT] Directory contents:"
ls -la
echo "[ENTRYPOINT] Environment variables:"
env | grep -E "(FIREBASE|GOOGLE|LOG_DIR|TRACE)" | sort
echo "[ENTRYPOINT] Python path:"
python -c "import sys; print('\n'.join(sys.path))"
echo "[ENTRYPOINT] Testing imports..."
python -c "
import sys
sys.path.insert(0, '/app')
try:
    from utils.firebase_client import FirebaseFunctionsClient
    print('[ENTRYPOINT] ✓ firebase_client imports')
except Exception as e:
    print(f'[ENTRYPOINT] ✗ firebase_client import failed: {e}')
    import traceback
    traceback.print_exc()
    
try:
    from orchestrator.orchestrator import CatalogOrchestrator
    print('[ENTRYPOINT] ✓ orchestrator imports')
except Exception as e:
    print(f'[ENTRYPOINT] ✗ orchestrator import failed: {e}')
    import traceback
    traceback.print_exc()
"

echo "[ENTRYPOINT] Starting pipeline..."
exec python scripts/run_pipeline.py "$@"
