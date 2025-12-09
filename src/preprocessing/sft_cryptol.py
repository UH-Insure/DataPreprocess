SYSTEM_PROMPT_CRYPTOL = (
    "You are generating a user request for a given piece of code. The code is a Cryptol specification. "
    "Identify what it implements or proves, and ask for that in one sentence. Be concise and accurate. Do not add any extraneous explanation or story.\n"
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
    "`property` is a keyword in Cryptol used to define boolean conditions that can be checked by SAT solvers. DO NOT STATE 'define a property that ....' FOR ANYTHING OTHER THAN THE STATEMENTS FOLLOWING THE 'property' KEYWORD.\n"
    "`module` is a keyword in Cryptol used to define a collection of related definitions, including types, functions, and properties so that they can be imported and used together. DO NOT STATE 'define a module that ....' FOR ANYTHING OTHER THAN THE STATEMENTS FOLLOWING THE 'module' KEYWORD.\n"
    "(file_search / RAG) You have access to a `file_search` tool that contains a 'Cryptol Reference Manual'. Use the reference manual for definitions of syntax, operators, types, and core language concepts.\n"
    "The instruction must be standalone, concise (<= {max_words} words), and contain no solution.\n"
    "Each Request MUST only be a couple of sentences long. If it is difficult to summarize, focus on the main goal. You cannot end the instruction with as shown because the assistant will not be shown anything other than your generated instruction.\n"
)

USER_TEMPLATE_CRYPTOL = (
    "File path: {filename}\n"
    "Language: Cryptol\n"
    "Return ONLY a JSON object with keys: instruction, input, output. Set 'output' to an empty string. "
    "If you include an 'input', keep it very short or empty.\n\n"
    "Code excerpt:\n"
    "-----8<-----\n{code}\n-----8<-----\n"
)