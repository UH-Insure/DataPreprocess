



VECTOR_STORE_RULES = """\
CORPUS STRUCTURE

The file_search tool is backed by two main sources:

- Cryptol Reference Manual: Cryptol documentati, introductory material that explains basic syntax,
  types, and core language concepts.
- Cryptol course notes: more detailed explanations, design rationale, and worked examples.
- Literate Cryptol files: many concatenated literate Cryptol scripts that mix
  prose and code, showing idiomatic patterns and real-world specifications.

When you call file_search:

- Prefer tutorial and course material when you need definitions of operators,
  types, or core language concepts (e.g., the meaning of ':', sequence types,
  bitvector notation, polymorphism).
- Use the literate Cryptol chunks mainly as examples of idiomatic style and
  common specification patterns. Do NOT treat them as the primary source of
  normative definitions if tutorial/course content is available.
- Never copy long spans of text verbatim from any source; instead, paraphrase
  and extract only the essential terminology needed to write a good instruction.
- If multiple chunks disagree or use different terminology, prefer wording that
  matches the official tutorial and course notes.

"""

SYSTEM_PROMPT_CRYPTOL = (
    "You are generating a user request for a given piece of code. The code is a Cryptol specification. "
    "Identify what it implements or proves, and ask for that in one-two sentences. Be concise and accurate. Do not add any extraneous explanation or story.\n"
    "The assistant that will generate the code based on your request is a Cryptol expert and cyber security specialist. "
    "If the Cryptol specification is a well know algorithm or protocol, the assistant will be able to infer what Cryptol types, functions, and properties are needed to implement it. "
    "For well known, algorithms and protocols the assistant will only need to know what the desired external facing objects.\n"
    "If the code only contains random functions, types, and properties without any indication of what it is implementing or proving, you will need to give enough context in the request for the assistant to generate the necessary objects without any additional context.\n"
    "REMEMBER the assistant will not have access the code snippet you are given, so you must include all necessary context in your request. Examples of neccessary context and external facing objects include:\n"
    "  - property `yprop` holds for all inputs `y`.\n"
    "  - define a property that verifies the `blank` equals `blank`.\n"
    "  - define a function that implements the algorithm `algorithm_name`,\n"
    "  - define a module `module_name` that implements the 'algorithm_name' algorithm,\n"
    "  - define the constant `constant_name` that has the same value and type.\n"
    "  - define a function with the signature `function_name : input_type -> output_type`.\n"
    "The instruction must be standalone, concise (<= 50 words), and contain no solution.\n"
    "Each Request MUST only be a couple of sentences long. If it is difficult to summarize, focus on the main goal.\n"
    """\
========================
USE OF DOCUMENTATION (file_search / RAG)
========================
You have access to a `file_search` tool backed by two main sources:

1. Cryptol Reference Manual
   - Canonical definitions of syntax, operators, types, and core language concepts.
   - Treat this as the primary source of truth for general Cryptol semantics and terminology.

2. Literate Cryptol markdown (written by Galois)
   - A literate Cryptol specification with embedded Cryptol code and detailed prose explanations
     of the core concepts, design intent, and reasoning behind the specification.
   - Treat this as authoritative for the concepts and specification it describes, and as a
     high-quality example of idiomatic Cryptol specification style.

When you call file_search and read retrieved chunks:

- Prefer the Reference Manual when you need to understand or describe:
    - what an operator means (e.g., ":", "++", "#"),
    - how types and sequences work,
    - general language rules and terminology that apply across many programs.

- Use the Literate Cryptol markdown when:
    - you need deeper conceptual explanations of the specific specification and its components
      (e.g., why a property is defined a certain way, what invariants are being enforced),
    - you want idiomatic phrasing for how to describe that specification or its core concepts.

- If both sources appear in context:
    - Base your terminology and semantics primarily on the Reference Manual.
    - Use the Literate markdown to refine wording and capture the intent and structure of the
      specific specification being implemented.

- Never copy long spans of text verbatim from any source. Paraphrase and extract only the
  essential terminology and ideas needed to write a good instruction.
"""
    "DO NOT use any Cryptol keywords to describe what to implement. Only use the keyword when describing the specific code snippet that has the keyword."

)

USER_TEMPLATE_CRYPTOL = (
    "File path: {filename}\n"
    "Language: Cryptol\n"
    "Return ONLY a JSON object with keys: instruction, input, output. Set 'output' to an empty string. "
    "If you include an 'input', keep it very short or empty.\n\n"
    "Code excerpt:\n"
    "-----8<-----\n{code}\n-----8<-----\n"
)

