import re
from pathlib import Path
from typing import Dict, List, Optional, Iterable, Set, Tuple, Any
import pandas as pd
import networkx as nx

# ---------------------------
# Regexes (operate on stripped content)
# ---------------------------
MODULE_RE = re.compile(r"(?m)^\s*module\s+([A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*)\b")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*)\b")
TYPE_HEAD_RE = re.compile(r"(?m)^\s*type\s+([A-Z][A-Za-z0-9_]*)\b([^\n=]*)=\s*")
VAL_TYPE_SIG_RE = re.compile(r"(?m)^\s*([a-z_][A-Za-z0-9_']*)\s*:\s*(.+)$")
CAPNAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\b")

# Ignore capitalized tokens that are not user-defined type constructors
BUILTINS_STOP = {
    "Bit", "Integer", "Rational", "True", "False"
}

def _balanced_record_span(text: str, start_idx: int) -> int:
    """Match '{ ... }' with nesting; return end index (exclusive)."""
    if start_idx >= len(text) or text[start_idx] != "{":
        nl = text.find("\n", start_idx)
        return len(text) if nl == -1 else nl
    depth, i = 0, start_idx
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i

def extract_module_name(text: str) -> Optional[str]:
    m = MODULE_RE.search(text)
    return m.group(1) if m else None

def extract_imports(text: str) -> List[str]:
    return IMPORT_RE.findall(text)

def extract_type_defs(text: str) -> Dict[str, str]:
    """Return {TypeName: type_body_string}."""
    out: Dict[str, str] = {}
    for m in TYPE_HEAD_RE.finditer(text):
        name = m.group(1)
        body_start = m.end()
        i = body_start
        while i < len(text) and text[i].isspace():
            i += 1
        if i < len(text) and text[i] == "{":
            end = _balanced_record_span(text, i)
            out[name] = text[i:end].strip()
        else:
            nl = text.find("\n", body_start)
            out[name] = text[body_start:nl if nl != -1 else len(text)].strip()
    return out

def extract_value_type_sigs(text: str) -> Dict[str, str]:
    return {name: ty.strip() for name, ty in VAL_TYPE_SIG_RE.findall(text)}

def capitalized_idents(s: str) -> Set[str]:
    names = set(CAPNAME_RE.findall(s))
    return {n for n in names if n not in BUILTINS_STOP}

