#!/usr/bin/env python3
"""
Parse all .cry (Cryptol) files under a directory (recursively) and export to JSONL.

Each line in the JSONL has:
  - filename: absolute file path
  - relpath: path relative to the provided root directory
  - content: file contents as UTF-8 (with replacement for invalid bytes)

Usage:
  python code_parser.py /path/to/repo --out data/cryptol_sources.jsonl

If --out is omitted, defaults to ./data/cryptol_sources.jsonl
"""
from __future__ import annotations
import sys
import argparse
import json
from pathlib import Path

def iter_source_files(root: Path, exts=(".cry", ".saw")):
    """
    Yield Path objects for files under `root` matching any extension in `exts`.
    - exts: iterable of extension strings (including the leading dot), e.g. (".cry", ".saw")
    """
    # Use rglob for recursive search. Convert to lower() to be case-insensitive on extension.
    for ext in exts:
        # rglob is fine; we iterate per-extension to avoid complex glob patterns
        yield from root.rglob(f"*{ext}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def read_text_safe(p: Path) -> str:
    # Read as UTF-8, replacing undecodable bytes so we never crash
    return p.read_text(encoding="utf-8", errors="replace")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect Cryptol (.cry) files into a JSONL dataset.")
    parser.add_argument("roots", nargs="+", default=".", help="One or more root directories to search (default: current directory).")
    parser.add_argument("--out", "-o", default="data/cryptol_sources.jsonl", help="Output JSONL path (default: data/cryptol_sources.jsonl).")
    parser.add_argument("--absolute", action="store_true", help="Store absolute file paths in 'filename' (default).")
    parser.add_argument("--relative-only", action="store_true", help="Store only relative paths in 'filename'.")
    args = parser.parse_args(argv)

    roots = [Path(r).expanduser().resolve() for r in args.roots]
    out_path = Path(args.out)

    ensure_parent(out_path)

    total = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for root in roots:
            for p in iter_source_files(root, exts=(".cry", ".saw")):
                try:
                    content = read_text_safe(p)
                except Exception as e:
                    # Skip unreadable files but continue processing
                    print(f"[WARN] Could not read {p}: {e}", file=sys.stderr)
                    continue

                rel = p.relative_to(root) if p.is_absolute() else p
                record = {
                    "filename": (str(p) if not args.relative_only else str(rel)),
                    #"root" : str(root),
                    "relpath": str(rel),
                    "content": content,
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1

    print(f"Wrote {total} .cry files to {out_path}")

if __name__ == "__main__":
    main()
