# comment_extractor.py
from __future__ import annotations
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple
from preprocessing.comment_policy_agent import decide_keep_drop_batch

# Line comment; Block comment; Doc string;
LINE_RE_CRY  = re.compile(r"//[^\n]*")          
BLOCK_RE_CRY = re.compile(r"/\*(?!\*)(.*?)\*/", re.S)
DOC_RE_CRY   = re.compile(r"/\*\*.*?\*/", re.S)

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def _read_decision_cache(path: Path) -> Dict[str, bool]:
    decisions: Dict[str, bool] = {}
    if not path.exists():
        return decisions
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            h = obj.get("sha1")
            k = obj.get("keep")
            if isinstance(h, str) and isinstance(k, bool):
                decisions[h] = k
    return decisions


def _append_decision(path: Path, sha1: str, keep: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"sha1": sha1, "keep": keep}, ensure_ascii=False) + "\n")

def _collect_spans(content: str) -> List[Tuple[int, int, str]]:
    """Collect non-overlapping comment spans using only LINE_RE and BLOCK_RE,
    and coalesce *adjacent* line comments (consecutive lines starting with //)
    into a single span.
    Returns: list of (start, end, kind) where kind in {'line','block'}.
    """
    spans: List[Tuple[int, int, str]] = []

    # Find block comments
    for m in BLOCK_RE_CRY.finditer(content):
        spans.append((m.start(), m.end(), "block"))

    # Find line comments
    for m in LINE_RE_CRY.finditer(content):
        spans.append((m.start(), m.end(), "line"))

    # Sort and drop overlaps (keep earlier)
    spans.sort(key=lambda t: t[0])
    non_overlap: List[Tuple[int, int, str]] = []
    last_end = -1
    for s, e, k in spans:
        if s >= last_end:
            non_overlap.append((s, e, k))
            last_end = e

    # Coalesce adjacent line-comment runs:
    # Two line comments are "adjacent" if between them there is exactly
    # a single newline (CRLF or LF) and optional indentation spaces/tabs.
    coalesced: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(non_overlap):
        s, e, k = non_overlap[i]
        if k != "line":
            coalesced.append((s, e, k))
            i += 1
            continue

        # try to extend this run forward
        j = i
        end_j = e
        while j + 1 < len(non_overlap) and non_overlap[j + 1][2] == "line":
            s_next, e_next, _ = non_overlap[j + 1]
            between = content[end_j:s_next]
            # exactly one line break (+ optional indent), not blank lines
            if re.fullmatch(r"\r?\n[ \t]*", between):
                end_j = e_next
                j += 1
            else:
                break

        coalesced.append((s, end_j, "line"))
        i = j + 1

    return coalesced


def _extend_end_consume_eol_if_standalone(content: str, s: int, e: int) -> int:
    """If a removed comment occupies its own line, also consume the trailing newline
    so we don't leave a blank line behind. For inline comments, keep the newline.
    """
    bol = content.rfind("\n", 0, s) + 1
    eol_idx = content.find("\n", e)
    if eol_idx == -1:
        eol_idx = len(content)
    left = content[bol:s]
    right = content[e:eol_idx]
    if left.strip() == "" and right.strip() == "":
        # consume the newline too (if exists)
        if eol_idx < len(content) and content[eol_idx] == "\n":
            return eol_idx + 1
        return eol_idx
    return e


def _next_span_start(spans: List[Tuple[int, int, str]], cur_index: int) -> int | None:
    """Given the spans list and the current span index, return the start of the next span (or None)."""
    nxt = cur_index + 1
    if 0 <= nxt < len(spans):
        return spans[nxt][0]
    return None

def _make_code_context(
    content: str,
    after_end: int,
    next_start: int | None,
    *,
    max_chars: int = 4000,
) -> str:
    """Return code snippet following the comment:
    - From `after_end` up to the next comment start (exclusive), capped at `max_chars`.
    - Strips leading blank lines/newlines for better signal.
    """
    stop = next_start if next_start is not None else len(content)
    snippet = content[after_end:stop][:max_chars]
    snippet = DOC_RE_CRY.sub("", snippet)
    # Normalize leading whitespace: drop leading blank lines
    snippet = re.sub(r"^\s*\n", "", snippet, count=1)
    return snippet


