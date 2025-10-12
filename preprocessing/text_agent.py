import os
from openai import OpenAI


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


def preprocess_text_via_openai(raw_text: str, model: str = "gpt-4") -> str:
    """
    Send raw_text to the OpenAI API using the prompt template and return the cleaned snippet.
    """
    prompt = PROMPT_TEMPLATE.format(raw_text=raw_text)
    client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=1024,
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
    cleaned = preprocess_text_via_openai(raw)
    print("=== Cleaned Snippet ===")
    print(cleaned)
