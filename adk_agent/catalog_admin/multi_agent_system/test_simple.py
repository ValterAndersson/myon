#!/usr/bin/env python3
print("STARTING", flush=True)
import sys
print("HELLO FROM CONTAINER", flush=True)
print(f"Args: {sys.argv}", flush=True)
import os
print(f"ENV: {os.environ}", flush=True)
sys.exit(0)