def extract_strip_cry_comments(
    filename: str,
    content: str,
    decision_cache_path: str | Path = "decision_cache.jsonl",
    *,
    llm_buffer_size: int = 8,
    context_max_chars: int = 600,
    llm_model_name: str | None = None,   # passed through if your agent supports it
) -> tuple[list[dict], dict]:
    """Extract comments and return (comments_list, file_record).

    Parameters
    ----------
    llm_buffer_size : int
        Max uncached comments to batch per LLM call.
    context_max_chars : int
        Max chars of code context to include after each comment.
    llm_model_name : str  

    Returns
    -------
    comments_list : List[Dict]
        [{filename: str, sha1: str, comment: str, keep: bool}, ...]
    file_record : Dict
        {filename: str, content: str} where content removes comments with keep=False.
    """
    cache_path = Path(decision_cache_path)
    decisions = _read_decision_cache(cache_path)

    spans = _collect_spans(content)

    comments: list[dict] = []
    out_parts: list[str] = []
    idx = 0

    # Buffer entries: {"s","e","sha1","comment","ctx"}
    pending: list[dict] = []

    def _apply_decision_and_emit(rec: dict) -> None:
        nonlocal idx, comments, out_parts
        s, e, sha, ctext = rec["s"], rec["e"], rec["sha1"], rec["comment"]

        # emit code preceding this comment
        if idx < s:
            out_parts.append(content[idx:s])

        keep_flag = bool(decisions[sha])
        comments.append(
            {
                "filename": filename,
                "sha1": sha,
                "comment": ctext,
                "keep": keep_flag,
                "snippet": ctx,
            }
        )

        if keep_flag:
            out_parts.append(ctext)
            idx = e
        else:
            e_ext = _extend_end_consume_eol_if_standalone(content, s, e)
            idx = e_ext
            # Also consume any *immediately* following blank lines
            while idx < len(content) and content[idx] == "\n":
                idx += 1

    def _flush_pending() -> None:
        nonlocal pending, decisions

        if not pending:
            return

        # Build agent items only for uncached
        to_query: list[dict] = []
        map_idx: list[int] = []
        for i, rec in enumerate(pending):
            if rec["sha1"] not in decisions:
                to_query.append(
                    {
                        "comment_text": rec["comment"],
                        "file_path": filename,
                        "code_context": rec["ctx"],
                    }
                )
                map_idx.append(i)

        if to_query:
            # Call your agent (supports batch)
            keeps = list(decide_keep_drop_batch(to_query, model_name=llm_model_name))

            # Persist decisions for queried items
            for j, keep in zip(map_idx, keeps):
                sha = pending[j]["sha1"]
                decisions[sha] = bool(keep)
                _append_decision(cache_path, sha, bool(keep))

        # Apply decisions in order (defaults for any missing)
        for rec in pending:
            decisions.setdefault(rec["sha1"], len(rec["comment"]) < 500)
            _apply_decision_and_emit(rec)

        pending.clear()

    # Iterate comments
    for i, (s, e, kind) in enumerate(spans):
        if s < idx:
            continue

        ctext = content[s:e]
        sha = _sha1(ctext)

        # Build code context from end of this comment to next span (or EOF)
        next_s = _next_span_start(spans, i)
        ctx = _make_code_context(content, e, next_s, max_chars=context_max_chars)

        # If cached, flush pending then apply immediately
        if sha in decisions:
            _flush_pending()
            _apply_decision_and_emit({"s": s, "e": e, "sha1": sha, "comment": ctext, "ctx": ctx})
            continue

        # Otherwise buffer for batched LLM decision
        pending.append({"s": s, "e": e, "sha1": sha, "comment": ctext, "ctx": ctx})

        if len(pending) >= llm_buffer_size:
            _flush_pending()

    # Flush any remaining buffered items
    _flush_pending()

    # Tail of code after last comment
    if idx < len(content):
        out_parts.append(content[idx:])

    new_content = "".join(out_parts)

    # Remove leading blank lines
    new_content = re.sub(r"^\n+", "", new_content)

    file_record = {"filename": filename, "content": new_content}
    return comments, file_record



__all__ = ['extract_strip_cry_comments']

if __name__ == "__main__":
    content = """
// line comment
// with multiple lines
let x = 1;
/** public API docs */
let y = x + 1;
/* block comment */
let z = y + 2;
// http://example.com should not trigger
"""
    comments, file_record = extract_strip_cry_comments(
        filename="example.cry",
        content=content,
        decision_cache_path="decision_cache.jsonl", 
        llm_model_name="gpt-oss:20b",
    )
    print(comments, "\n", file_record)