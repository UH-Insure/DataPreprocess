#!/usr/bin/env python3
"""
interpreter_check.py

- Reassembles multi-chunk JSONL rows back into full source files
- Saves each file under a supplied root directory, preserving relative paths
  but appending a random GUID to the filename to avoid clobbering
- Runs the Cryptol interpreter from the file's directory so relative imports work
- Writes a JSON results file with stdout/stderr/returncode for each file

Usage:
  python interpreter_check.py \
    --jsonl cryptol_sources.jsonl \
    --root out_cry_files \
    --out interpreter_results.json \
    --cryptol /usr/local/bin/cryptol        # optional; defaults to "cryptol"
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from collections import defaultdict

def load_chunks(jsonl_path: Path):
    """
    Stream the JSONL file and collect chunks by original filename.
    Returns a dict: {filename: [{"chunk_idx": int, "chunks_total": int, "content": str, ...}, ...]}
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    with jsonl_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping line {i}: invalid JSON ({e})", file=sys.stderr)
                continue
            filename = obj.get("filename")
            content  = obj.get("content")
            if not filename or content is None:
                print(f"[WARN] Skipping line {i}: missing 'filename' or 'content'", file=sys.stderr)
                continue
            groups[filename].append(obj)
    return groups

def reassemble(groups: dict[str, list[dict]]) -> dict[str, str]:
    """
    For each filename, sort by chunk_idx (if present) and concatenate contents.
    """
    combined: dict[str, str] = {}
    for fname, rows in groups.items():
        # If chunk metadata is present, sort; otherwise keep input order.
        if all("chunk_idx" in r for r in rows):
            rows_sorted = sorted(rows, key=lambda r: (r.get("chunk_idx", 0), r.get("n") or r.get("i") or 0))
        else:
            rows_sorted = rows  # best effort
        parts = []
        for r in rows_sorted:
            c = r.get("content", "")
            parts.append(c)
        combined[fname] = "".join(parts)
    return combined

def write_with_guid(root: Path, rel_filename: str, content: str) -> Path:
    """
    Save content under `root/<parent_dirs>/<stem>_<GUID><suffix>`.
    Returns the absolute Path to the saved file.
    """
    rel = Path(rel_filename)
    parent = root / rel.parent
    parent.mkdir(parents=True, exist_ok=True)
    stem = rel.stem
    suffix = rel.suffix or ".cry"
    unique = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
    out_path = parent / unique
    out_path.write_text(content, encoding="utf-8")
    return out_path

def run_cryptol(cryptol_bin: str, file_path: Path, timeout: int = 120):
    """
    Run Cryptol in the directory of `file_path`, loading just that file to
    catch obvious parse/type/import issues. Returns dict with stdout/stderr/returncode.
    """
    cwd = file_path.parent
    # Use -c with multiple commands separated by newlines. We just load and quit.
    cmd_script = f":l {file_path.name}\n:q\n"
    try:
        proc = subprocess.run(
            [cryptol_bin, "-q", "-c", cmd_script],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except FileNotFoundError as e:
        return {"returncode": -127, "stdout": "", "stderr": f"cryptol not found: {e}"}
    except subprocess.TimeoutExpired as e:
        return {"returncode": -124, "stdout": e.stdout or "", "stderr": (e.stderr or "") + "\n[timeout]"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True, help="Path to JSONL with rows containing filename/content (possibly chunked)")
    ap.add_argument("--root", required=True, help="Root directory to write .cry files into (imports resolve relative to this)")
    ap.add_argument("--out", required=True, help="Where to write JSON results")
    ap.add_argument("--cryptol", default="cryptol", help="Path to the cryptol binary (default: 'cryptol' in PATH)")
    ap.add_argument("--timeout", type=int, default=120, help="Interpreter timeout per file (seconds)")
    args = ap.parse_args()

    jsonl_path = Path(args.jsonl)
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    # 1) Load & group chunks
    groups = load_chunks(jsonl_path)

    # 2) Reassemble each file from its chunks
    combined = reassemble(groups)

    # 3) Write each to disk under root, preserving subdirs, with GUID suffix
    results = {}
    for original_filename, content in combined.items():
        out_path = write_with_guid(root, original_filename, content)

        # 4) Run the interpreter from the file's directory so imports work
        res = run_cryptol(args.cryptol, out_path, timeout=args.timeout)

        results[str(out_path)] = {
            "original_filename": original_filename,
            **res,
        }
        # Keep files on disk (do NOT delete)

    # 5) Save results JSON
    out_json = Path(args.out)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Console summary
    total = len(results)
    ok = sum(1 for r in results.values() if r["returncode"] == 0)
    print(f"[done] processed: {total}, ok: {ok}, failed: {total - ok}")
    print(f"[info] results -> {out_json}")
    print(f"[info] files written under -> {root.resolve()}")

if __name__ == "__main__":
    main()
