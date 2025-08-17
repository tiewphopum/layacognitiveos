#!/usr/bin/env python3
"""
summarize_symbols.py

Scan a Python project and produce a summary of:
- class names (with __init__ arguments + default values)
- top-level function names
- optional: methods inside classes

Usage:
  python summarize_symbols.py --root . --out symbols.md
  python summarize_symbols.py --root . --out symbols.md --include-methods
"""

from __future__ import annotations
import os, re, ast, argparse

IGNORE_DEFAULT = r"venv|\.git|__pycache__|build|dist|site-packages|\.mypy_cache|\.pytest_cache"

def should_skip(path: str, ignore_regex: str) -> bool:
    return re.search(ignore_regex, path) is not None

def get_init_args(class_node: ast.ClassDef):
    """Extract __init__ args and defaults as strings"""
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            args = node.args
            arg_list = []
            defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
            for arg, default in zip(args.args, defaults):
                if arg.arg == "self":
                    continue
                if default is None:
                    arg_list.append(f"{arg.arg}")
                else:
                    try:
                        val = ast.literal_eval(default)
                        arg_list.append(f"{arg.arg}={repr(val)}")
                    except Exception:
                        # fallback if default too complex
                        arg_list.append(f"{arg.arg}=…")
            return arg_list
    return []

def scan_file(py_path: str, include_methods: bool):
    try:
        with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
        tree = ast.parse(src, filename=py_path)
    except SyntaxError:
        return None

    classes = []     # [(class_name, init_args, [method_names?])]
    functions = []   # [func_name]

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            init_args = get_init_args(node)
            methods = []
            if include_methods:
                for b in node.body:
                    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name != "__init__":
                        methods.append(b.name)
            classes.append((node.name, init_args, methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)

    return {"classes": classes, "functions": functions}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Project root to scan")
    ap.add_argument("--out", default="symbols.md", help="Output markdown file")
    ap.add_argument("--ignore", default=IGNORE_DEFAULT, help="Regex of paths to ignore")
    ap.add_argument("--include-methods", action="store_true", help="Include methods under classes")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip(os.path.join(dirpath, d), args.ignore)]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            if should_skip(full, args.ignore):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            res = scan_file(full, include_methods=args.include_methods)
            if res is None:
                continue
            items.append((rel, res))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# Symbols Summary\n\n")
        f.write(f"- Root: `{root}`\n\n")
        for rel, res in sorted(items):
            f.write(f"## `{rel}`\n\n")
            if res["classes"]:
                f.write("**Classes**\n\n")
                for cls, init_args, methods in res["classes"]:
                    if init_args:
                        f.write(f"- `{cls}` (init: {', '.join(init_args)})\n")
                    else:
                        f.write(f"- `{cls}`\n")
                    if args.include_methods and methods:
                        for m in methods:
                            f.write(f"  - `{m}`\n")
                f.write("\n")
            if res["functions"]:
                f.write("**Functions**\n\n")
                for fn in res["functions"]:
                    f.write(f"- `{fn}`\n")
                f.write("\n")

    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()