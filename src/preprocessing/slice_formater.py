#!/usr/bin/env python3
"""
cryptol_seq_formatter.py

Reflow Cryptol sequence literals (e.g. sbox tables) so that as many elements
as possible are placed on each line, without exceeding a given line width
(default 80 characters).

CLI usage:

    python cryptol_seq_formatter.py aes.cry > aes_formatted.cry

    # or, to edit in-place:
    python cryptol_seq_formatter.py --in-place aes.cry

Notebook usage:

    from cryptol_seq_formatter import format_cryptol_tree
    changed_files = format_cryptol_tree("/path/to/root", width=80)
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List


def is_comprehension(inner: str) -> bool:
    """
    Heuristically detect list comprehensions like:
        [ gf28Pow 2 (k - 1) | k <- [1 ...] ]

    We look for a '|' at top level inside the brackets (not nested).
    If found, we treat this as a comprehension and do NOT reformat it.
    """
    depth_paren = depth_bracket = depth_brace = 0
    for c in inner:
        if c == '(':
            depth_paren += 1
        elif c == ')':
            depth_paren -= 1
        elif c == '[':
            depth_bracket += 1
        elif c == ']':
            depth_bracket -= 1
        elif c == '{':
            depth_brace += 1
        elif c == '}':
            depth_brace -= 1
        elif c == '|' and depth_paren == depth_bracket == depth_brace == 0:
            return True
    return False


def split_elements(inner: str) -> List[str]:
    """
    Split the inside of a list literal (string between '[' and ']')
    into top-level elements separated by commas, ignoring commas
    that occur inside (), [], or {}.
    """
    elems: List[str] = []
    buf: List[str] = []
    depth_paren = depth_bracket = depth_brace = 0

    i = 0
    while i < len(inner):
        c = inner[i]

        if c == ',' and depth_paren == depth_bracket == depth_brace == 0:
            elem = ''.join(buf).strip()
            if elem:
                elems.append(elem)
            buf = []
            i += 1
            continue

        buf.append(c)

        if c == '(':
            depth_paren += 1
        elif c == ')':
            depth_paren -= 1
        elif c == '[':
            depth_bracket += 1
        elif c == ']':
            depth_bracket -= 1
        elif c == '{':
            depth_brace += 1
        elif c == '}':
            depth_brace -= 1

        i += 1

    last = ''.join(buf).strip()
    if last:
        elems.append(last)
    return elems


def format_list_literal(indent: str, code_prefix: str,
                        elements: List[str], width: int) -> str:
    """
    Format a single list literal with the given indentation and code prefix.

    `indent`      = leading whitespace of the line
    `code_prefix` = text before the '[' on that line (e.g. "sbox = ")
    """
    first_prefix = indent + code_prefix + '['
    # Continuation lines: indent to align under first element after "[ "
    cont_prefix = indent + ' ' * (len(code_prefix) + 1)

    if not elements:
        # Empty list
        return first_prefix + ']'

    lines: List[str] = []
    current = first_prefix
    tokens_on_line = 0

    for idx, elem in enumerate(elements):
        is_last = idx == len(elements) - 1
        token = elem + (',' if not is_last else '')

        # Always add a single space before each token on a line
        candidate = current + ' ' + token

        if len(candidate) <= width or tokens_on_line == 0:
            current = candidate
            tokens_on_line += 1
        else:
            # Wrap to next line
            lines.append(current)
            current = cont_prefix + ' ' + token
            tokens_on_line = 1

    # Attach closing bracket
    closing = current + ']'
    if len(closing) <= width:
        lines.append(closing)
    else:
        lines.append(current)
        lines.append(indent + code_prefix + ']')

    return '\n'.join(lines)


def reformat_cryptol_sequences(source: str, width: int = 80) -> str:
    """
    Reformat all "literal" sequence expressions in a Cryptol source string.

    It scans for [...] regions, skips those that look like comprehensions,
    and reflows those that contain commas into neatly wrapped lines.
    """
    out = ''
    line_start = 0  # index in `out` of the current line start
    i = 0
    n = len(source)

    while i < n:
        c = source[i]

        if c != '[':
            out += c
            if c == '\n':
                line_start = len(out)
            i += 1
            continue

        # Found a '[', find its matching ']'
        depth = 0
        j = i
        while j < n:
            cj = source[j]
            if cj == '[':
                depth += 1
            elif cj == ']':
                depth -= 1
                if depth == 0:
                    break
            j += 1

        if depth != 0:
            # Unmatched '[', just treat it literally
            out += c
            i += 1
            continue

        seq_text = source[i : j + 1]   # includes the brackets
        inner = seq_text[1:-1]

        # If there's no comma, or it looks like a comprehension, leave it alone.
        if ',' not in inner or is_comprehension(inner):
            out += seq_text
            i = j + 1
            continue

        # Determine text from the start of this line up to the '['
        line_prefix = out[line_start:]
        # Remove that prefix from `out`; we'll rebuild it with formatted list
        out = out[:line_start]

        # Split into indentation vs code
        m = re.match(r'(\s*)(.*)', line_prefix)
        indent = m.group(1)
        code_prefix = m.group(2)

        elements = split_elements(inner)
        formatted = format_list_literal(indent, code_prefix, elements, width)

        out += formatted

        # Update line_start to index after last newline in `out`
        last_nl = out.rfind('\n')
        if last_nl == -1:
            line_start = 0
        else:
            line_start = last_nl + 1

        i = j + 1

    return out


def process_file(path: Path, width: int = 80, in_place: bool = False) -> None:
    """
    CLI helper: read a single file, reformat, and either print or overwrite.
    """
    text = path.read_text(encoding="utf-8")
    new_text = reformat_cryptol_sequences(text, width=width)

    if in_place:
        path.write_text(new_text, encoding="utf-8")
    else:
        print(new_text, end='')


# ---------- NEW: notebook-friendly directory function ----------

def format_cryptol_tree(
    root_dir: str | Path,
    width: int = 80,
    glob_pattern: str = "*.cry",
) -> list[Path]:
    """
    Recursively reformat all Cryptol files under `root_dir`.

    Parameters
    ----------
    root_dir : str | Path
        Root directory to walk (will use Path(root_dir).rglob(glob_pattern)).
    width : int
        Maximum line width for sequence literals (default: 80).
    glob_pattern : str
        Glob for Cryptol files (default: "*.cry").

    Returns
    -------
    list[Path]
        List of files that were modified (content changed).
    """
    root = Path(root_dir)
    changed: list[Path] = []

    for path in root.rglob(glob_pattern):
        if not path.is_file():
            continue

        text = path.read_text(encoding="utf-8")
        new_text = reformat_cryptol_sequences(text, width=width)

        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed.append(path)

    return changed


# ---------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reflow Cryptol sequence literals to a given line width."
    )
    parser.add_argument("file", type=Path, help="Cryptol source file (.cry)")
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=80,
        help="Maximum line width (default: 80)",
    )
    parser.add_argument(
        "-i", "--in-place",
        action="store_true",
        help="Modify the file in place instead of printing to stdout",
    )

    args = parser.parse_args()
    process_file(args.file, width=args.width, in_place=args.in_place)


if __name__ == "__main__":
    main()
