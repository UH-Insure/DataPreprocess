import re
from pathlib import Path
import pandas as pd

# Pattern to match URL in a line
PAT_URL = re.compile(r"https?://[^\s]+")
# Pattern to match content inside <% … %>
PAT_CONTENT = re.compile(r"<%(.*?)%>", re.DOTALL)

def parse_with_url_pattern(fp: Path):
    raw = fp.read_text(encoding="utf-8")
    # We split by newline + '<%' so that each piece corresponds to a block (except maybe first)
    parts = raw.split("\n<%")
    records = []
    for i, part in enumerate(parts):
        # The first part (i=0) is before the first block — skip it
        if i == 0:
            continue
        # part begins with content starting from after "<%"
        part = "<%" + part  # re-add the delimiter so the regex matches
        # Extract block content
        m = PAT_CONTENT.search(part)
        if not m:
            continue
        content = m.group(1).strip()
        # For determining URL: look just before the split point
        # We know the original raw text had "\n<%" at split, so the preceding line ends right before that newline
        # So we find the last URL in the text up to the split boundary
        # Reconstruct prefix:
        prefix = raw[: raw.find(part)]  # text before this block’s start
        urls = PAT_URL.findall(prefix)
        if urls:
            url = urls[-1]
        else:
            url = fp.stem
        # Sanitize URL for filename
        safe = url.replace("://", "_").replace("/", "_").replace("?", "_").replace("&", "_")
        filename = safe + ".txt"
        rec = {
            "filename": filename,
            "filetype": "txt",
            "content": content
        }
        records.append(rec)
    return records

def load_dir(input_dir: str, ext: str = ".txt") -> pd.DataFrame:
    recs = []
    p = Path(input_dir)
    for fp in p.glob(f"*{ext}"):
        recs.extend(parse_with_url_pattern(fp))
    df = pd.DataFrame(recs)
    return df

if __name__ == "__main__":
    INPUT_DIR = "/Users/josh/SecurityAnalytics/DataPreprocess/data/text"
    df = load_dir(INPUT_DIR)
    print("Rows:", len(df))
    print(df.head(100))
    df.to_json("/Users/josh/SecurityAnalytics/DataPreprocess/data/parsed_text_data.jsonl", orient="records", lines=True)