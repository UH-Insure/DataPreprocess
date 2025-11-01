SYSTEM_PROMPT_CRYPTOL = (
    "You write *spec-writing instructions* specifically for Cryptol.\n"
    "Given a code snippet, return exactly one Alpaca-style 'instruction' that asks "
    "a model to produce Cryptol specifications or properties suitable for the Cryptol REPL, "
    "e.g., type signatures, properties with pre/post conditions, and properties intended for "
    ":check / :prove. The instruction must be standalone, <=150 words, and contain no solution."
)

USER_TEMPLATE_CRYPTOL = (
    "File path: {filename}\n"
    "Language: Cryptol\n"
    "Goal: Produce one *instruction* asking the assistant to write Cryptol properties/specs for this file. "
    "Prefer properties suitable for :check / :prove and include any useful type signatures in the request.\n"
    "Return ONLY a JSON object with keys: instruction, input, output. Set 'output' to an empty string. "
    "If you include an 'input', keep it very short or empty.\n\n"
    "Code excerpt:\n"
    "-----8<-----\n{code}\n-----8<-----\n"
)

