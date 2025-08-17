import ast, pathlib, collections

BASE = pathlib.Path("src/layaos")
symbols = collections.defaultdict(list)

for py in BASE.rglob("*.py"):
    if any(part in {"__pycache__", "legacy"} for part in py.parts):
        continue
    mod = py.relative_to("src").with_suffix("").as_posix().replace("/", ".")
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols[node.name].append((mod, py))

dupes = {k: v for k, v in symbols.items() if len(v) > 1}
if dupes:
    print("Duplicated symbols:")
    for name, locs in dupes.items():
        print(f" - {name}")
        for mod, path in locs:
            print(f"    {mod} :: {path}")
    raise SystemExit(1)
print("OK: no duplicate symbols in non-legacy modules.")