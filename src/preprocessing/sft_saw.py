#!/usr/bin/env python3
# saw_SFT_preprocessor.py
from __future__ import annotations
from pathlib import Path
import re
import pandas as pd
from pydantic import BaseModel

ROOT_DIR = "~/SecurityAnalytics"

LLVM_RE = re.compile(r'llvm_load_module\s*"([^"\n]+\.bc)"')
JAVA_RE = re.compile(r'java_load_class\s*"([^"\n]+)"')
C_EXTS = (".c", ".cc", ".cpp", ".cxx")

class AlpacaRow(BaseModel):
    instruction: str
    input: str
    output: str


SYSTEM_PROMPT = (
    "You write spec-writing instructions for software verification.\n"
    "Given a SAW script and/or associated source files, return exactly one Alpaca-style instruction.\n"
    "The instruction must be standalone, <= 100 words, and contain no solution.\n"
    ""
)


USER_TEMPLATE = (
    "Primary SAW file: {saw_filename}\n"
    "Associated source files: {source_names}\n"
    "Goal: Produce one *instruction* that an assistant can use to write a SAW verification script. The instruction must directly reference functions/methods defined in the associated C/Java source in the associated source files.\n"
    "Rules for the instruction you will produce:\n"
    "- If any Cryptol modules are imported reference their module/property names in the instruction, but do not include any Cryptol source.\n"
    "- SAW only. Infer the backend from the excerpt: use jvm_* if `java_load_class` appears; use llvm_* if `llvm_load_module` appears.\n"
    "- Require a let-bound spec, e.g., `let <name>_spec = do {{ ... }};` (do NOT pass an inline `do {{ ... }}` directly as an argument).\n"
    "- Reference exact symbol names/signatures from the associated source (e.g., class.method or function prototypes) and call them accordingly.\n"
    "- Prefer symbolic inputs (`jvm_fresh_var` / `llvm_fresh_var`) over hard-coded constants; add minimal preconditions needed for termination or safety (loops, division, array bounds).\n"
    "- Do not reference the solvers being used.\n"
    "- Give only enough detail to specify what is being verified; do not include implementation details or code.\n"
    "- If helper functions, types, variables, or constraints can be infered, do not mention them in the instruction.\n"
    "\n"
    "Output format (MANDATORY):\n"
    "- Return ONLY a minified JSON object with keys: instruction, input, output.\n"
    "- Set \"output\" to an empty string \"\".\n"
    "- Set \"input\" to an empty string \"\".\n"
    "- ASCII only; no code fences, no trailing commas, no extra fields.\n"
    "- Do not include the source code in the JSON.\n"
    "\n"
    "SAW excerpt:\n"
    "-----8<-----\n{saw_excerpt}\n-----8<-----\n"
    "{sources_block}"
)

# --- Helper to build the per-source blocks and final user content ---
def build_sources_block(sources) -> str:
    """
    sources: iterable of dicts with keys: name (str), lang (str), code (str)
             (you can pass excerpts already trimmed)
    """
    parts = []
    for s in sources:
        parts.append(
            f"{s['name']} ({s['lang']}) excerpt:\n"
            "-----8<-----\n"
            f"{s['code']}\n"
            "-----8<-----\n"
        )
    return "".join(parts)

def build_user_prompt(
    filename: str,
    content: str,
    ) -> tuple[str, str]:
    """
    Returns (user_prompt, alpaca_input).
    alpaca_input mirrors your chosen input_mode; here we keep it very short deterministically.
    """
    sources = get_associated_sources(
        f"{ROOT_DIR}/{filename}", content
    )
    source_names = ", ".join(k for source in sources for k, v in source.items())
    source_code = ""
    for source in sources:
        for k, v in source.items():
            source_code += f"{k}\n{v}\n"
    #sources_block = build_sources_block(sources)
    user = USER_TEMPLATE.format(
        saw_filename=filename,
        source_names=source_names,
        saw_excerpt=content,
        sources_block=source_code,
    )
    # Deterministic 'input' (<=512 chars) from concatenated source names + tiny SAW hint
    #alpaca_input = (content[:256] + "\n" + source_names)[:512]
    alpaca_input = ""
    return user, source_code, alpaca_input


def get_associated_sources(saw_path: str | Path, content: str) -> list[Path]:
    """
    Get the java or C/C++ source files associated with a SAW file.
    Looks for llvm_load_module and java_load_class statements in the SAW content
    and attempts to find the corresponding source files in the same directory.
    Args:
        saw_path (str | Path): Path to the SAW file.
        content (str): Content of the SAW file.
    Returns:
        list[Dict[str, str]]: List of dictionaries mapping filenames to their content.
    """
    saw_path = Path(saw_path).expanduser().resolve()
    text = content
    base_dir = saw_path.parent

    results: list[dict[str, str]] = []
    seen_names: set[str] = set()

    # llvm_load_module "name.bc" -> ./name.{c,cc,cpp,cxx}
    for bc in LLVM_RE.findall(text):
        stem = Path(bc).stem
        for ext in C_EXTS:
            p = base_dir / f"{stem}{ext}"
            if p.exists():
                try:
                    code = p.read_text(encoding="utf-8", errors="replace")
                    if p.name not in seen_names:
                        results.append({p.name: f"```C\n{code}\n```"})
                        seen_names.add(p.name)
                except Exception:
                    pass
                break  # take the first C/C++ that exists
    # java_load_class "pkg.ClassName" -> ./ClassName.java
    for cls in JAVA_RE.findall(text):
        simple = cls.rsplit(".", 1)[-1]
        p = base_dir / f"{simple}.java"
        if p.exists():
            try:
                code = p.read_text(encoding="utf-8", errors="replace")
                if p.name not in seen_names:
                    results.append({p.name: f"```java\n{code}\n```"})
                    seen_names.add(p.name)
            except Exception:
                pass

    return results


if __name__ == "__main__":
    # --- example usage (set your SAW file here) ---
    data_df = pd.read_json("data/training_datasets/train_test_split/all_nocomments.jsonl", lines=True)
    

    SAW_FILE = Path("/absolute/path/to/verify.saw")
    if SAW_FILE.exists():
        for src in get_associated_sources(SAW_FILE):
            print(src)  # Path to the resolved C/Java file in the same directory
    else:
        print("Set SAW_FILE to a valid .saw path.")
