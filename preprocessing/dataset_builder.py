#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

# ---------- Helpers ----------

CRYPTOL_EXTS = {".cry", ".saw"}

def read_text_utf8(p: Path) -> str:
    # Keep errors as-is but avoid crashes on odd bytes
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

def normalize_blanklines(s: str, strip_leading: bool = True) -> str:
    lines = s.split("\n")
    out = []
    blank_streak = 0
    for ln in lines:
        if ln.strip() == "":
            blank_streak += 1
            # collapse 2+ blanks into 1
            if blank_streak == 1:
                out.append("")
        else:
            blank_streak = 0
            out.append(ln)
    if strip_leading:
        while out and out[0].strip() == "":
            out.pop(0)
    return "\n".join(out)

def strip_cryptol_comments_all(s: str) -> str:
    """
    Remove both // line comments and /* ... */ block comments while
    preserving content inside '...' and "..." string/char literals.
    """
    i, n = 0, len(s)
    out = []
    in_slash = False
    in_block = False
    block_depth = 0
    in_line = False
    in_sq = False  # '
    in_dq = False  # "
    escape = False

    while i < n:
        ch = s[i]
        nxt = s[i+1] if i+1 < n else ""

        # inside single- or double-quoted literal
        if in_sq or in_dq:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            else:
                if in_sq and ch == "'":
                    in_sq = False
                if in_dq and ch == '"':
                    in_dq = False
            i += 1
            continue

        # inside line comment
        if in_line:
            if ch == "\n":
                in_line = False
                out.append("\n")
            i += 1
            continue

        # inside block comment (support nesting just in case)
        if in_block:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    in_block = False
                continue
            i += 1
            continue

        # not in string or comment
        if ch == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            block_depth = 1
            i += 2
            continue

        # Start of string/char?
        if ch == "'":
            in_sq = True
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

def strip_cryptol_line_comments_only(s: str) -> str:
    """Remove only // comments; keep block comments intact."""
    i, n = 0, len(s)
    out = []
    in_line = False
    in_sq = False
    in_dq = False
    escape = False

    while i < n:
        ch = s[i]
        nxt = s[i+1] if i+1 < n else ""

        # strings
        if in_sq or in_dq:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            else:
                if in_sq and ch == "'":
                    in_sq = False
                if in_dq and ch == '"':
                    in_dq = False
            i += 1
            continue

        # in // comment
        if in_line:
            if ch == "\n":
                in_line = False
                out.append("\n")
            i += 1
            continue

        # detect // but NOT /* */
        if ch == "/" and nxt == "/":
            in_line = True
            i += 2
            continue

        if ch == "'":
            in_sq = True
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

def iter_source_files(inputs):
    for path in inputs:
        p = Path(path)
        if p.is_file() and p.suffix.lower() in CRYPTOL_EXTS:
            yield p
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and sub.suffix.lower() in CRYPTOL_EXTS:
                    yield sub

def write_jsonl(rows, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------- Build Datasets ----------

def build_datasets(inputs, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_with = []
    rows_without = []
    rows_hybrid = []

    for fp in iter_source_files(inputs):
        raw = read_text_utf8(fp)
        # normalize newlines for all variants
        base = raw.replace("\r\n", "\n").replace("\r", "\n")

        # 1) with_comments (only newline normalization)
        rows_with.append({
            "filename": str(fp),
            "content": base,
            "variant": "with_comments"
        })

        # 2) without_comments (strip // and /*...*/)
        no_comments = strip_cryptol_comments_all(base)
        no_comments = normalize_blanklines(no_comments, strip_leading=True)
        if not no_comments.endswith("\n"):
            no_comments += "\n"
        rows_without.append({
            "filename": str(fp),
            "content": no_comments,
            "variant": "without_comments"
        })

        # 3) hybrid (strip only //, keep block comments, tidy whitespace)
        hybrid = strip_cryptol_line_comments_only(base)
        hybrid = normalize_blanklines(hybrid, strip_leading=True)
        if not hybrid.endswith("\n"):
            hybrid += "\n"
        rows_hybrid.append({
            "filename": str(fp),
            "content": hybrid,
            "variant": "hybrid"
        })

    write_jsonl(rows_with, out_dir / "dataset_with_comments.jsonl")
    write_jsonl(rows_without, out_dir / "dataset_without_comments.jsonl")
    write_jsonl(rows_hybrid, out_dir / "dataset_hybrid.jsonl")

    print("Wrote:",
          out_dir / "dataset_with_comments.jsonl",
          out_dir / "dataset_without_comments.jsonl",
          out_dir / "dataset_hybrid.jsonl", file=sys.stderr)

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Build Cryptol/SAW datasets with three comment-variants.")
    ap.add_argument("inputs", nargs="+", help="Files and/or directories to scan (.cry, .saw).")
    ap.add_argument("--out-dir", required=True, help="Directory to write JSONL datasets.")
    args = ap.parse_args()

    build_datasets(args.inputs, Path(args.out_dir))

if __name__ == "__main__":
    main()
