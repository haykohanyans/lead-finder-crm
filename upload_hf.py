#!/usr/bin/env python3
"""Upload files to HuggingFace Space from local repo."""
import os, sys

token = os.environ.get("HF_TOKEN", "")
if not token:
    print("ERROR: Set HF_TOKEN env var")
    sys.exit(1)

from huggingface_hub import HfApi

api = HfApi()
space_id = "hvoh/lead-finder-crm"
base = os.path.dirname(os.path.abspath(__file__))

files = [
    "app.py",
    "requirements.txt",
    "Dockerfile",
    "templates/index.html",
]

print(f"=== Uploading to HF Space: {space_id} ===\n")

for f in files:
    local = os.path.join(base, f)
    if not os.path.exists(local):
        print(f"⚠ SKIP {f}")
        continue
    try:
        api.upload_file(path_or_fileobj=local, path_in_repo=f,
                        repo_id=space_id, repo_type="space", token=token)
        print(f"✅ {f}")
    except Exception as e:
        print(f"❌ {f}: {e}")

print(f"\nDone! https://hvoh-lead-finder-crm.hf.space")
