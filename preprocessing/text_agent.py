import os
import random
from openai import OpenAI
import time
from openai import RateLimitError
import os
import hashlib
import json

import pandas as pd

CACHE_PATH = "GPT_text_processing_cache.jsonl"

PROMPT_TEMPLATE = """
You are a **preprocessing assistant** whose job is to convert a raw text section (which may include prose, Cryptol examples, comments, docstrings, etc.) into a **cleaned snippet** optimal for fine-tuning a code LLM.

**Requirements / rules (strict):**
1. Always output **only** the cleaned snippet (no explanations, no additional commentary).
2. Use **Markdown format**:
   - Section headings: use `## Section Name`
   - Code blocks: wrap Cryptol code in triple-backticks with language identifier, e.g.  
     ```cryptol  
     f x = x + y + z  
     ```
3. Convert raw section markers like `Declarations` into clean headings (e.g. `## Declarations`), removing trailing symbols like ``.
4. Normalize whitespace:
   - Collapse more than two consecutive blank lines into two.
   - Remove leading/trailing spaces on lines.
5. Fix obvious typos (e.g. “functoin” → “function”), formatting noise, or broken markup.
6. If a section is clearly truncated (mid-sentence, missing context), either:
   - Smooth it so it reads like a coherent fragment, or
   - If too fragmented, produce an empty string (i.e. skip it).
7. Preserve semantic structure: keep lists, constraints, comments, docstring formatting (e.g. `/** … */`) intact as much as possible.
8. Ensure the cleaned snippet is **self-contained** and ready for tokenization without external dependencies.

### Example

**Raw input:**
Declarations
f x = x + y + z


**Desired output:**
```markdown
## Declarations

```cryptol
f x = x + y + z

---

### Now process this raw text:

### RAW TEXT BEGIN  
{raw_text}  
### RAW TEXT END  
"""

def compute_hash(s: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return h

def load_cache_index(cache_path: str) -> dict:
    """
    Read the JSONL cache file and return a dict mapping hash → processed_text.
    If file doesn't exist, return empty dict.
    """
    cache = {}
    if not os.path.exists(cache_path):
        return cache
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Expect each line to have keys: "hash", "processed"
                h = obj.get("hash")
                proc = obj.get("processed")
                if h is not None and proc is not None:
                    cache[h] = proc
            except json.JSONDecodeError:
                # skip malformed line
                continue
    return cache

def append_to_cache(cache_path: str, hash_key: str, processed: str):
    """
    Append one entry to the JSONL cache (hash → processed text).
    """
    rec = {
        "hash": hash_key,
        "processed": processed
    }
    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def get_or_process_text(raw_text: str, model: str = "gpt-4.1-mini", key: str = None) -> str:
    """
    If raw_text is in cache, return cached processed. Otherwise, call
    preprocess_text_via_openai, cache the result, and return it.
    """
    h = compute_hash(raw_text)
    cache = load_cache_index(CACHE_PATH)
    if h in cache:
        return (h, cache[h])
    # Not in cache — call the OpenAI preprocessing
    processed = preprocess_text_via_openai(raw_text, model=model, key=key)
    # Optionally: ensure processed is non-empty or valid
    append_to_cache(CACHE_PATH, h, processed)
    return (h, processed)



def call_with_retry(func, *args, max_retries=5, base_delay=1.0, max_delay=60.0, **kwargs):
    """
    Call func(*args, **kwargs). If it raises RateLimitError, retry
    with exponential backoff and jitter, up to max_retries.
    """
    delay = base_delay
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except RateLimitError as e:
            # On final attempt, re-raise
            if attempt == max_retries - 1:
                raise
            # Sleep with jitter
            jitter = delay * (0.5 + 0.5 * random.random())
            time.sleep(jitter)
            # Exponentially increase delay (capped)
            delay = min(delay * 2, max_delay)
    # If we got here, all retries failed
    return func(*args, **kwargs)


def preprocess_text_via_openai(raw_text: str, model: str = "gpt-4.1-mini", key: str = None) -> str:
    """
    Send raw_text to the OpenAI API using the prompt template and return the cleaned snippet.
    """
    prompt = PROMPT_TEMPLATE.format(raw_text=raw_text)
    client = OpenAI(
    api_key=key if key is not None else os.getenv("OPENAI_API_KEY"),
)

    response = call_with_retry(client.chat.completions.create,
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ],

    )

    # Get output
    cleaned = response.choices[0].message.content
    return cleaned

if __name__ == "__main__":
    # Example usage
    raw = """
Basic Syntax

Declarations

f x = x + y + z
Type Signatures

f,g : {a,b} (fin a) => [a] b
Numeric Constraint Guards

A declaration with a signature can use numeric constraint guards, which are used to change the behavior of a functoin depending on its numeric type parameters. For example:

len : {n} (fin n) => [n]a -> Integer
len xs | n == 0 => 0
       | n >  0 => 1 + len (drop `{1} xs)
Each behavior starts with | and lists some constraints on the numeric parameters to a declaration. When applied, the function will use the first definition that satisfies the provided numeric parameters.

...
    """
    test_df = pd.read_json("/Users/josh/SecurityAnalytics/DataPreprocess/data/parsed_text_data.jsonl", lines=True)
    raw = test_df.loc[
    test_df["filename"] == "https_galoisinc.github.io_saw-script_master_saw-user-manual_specification-based-verification.html.txt",
            "content"
        ].iloc[0]
    print(raw)
    gpt4_text = preprocess_text_via_openai(raw, model="gpt-4.1-mini")
    print("=== GPT-4 Cleaned Snippet ===")
    print(gpt4_text)
    #gpt5_text = preprocess_text_via_openai(raw, model="gpt-5")
    print("=== GPT-5 Cleaned Snippet ===")
    #print(gpt5_text)