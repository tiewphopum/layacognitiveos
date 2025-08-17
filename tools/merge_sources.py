#!/usr/bin/env python3
"""
merge_sources.py

Merge multiple source files into one, driven by a YAML/JSON (or newline list) of paths.
Useful for giving AI a single file that contains all relevant code, separated by file path.
"""

from __future__ import annotations
import os, sys, argparse, json, re
from typing import Any, List, Dict

# -------- config parsing --------
def load_config(path: str) -> List[Dict[str, Any]]:
    data = None
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = yaml.safe_load(f)
    except Exception:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
            data = lines

    def normalize_item(it):
        if isinstance(it, str):
            return {"path": it}
        if isinstance(it, dict):
            if "path" in it or "file" in it:
                d = dict(it)
                if "file" in d and "path" not in d:
                    d["path"] = d.pop("file")
                return d
        raise ValueError(f"Unsupported item in config: {it!r}")

    if isinstance(data, dict) and "files" in data:
        items = [normalize_item(x) for x in data["files"]]
    elif isinstance(data, list):
        items = [normalize_item(x) for x in data]
    else:
        raise SystemExit("Config must be a list or have a 'files' key.")
    return items

# -------- utilities --------
EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "jsx", ".json": "json", ".yml": "yaml", ".yaml": "yaml",
    ".md": "markdown", ".sh": "bash", ".zsh": "bash", ".ps1": "powershell",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".sql": "sql", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".css": "css", ".scss": "scss", ".html": "html", ".vue": "vue",
}

def guess_lang(path: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    ext = os.path.splitext(path)[1].lower()
    return EXT_LANG.get(ext, "")

def read_file_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# -------- rendering --------
def render_md(items: List[Dict[str, Any]], out: str, root: str, title: str, use_fence: bool, skip_missing: bool):
    parts = [f"# {title}", ""]
    for it in items:
        src = os.path.join(root, it["path"]) if not os.path.isabs(it["path"]) else it["path"]
        alias = it.get("alias") or it["path"]
        lang = guess_lang(src, it.get("lang"))
        if not os.path.exists(src):
            msg = f"⚠️ Missing: {src}"
            if skip_missing:
                parts += [f"## `{alias}`", "", msg, ""]
                continue
            else:
                raise FileNotFoundError(msg)
        code = read_file_text(src)
        parts += [f"## `{alias}`", f"_Source: `{os.path.abspath(src)}`_", ""]
        if use_fence:
            fence_lang = lang or ""
            parts += [f"```{fence_lang}", code.rstrip(), "```", ""]
        else:
            parts += [code.rstrip(), ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

def render_plain(items: List[Dict[str, Any]], out: str, root: str, separator: str, skip_missing: bool):
    parts = []
    sep_line = separator if separator else "=" * 80
    for it in items:
        src = os.path.join(root, it["path"]) if not os.path.isabs(it["path"]) else it["path"]
        alias = it.get("alias") or it["path"]
        header = f"{sep_line}\n# PATH: {alias}\n# SRC : {os.path.abspath(src)}\n{sep_line}\n"
        if not os.path.exists(src):
            msg = f"# MISSING: {os.path.abspath(src)}\n"
            if skip_missing:
                parts.append(header + msg)
                continue
            else:
                raise FileNotFoundError(msg.strip())
        code = read_file_text(src)
        parts.append(header + code.rstrip() + "\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(parts))

# -------- main --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="YAML/JSON/newline list of files to merge")
    ap.add_argument("--out", default=None, help="Output file (defaults by format)")
    ap.add_argument("--format", choices=["md","plain"], default="md")
    ap.add_argument("--root", default=".", help="Base directory to resolve relative paths")
    ap.add_argument("--skip-missing", action="store_true", help="Skip missing files instead of failing")
    ap.add_argument("--separator", default="="*80, help="Plain mode separator line")
    ap.add_argument("--title", default="Merged Sources", help="Title for Markdown output")
    ap.add_argument("--no-fence", action="store_true", help="Do not wrap code in ``` fences (Markdown)")
    args = ap.parse_args()

    items = load_config(args.config)
    out = args.out
    if out is None:
        out = "merged.md" if args.format == "md" else "merged.txt"

    if args.format == "md":
        render_md(items, out=out, root=args.root, title=args.title, use_fence=(not args.no_fence), skip_missing=args.skip_missing)
    else:
        render_plain(items, out=out, root=args.root, separator=args.separator, skip_missing=args.skip_missing)

    print(f"[ok] wrote {out}")

if __name__ == "__main__":
    main()