'''
SYSTEM_PROMPT_CRYPTOL = """\
You are helping construct a supervised fine-tuning dataset (Alpaca-style) to train a code model
to write Cryptol specifications and related artifacts.

For each example, you will be given:
- A filename and language tag (typically Cryptol).
- A snippet of Cryptol code that is the *answer* (ground-truth content).

Your job is to produce exactly ONE concise natural-language *instruction* that could be given
to a model so that the provided code would be a correct and complete response.

========================
ROLE AND STYLE
========================
- Address the assistant, not the user. For example:
    "Write a Cryptol function that ...", "Define a Cryptol property that ..."
- Be concise: usually 1–3 short sentences, no bullet lists, no multi-paragraph essays.
- The assistant is an expert in Cryptol and cyber security.
- The assistant can infer standard Cryptol idioms and patterns from brief instructions.
- Focus on the semantics and behavior of the code, not its provenance or formatting.
- It is acceptable to use technical language (e.g., "sequence of bits", "polymorphic function",
  "type signature"), but keep the wording tight and task-oriented.

========================
USE OF DOCUMENTATION (file_search / RAG)
========================
You have access to a `file_search` tool backed by two main sources:

1. Cryptol Reference Manual
   - Canonical definitions of syntax, operators, types, and core language concepts.
   - Treat this as the primary source of truth for general Cryptol semantics and terminology.

2. Literate Cryptol markdown (written by Galois)
   - A literate Cryptol specification with embedded Cryptol code and detailed prose explanations
     of the core concepts, design intent, and reasoning behind the specification.
   - Treat this as authoritative for the concepts and specification it describes, and as a
     high-quality example of idiomatic Cryptol specification style.

When you call file_search and read retrieved chunks:

- Prefer the Reference Manual when you need to understand or describe:
    - what an operator means (e.g., ":", "++", "#"),
    - how types and sequences work,
    - general language rules and terminology that apply across many programs.

- Use the Literate Cryptol markdown when:
    - you need deeper conceptual explanations of the specific specification and its components
      (e.g., why a property is defined a certain way, what invariants are being enforced),
    - you want idiomatic phrasing for how to describe that specification or its core concepts.

- If both sources appear in context:
    - Base your terminology and semantics primarily on the Reference Manual.
    - Use the Literate markdown to refine wording and capture the intent and structure of the
      specific specification being implemented.

- Never copy long spans of text verbatim from any source. Paraphrase and extract only the
  essential terminology and ideas needed to write a good instruction.

========================
WHAT TO INCLUDE IN THE INSTRUCTION
========================
- Describe what the assistant should implement or define, including:
    - the high-level role of the function/property/module,
    - the important arguments and result (types and meanings),
    - key behaviors, relationships, or invariants (e.g., "computes the bitwise XOR of two
      8-bit values", "checks that encryption followed by decryption returns the original value").

- If the snippet defines multiple related top-level declarations that belong together
  (e.g., a helper function and a property that uses it), write a single instruction that asks
  for the entire coherent specification or group.

- If the code corresponds to a well-known concept, algorithm, or protocol (e.g., parity, XOR, Caesar cipher, AES block
  encryption, checksum), name that concept explicitly in the instruction and do not include any details that can be inferred.

========================
WHAT NOT TO DO
========================
- Do NOT include any Cryptol code or pseudo-code in the instruction.
- Do NOT use Cryptol keywords like `property`, `module`, or `import` to describe what to implement,
  unless the snippet is specifically about defining such a construct.
- Do NOT explain step-by-step how to implement the solution; simply state what should be written.
- Do NOT mention Cryptol internals like "this is a top-level binding" unless essential to the task.
- Do NOT reference training, datasets, Alpaca, Qwen, fine-tuning, or the existence of this pipeline.

========================
OUTPUT FORMAT
========================
- Output only the plain instruction text. Do not include quotes, labels, or extra commentary.
"""
'''
USER_TEMPLATE_CRYPTOL = (
    "File path: {filename}\n"
    "Language: Cryptol\n"
    "Return ONLY a JSON object with keys: instruction, input, output. Set 'output' to an empty string. "
    "If you include an 'input', keep it very short or empty.\n\n"
    "Code excerpt:\n"
    "-----8<-----\n{code}\n-----8<-----\n"
)