#!/usr/bin/env python3
"""
Reusable Library CLI Helper
Searches, lists, and downloads reusable modules directly from GitHub.

Usage:
  python3 fetch.py --list
  python3 fetch.py --search <keyword>
  python3 fetch.py --module <module_id> [--output-dir ./app]
"""

import argparse
import json
import os
import sys
import urllib.request

REPO_RAW_BASE = "https://raw.githubusercontent.com/sh15aa/botserusable/main"
REGISTRY_URL = f"{REPO_RAW_BASE}/registry/modules.json"

def fetch_registry():
    try:
        req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": "ReusableCodeClient/1.0"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # Fallback to local registry if running within the repo
        local_path = os.path.join(os.path.dirname(__file__), "..", "registry", "modules.json")
        if os.path.exists(local_path):
            with open(local_path, "r") as f:
                return json.load(f)
        print(f"Error fetching registry from {REGISTRY_URL}: {e}", file=sys.stderr)
        sys.exit(1)

def list_modules(registry, search_term=None):
    modules = registry.get("modules", [])
    if search_term:
        term = search_term.lower()
        modules = [m for m in modules if term in m["id"].lower() or term in m["name"].lower() or term in m["description"].lower() or term in m.get("category", "").lower()]
    
    print(f"\nFound {len(modules)} reusable module(s):")
    print("-" * 80)
    for m in modules:
        print(f"ID:          {m['id']}")
        print(f"Name:        {m['name']} [{m.get('category', 'general')}]")
        print(f"Path:        {m['path']}")
        print(f"Description: {m['description']}")
        print(f"Classes:     {', '.join(m.get('classes', []))}")
        print(f"Dependencies:{', '.join(m.get('dependencies', []))}")
        print("-" * 80)

def download_module(registry, module_id, output_dir):
    modules = registry.get("modules", [])
    match = next((m for m in modules if m["id"] == module_id), None)
    if not match:
        print(f"Error: Module '{module_id}' not found in registry.", file=sys.stderr)
        sys.exit(1)

    rel_path = match["path"]
    target_path = os.path.join(output_dir, rel_path)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    file_url = f"{REPO_RAW_BASE}/{rel_path}"
    print(f"Downloading {module_id} from {file_url} -> {target_path}...")
    try:
        req = urllib.request.Request(file_url, headers={"User-Agent": "ReusableCodeClient/1.0"})
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
        with open(target_path, "wb") as f:
            f.write(content)
        print(f"Successfully downloaded {module_id} to {target_path}")
        if match.get("dependencies"):
            print(f"Note: Requires dependencies: {', '.join(match['dependencies'])}")
        if match.get("env_vars"):
            print(f"Note: Requires environment variables: {', '.join(match['env_vars'])}")
    except Exception as e:
        print(f"Failed to download module file: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Reusable Library Module Fetcher")
    parser.add_argument("--list", action="store_true", help="List all available reusable modules")
    parser.add_argument("--search", type=str, help="Search modules by keyword")
    parser.add_argument("--module", type=str, help="Module ID to download (e.g. ai.guardrails)")
    parser.add_argument("--output-dir", type=str, default=".", help="Target root directory (defaults to current dir)")

    args = parser.parse_args()
    registry = fetch_registry()

    if args.list:
        list_modules(registry)
    elif args.search:
        list_modules(registry, search_term=args.search)
    elif args.module:
        download_module(registry, args.module, args.output_dir)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
