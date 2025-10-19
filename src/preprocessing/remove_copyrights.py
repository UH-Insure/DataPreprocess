# remove_copyrights.py
import json
import re
from pathlib import Path

# Robust copyright matchers
COPYRIGHT_BLOCK = re.compile(r"/\*.*?copyright.*?\*/", re.IGNORECASE | re.DOTALL)
COPYRIGHT_LINE  = re.compile(r"^[ \t]*//.*copyright.*?$", re.IGNORECASE | re.MULTILINE)

def strip_copyrights_from_row(row: dict) -> dict:
    if "content" in row and isinstance(row["content"], str):
        s = row["content"]
        s = COPYRIGHT_BLOCK.sub("", s)
        s = COPYRIGHT_LINE.sub("", s)
        row["content"] = s
    return row

def process_jsonl(input_path: str, output_path: str = None):
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_nocopyright.jsonl")

    with input_path.open("r", encoding="utf-8") as infile, \
         Path(output_path).open("w", encoding="utf-8") as outfile:
        for line in infile:
            if not line.strip():
                continue
            row = json.loads(line)
            outfile.write(json.dumps(strip_copyrights_from_row(row), ensure_ascii=False) + "\n")

    print(f"Processed file written to: {output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python remove_copyrights.py <input.jsonl> [output.jsonl]")
    else:
        process_jsonl(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