# ---------------------------
# DF → Graph
# ---------------------------
def build_graph_from_df(
    df: pd.DataFrame,
    filename_col: str = "filename",
    content_col: str = "content",
    filedeps_col: str = "file_deps",
) -> Tuple[nx.DiGraph, pd.DataFrame]:
    """
    Returns (G, summary_df).
    summary_df has per-file extracted fields to inspect/debug.
    """
    # Normalize file_deps to lists
    if filedeps_col in df.columns:
        df = df.copy()
        df[filedeps_col] = df[filedeps_col].apply(lambda x: x if isinstance(x, list) else ([] if pd.isna(x) else [x]))
    else:
        df = df.copy()
        df[filedeps_col] = [[] for _ in range(len(df))]

    # Extract per-row info
    extracted_rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        fn = str(row[filename_col])
        text = str(row[content_col] or "")
        module = extract_module_name(text)
        imports = extract_imports(text)
        type_defs = extract_type_defs(text)
        value_sigs = extract_value_type_sigs(text)
        extracted_rows.append({
            "filename": fn,
            "module": module,
            "imports": imports,
            "type_defs": type_defs,          # dict name -> body
            "value_sigs": value_sigs,        # dict name -> typeExpr
            "file_deps": row[filedeps_col],  # filenames or module names
        })
    summary_df = pd.DataFrame(extracted_rows)

    # Build filename -> module map (for resolving file_deps)
    fname_to_module: Dict[str, str] = {}
    for _, r in summary_df.iterrows():
        if r["module"]:
            fname_to_module[r["filename"]] = r["module"]

    # Build graph
    G = nx.DiGraph()

    # Index of where a type is defined: TypeName -> Module
    type_to_module: Dict[str, str] = {}

    # First pass: add module nodes & type definition nodes
    for _, r in summary_df.iterrows():
        module = r["module"] or f"__file__::{Path(r['filename']).stem}"
        # module node
        if module not in G:
            G.add_node(module, kind="module", files=[r["filename"]], declared=bool(r["module"]))
        else:
            # accumulate files in case of duplicates
            files = set(G.nodes[module].get("files", []))
            files.add(r["filename"])
            G.nodes[module]["files"] = sorted(files)

        # type defs
        for tname in r["type_defs"].keys():
            type_to_module.setdefault(tname, module)
            tnode = f"{module}.{tname}"
            if tnode not in G:
                G.add_node(tnode, kind="type", module=module)
            G.add_edge(module, tnode, rel="defines")

    # Second pass: add imports (declared imports + file_deps-resolved)
    for _, r in summary_df.iterrows():
        src_mod = r["module"] or f"__file__::{Path(r['filename']).stem}"

        # 2a) imports from source content
        for imp in r["imports"]:
            if imp not in G:
                G.add_node(imp, kind="module", files=[], declared=False)
            G.add_edge(src_mod, imp, rel="imports", via="import")

        # 2b) imports from file_deps (filenames or modules)
        for dep in r["file_deps"]:
            if isinstance(dep, str) and dep.endswith(".cry"):
                tgt_mod = fname_to_module.get(dep)
                if not tgt_mod:
                    # fall back to pseudo
                    tgt_mod = f"__file__::{Path(dep).stem}"
                    if tgt_mod not in G:
                        G.add_node(tgt_mod, kind="module", files=[dep], declared=False, pseudo=True)
                if tgt_mod not in G:
                    G.add_node(tgt_mod, kind="module", files=[dep], declared=False)
                G.add_edge(src_mod, tgt_mod, rel="imports", via="file_deps")
            else:
                # treat dep as a module name
                tgt_mod = str(dep)
                if tgt_mod not in G:
                    G.add_node(tgt_mod, kind="module", files=[], declared=False)
                G.add_edge(src_mod, tgt_mod, rel="imports", via="file_deps")

    # Third pass: add type usage edges
    for _, r in summary_df.iterrows():
        mod = r["module"] or f"__file__::{Path(r['filename']).stem}"

        # value signatures
        for ty in r["value_sigs"].values():
            for cap in capitalized_idents(ty):
                def_mod = type_to_module.get(cap)
                if def_mod:
                    G.add_edge(mod, f"{def_mod}.{cap}", rel="uses")
                else:
                    unk = f"?.{cap}"
                    if unk not in G:
                        G.add_node(unk, kind="type", unresolved=True)
                    G.add_edge(mod, unk, rel="uses")

        # type bodies
        for body in r["type_defs"].values():
            for cap in capitalized_idents(body):
                def_mod = type_to_module.get(cap)
                if def_mod:
                    G.add_edge(mod, f"{def_mod}.{cap}", rel="uses")
                else:
                    unk = f"?.{cap}"
                    if unk not in G:
                        G.add_node(unk, kind="type", unresolved=True)
                    G.add_edge(mod, unk, rel="uses")

    return G, summary_df

# ---------------------------
# Coverage helpers
# ---------------------------
def coverage_report_from_df(
    G: nx.DiGraph,
    df: pd.DataFrame,
    training_mask: Optional[pd.Series] = None,
    filename_col: str = "filename",
) -> Dict[str, Any]:
    """
    training_mask: boolean Series over df rows indicating which files are in the training set.
                   If None, assumes all rows are in training.
    """
    if training_mask is None:
        training_mask = pd.Series([True] * len(df), index=df.index)

    # Collect modules present in training files
    df_train = df.loc[training_mask]
    training_files = {str(Path(fn).resolve()) for fn in df_train[filename_col].astype(str)}
    training_modules: Set[str] = set()
    for n, data in G.nodes(data=True):
        if data.get("kind") == "module":
            for f in data.get("files", []):
                if Path(f).resolve().__str__() in training_files:
                    training_modules.add(n)
                    break

    # What modules do training modules import?
    imported_by_training: Set[str] = set()
    for m in training_modules:
        for _, tgt, ed in G.out_edges(m, data=True):
            if ed.get("rel") == "imports":
                imported_by_training.add(tgt)

    # Which of those imported modules are not present in the training set?
    missing_mods = sorted(t for t in imported_by_training if t not in training_modules)

    # Type coverage: what types do training modules use, and are their defs present?
    defined_types_in_training = {
        n for n, d in G.nodes(data=True)
        if d.get("kind") == "type" and d.get("module") in training_modules
    }
    used_types_by_training = {
        tgt for m in training_modules
        for _, tgt, ed in G.out_edges(m, data=True)
        if ed.get("rel") == "uses"
    }
    missing_type_defs = sorted(t for t in used_types_by_training if t not in defined_types_in_training)

    unresolved_types = sorted(
        t for t in missing_type_defs if G.nodes.get(t, {}).get("unresolved") is True
    )

    return {
        "training_modules": sorted(training_modules),
        "imports_by_training": sorted(imported_by_training),
        "missing_modules_in_training": missing_mods,
        "used_types_by_training": sorted(used_types_by_training),
        "missing_type_defs_in_training": missing_type_defs,
        "unresolved_types": unresolved_types,
    }
