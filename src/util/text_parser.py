import re
from pathlib import Path
import pandas as pd

# Keep your patterns (note: PAT_URL not needed anymore unless you want extra logic)
PAT_CONTENT = re.compile(r"<%(.*?)%>", re.DOTALL)

def parse_with_url_pattern(fp: Path):
    raw = fp.read_text(encoding="utf-8")
    records = []

    # Iterate with precise spans for each <% ... %> block
    for m in re.finditer(r"<%(.*?)%>", raw, flags=re.DOTALL):
        start, end = m.span()
        content = raw[start + 2 : end - 2].strip()

        # Find the nearest previous non-empty line just before the block
        before = raw[:start].rstrip("\n")
        source_line = ""
        for line in reversed(before.splitlines()):
            if line.strip():
                source_line = line.strip()
                break

        # Keep the line exactly as-is; fallback to filename if nothing found
        filename = source_line or fp.name

        records.append(
            {
                "filename": filename,   # URL or directory path preserved
                "filetype": "text",
                "content": content,
            }
        )

    return records

def load_dir(input_dir: str, ext: str = ".txt") -> pd.DataFrame:
    recs = []
    p = Path(input_dir)
    for fp in p.glob(f"*{ext}"):
        print("Processing:", fp)
        recs.extend(parse_with_url_pattern(fp))
    return pd.DataFrame(recs)

if __name__ == "__main__":
    INPUT_DIR = "data/text"
    df = load_dir(INPUT_DIR)
    print("Rows:", len(df))
    print(df.head(100))
    df.to_json(
        "data/parsed_text_data.jsonl",
        orient="records",
        lines=True,
    )
