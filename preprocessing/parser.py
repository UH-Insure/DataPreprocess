#!/usr/bin/env python3
"""
Parse all .cry (Cryptol) and .saw (SAW) files under one or more directories (recursively)
and export to JSONL.

Each line in the JSONL has:
  - filename: absolute file path (or stripped path if --strip is provided)
  - relpath: path relative to the provided root directory
  - filetype: 'cry' or 'saw'
  - content: file contents as UTF-8 (with replacement for invalid bytes)
  - root: the root directory that yielded this file

Usage:
  python code_parser.py /path/to/repo [/another/root ...] --out data/sources.jsonl --strip /path/to

If --out is omitted, defaults to ./data/cryptol_sources.jsonl
"""
from __future__ import annotations
import sys
import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, Optional
from database.utility import database
from database.entity import CryptolFile
from sqlalchemy.orm import Session
from sqlalchemy import select

# --- Helpers -----------------------------------------------------------------

def iter_source_files(root: Path, exts: Iterable[str]=(".cry", ".saw")) -> Iterator[Path]:
    """
    Yield Path objects for files under `root` matching any extension in `exts` (case-insensitive).
    """
    exts_lower = {e.lower() for e in exts}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts_lower:
            yield p

def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def read_text_safe(p: Path) -> str:
    # Read as UTF-8, replacing undecodable bytes so we never crash
    return p.read_text(encoding="utf-8", errors="replace")

def strip_prefix(full: Path, prefix: Optional[Path]) -> str:
    """
    If `prefix` is provided and is a real prefix of `full`, return the relative string path.
    Otherwise return the absolute path. Always uses POSIX separators for consistency.
    """
    full = full.resolve()
    if prefix is None:
        return full.as_posix()
    try:
        rel = full.relative_to(prefix.resolve())
        return rel.as_posix()
    except ValueError:
        # Not a prefix; fall back to absolute
        return full.as_posix()

def jsonl_to_dataframe(absolute_path: str):
    """
    Load a JSONL file into a pandas DataFrame. (Optional utility.)
    Expects per-line dicts with at least: filename, relpath, filetype, content, root.
    """
    import pandas as pd
    records = []
    with open(absolute_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return pd.DataFrame.from_records(records)

# --- Main --------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect Cryptol (.cry) and SAW (.saw) files into a JSONL dataset."
    )
    parser.add_argument(
        "roots",
        nargs="+",
        help="One or more root directories to search."
    )
    '''
    parser.add_argument(
        "--out", "-o",
        default="data/cryptol_sources.jsonl",
        help="Output JSONL path (default: data/cryptol_sources.jsonl)."
    )
    '''
    parser.add_argument(
        "--strip",
        metavar="PATH",
        type=str,
        default=None,
        help="If provided, strip this leading path prefix from 'filename' (nice for repo-relative paths)."
    )
    args = parser.parse_args(argv)

    roots = [Path(r).expanduser().resolve() for r in args.roots]
    #out_path = Path(args.out).expanduser().resolve()
    strip_path = Path(args.strip).expanduser().resolve() if args.strip else None

    #ensure_parent(out_path)

    total = 0
    errors = []
    db = database()
    with Session(db.engine) as session:
        for root in roots:
            root = root.resolve()
            for p in iter_source_files(root, exts=(".cry",)):
                try:
                    content = read_text_safe(p)
                except Exception as e:
                    print(f"[WARN] Could not read {p}: {e}", file=sys.stderr)
                    continue

                # Use suffix directly instead of regex; safer and faster.
                suff = p.suffix.lower()
                if suff not in (".cry"):
                    # Extremely defensive; should not happen due to filter above
                    continue

                filename = strip_prefix(p, strip_path)

                
                try:
                    stmt = select(CryptolFile).where(CryptolFile.filename == filename)
                    result = session.execute(stmt).first()
                    if result is not None:
                        continue
                    file = CryptolFile(
                        filename=filename,      # absolute or stripped path
                        #"relpath": relpath,        # relative to the producing root
                        #"filetype": filetype,      # 'cry' or 'saw'
                        #"root": root.as_posix(),   # emitting root
                        content=content,        # UTF-8 text with replacement
                    )
                    #out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    session.add(file)
                    session.commit()
                    total += 1
                except:
                    errors.append(filename)
                    session.flush()
    print(f"Wrote {total} files (.cry) to database")

if __name__ == "__main__":
    main()
