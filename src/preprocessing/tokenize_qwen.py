"""
tokenize_qwen.py
----------------
Utility functions to tokenize Cryptol and SAW source code using the Qwen2.5-Coder tokenizer.
Works seamlessly with pandas DataFrames loaded from JSONL files.

Example
-------
import pandas as pd
from tokenize_qwen import load_qwen_tokenizer, tokenize_df, chunk_token_ids

df = pd.read_json("data/cryptol_saw.jsonl", lines=True)
tokenizer = load_qwen_tokenizer("Qwen/Qwen2.5-Coder-7B")

tokenized_df = tokenize_df(df, tokenizer)
tokenized_df.to_json("data/tokenized.jsonl", orient="records", lines=True)
"""

from __future__ import annotations
import pandas as pd
from typing import List, Dict, Any, Iterator, Optional
from transformers import AutoTokenizer, PreTrainedTokenizerBase


# ---------------------------------------------------------------------------
#  Tokenizer loading
# ---------------------------------------------------------------------------

def load_qwen_tokenizer(model_name: str = "Qwen/Qwen2.5-Coder-7B",
                        padding_side: str = "right") -> PreTrainedTokenizerBase:
    """Load a Qwen2.5-Coder tokenizer with safe defaults."""
    tok = AutoTokenizer.from_pretrained(model_name, use_fast=True, trust_remote_code=True)
    tok.padding_side = padding_side
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


# ---------------------------------------------------------------------------
#  Text normalization and tokenization
# ---------------------------------------------------------------------------

def normalize_utf8(s: str) -> str:
    """Normalize UTF-8 text (replace NULs, ensure str)."""
    if isinstance(s, bytes):
        s = s.decode("utf-8", errors="replace")
    return s.replace("\x00", "�")


def tokenize_text(text: str,
                  tokenizer: PreTrainedTokenizerBase,
                  add_special_tokens: bool = False) -> Dict[str, Any]:
    """Tokenize a single UTF-8 text string."""
    text = normalize_utf8(text)
    encoded = tokenizer(text, add_special_tokens=add_special_tokens)
    ids = encoded["input_ids"]
    return {
        "input_ids": ids,
        "n_tokens": len(ids)
    }


def tokenize_df(df: pd.DataFrame,
                tokenizer: PreTrainedTokenizerBase,
                text_col: str = "content",
                add_special_tokens: bool = False) -> pd.DataFrame:
    """
    Apply tokenizer to every row in a pandas DataFrame.
    Adds columns: input_ids (list[int]) and n_tokens (int).
    """
    def _apply(text):
        return tokenize_text(text, tokenizer, add_special_tokens)

    tokenized = df[text_col].apply(_apply).apply(pd.Series)
    return pd.concat([df, tokenized], axis=1)


# ---------------------------------------------------------------------------
#  Chunking utilities
# ---------------------------------------------------------------------------

def chunk_token_ids(input_ids: List[int],
                    max_len: int = 4096,
                    stride: int = 256,
                    pad_id: Optional[int] = None,
                    pad_to_full: bool = False) -> Iterator[List[int]]:
    """
    Split token IDs into overlapping chunks for fine-tuning.
    pad_id: pad token id for right padding (if pad_to_full=True)
    """
    if max_len <= 0:
        raise ValueError("max_len must be > 0")
    if stride < 0 or stride >= max_len:
        raise ValueError("stride must be in [0, max_len-1]")

    n = len(input_ids)
    step = max_len - stride

    for start in range(0, n, step):
        end = min(start + max_len, n)
        ids = input_ids[start:end]
        if pad_to_full and pad_id is not None and len(ids) < max_len:
            ids = ids + [pad_id] * (max_len - len(ids))
        yield ids
        if end == n:
            break


def expand_chunked_df(df: pd.DataFrame,
                      tokenizer: PreTrainedTokenizerBase,
                      max_seq_len: int = 4096,
                      stride: int = 256) -> pd.DataFrame:
    """
    Expand a tokenized DataFrame into multiple rows, one per chunk.
    Columns: filename, chunk_index, input_ids, n_tokens
    """
    rows = []
    for _, row in df.iterrows():
        for i, ids in enumerate(
            chunk_token_ids(row["input_ids"],
                            max_len=max_seq_len,
                            stride=stride,
                            pad_id=tokenizer.pad_token_id,
                            pad_to_full=True)
        ):
            rows.append({
                "filename": row.get("filename", ""),
                "chunk_index": i,
                "input_ids": ids,
                "n_tokens": len([t for t in ids if t != tokenizer.pad_token_id])
            })
    return pd.DataFrame(rows)
