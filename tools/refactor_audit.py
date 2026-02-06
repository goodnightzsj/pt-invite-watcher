#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class FileDefs:
    path: str
    defs: set[str]


ROUTE_DECORATOR_RE = re.compile(
    r"@(?P<obj>app|router)\.(?P<m>get|post|put|delete|patch|options|head|websocket)\(\s*[\"'](?P<path>[^\"']+)[\"']"
)


def _run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _git_ls_tree(ref: str, root: str) -> list[str]:
    out = _run_git(["ls-tree", "-r", "--name-only", ref, "--", root])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _git_show(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True, stderr=subprocess.DEVNULL)


def _git_has_path(ref: str, path: str) -> bool:
    try:
        subprocess.check_output(["git", "cat-file", "-e", f"{ref}:{path}"], stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def _list_py_files_current(root: str) -> list[str]:
    base = Path(root)
    if not base.exists():
        return []
    return [p.as_posix() for p in base.rglob("*.py") if p.is_file()]


def _top_level_defs(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def _top_level_class_methods(text: str) -> dict[str, set[str]]:
    """
    Return: {class_name: {method_name, ...}}

    Only includes methods defined directly on the class body (FunctionDef / AsyncFunctionDef).
    Nested functions inside methods are intentionally ignored.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}

    out: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods: set[str] = set()
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(item.name)
        out[node.name] = methods
    return out


def _extract_routes(text: str) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for m in ROUTE_DECORATOR_RE.finditer(text):
        routes.add((m.group("m"), m.group("path")))
    return routes


def _find_definition_files(name: str, *, search_root: str) -> list[str]:
    patterns = [f"def {name}(", f"async def {name}(", f"class {name}(", f"class {name}:"]
    hits: list[str] = []
    for p in Path(search_root).rglob("*.py"):
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if any(pat in txt for pat in patterns):
            hits.append(p.as_posix())
    return hits


KNOWN_RENAMES: dict[str, str] = {
    "_cfg_bool": "cfg_bool",
    "_cfg_int": "cfg_int",
    "_cfg_str": "cfg_str",
    "_safe_dict": "safe_dict",
    "_safe_list": "safe_list",
    "_safe_str": "safe_str",
    "_safe_int": "safe_int",
    "_hosts_related": "hosts_related",
    "_page_kind_from_url": "page_kind_from_url",
    "_site_page_kind": "page_kind_from_url",
    "_default_paths": "default_paths_for_template",
    "_site_entry_view": "site_entry_view",
    "_relative_path_from_page_url": "relative_path_from_page_url",
    "_load_app_config": "load_app_config",
    "_load_sites_config": "load_sites_config",
}


@dataclass(frozen=True)
class MissingDef:
    old_file: str
    name: str


def _union_paths(ref: str, root: str) -> list[str]:
    old = set(p for p in _git_ls_tree(ref, root) if p.endswith(".py"))
    cur = set(p for p in _list_py_files_current(root) if p.endswith(".py"))
    return sorted(old | cur)


def audit_defs(ref: str, root: str) -> tuple[list[MissingDef], dict[str, dict[str, list[str]]]]:
    missing: list[MissingDef] = []
    moved: dict[str, dict[str, list[str]]] = {}

    for path in _union_paths(ref, root):
        old_text = _git_show(ref, path) if _git_has_path(ref, path) else ""
        new_text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""

        old_defs = _top_level_defs(old_text) if old_text else set()
        new_defs = _top_level_defs(new_text) if new_text else set()
        removed = sorted(old_defs - new_defs)
        if not removed:
            continue

        for name in removed:
            renamed_to = KNOWN_RENAMES.get(name)
            if renamed_to:
                renamed_hits = _find_definition_files(renamed_to, search_root=root)
                if renamed_hits:
                    moved.setdefault(path, {})[name] = renamed_hits
                    continue

            if name.startswith("_"):
                no_underscore = name.lstrip("_")
                if no_underscore:
                    renamed_hits = _find_definition_files(no_underscore, search_root=root)
                    if renamed_hits:
                        moved.setdefault(path, {})[name] = renamed_hits
                        continue

            hits = _find_definition_files(name, search_root=root)
            hits = [h for h in hits if h != path]
            if hits:
                moved.setdefault(path, {})[name] = hits
            else:
                missing.append(MissingDef(old_file=path, name=name))

    return missing, moved


def audit_routes(ref: str, root: str) -> tuple[set[tuple[str, str]], set[tuple[str, str]], set[tuple[str, str]], set[tuple[str, str]]]:
    old_routes: set[tuple[str, str]] = set()
    for path in _git_ls_tree(ref, root):
        if not path.endswith(".py"):
            continue
        try:
            old_routes |= _extract_routes(_git_show(ref, path))
        except Exception:
            continue

    new_routes: set[tuple[str, str]] = set()
    for path in _list_py_files_current(root):
        if not path.endswith(".py"):
            continue
        try:
            new_routes |= _extract_routes(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue

    old_only = old_routes - new_routes
    new_only = new_routes - old_routes
    return old_routes, new_routes, old_only, new_only


@dataclass(frozen=True)
class ClassMethods:
    files: list[str]
    methods: set[str]


def audit_class_methods(ref: str, root: str, *, classes: Iterable[str]) -> dict[str, tuple[ClassMethods, ClassMethods]]:
    """
    Compare method sets for selected classes between old ref and current working tree.

    Returns: {class_name: (old, new)}
    """
    target = [str(c).strip() for c in classes if str(c).strip()]
    if not target:
        return {}
    target_set = set(target)

    old: dict[str, ClassMethods] = {}
    for path in _git_ls_tree(ref, root):
        if not path.endswith(".py"):
            continue
        try:
            txt = _git_show(ref, path)
        except Exception:
            continue
        mapping = _top_level_class_methods(txt)
        for cls, methods in mapping.items():
            if cls not in target_set:
                continue
            item = old.get(cls)
            if item is None:
                old[cls] = ClassMethods(files=[path], methods=set(methods))
            else:
                item.files.append(path)
                item.methods |= set(methods)

    new: dict[str, ClassMethods] = {}
    for path in _list_py_files_current(root):
        if not path.endswith(".py"):
            continue
        try:
            txt = Path(path).read_text(encoding="utf-8")
        except Exception:
            continue
        mapping = _top_level_class_methods(txt)
        for cls, methods in mapping.items():
            if cls not in target_set:
                continue
            item = new.get(cls)
            if item is None:
                new[cls] = ClassMethods(files=[path], methods=set(methods))
            else:
                item.files.append(path)
                item.methods |= set(methods)

    out: dict[str, tuple[ClassMethods, ClassMethods]] = {}
    for cls in target:
        out[cls] = (
            old.get(cls) or ClassMethods(files=[], methods=set()),
            new.get(cls) or ClassMethods(files=[], methods=set()),
        )
    return out


def _resolve_missing_symbol(name: str, *, search_root: str) -> list[str]:
    """
    Best-effort: find where a missing symbol might have been moved/renamed to.

    This reuses the same heuristics as top-level def auditing:
    - known renames (e.g. _load_app_config -> load_app_config)
    - same-name search
    - underscore stripping (e.g. _sync_site_list_summary -> sync_site_list_summary)
    """
    raw = str(name or "").strip()
    if not raw:
        return []

    renamed_to = KNOWN_RENAMES.get(raw)
    if renamed_to:
        hits = _find_definition_files(renamed_to, search_root=search_root)
        if hits:
            return hits

    hits = _find_definition_files(raw, search_root=search_root)
    if hits:
        return hits

    if raw.startswith("_"):
        no_underscore = raw.lstrip("_")
        if no_underscore:
            hits = _find_definition_files(no_underscore, search_root=search_root)
            if hits:
                return hits

    return []


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit refactors to avoid missing function/route migrations.")
    parser.add_argument("--ref", default="HEAD", help="Git ref to compare against (default: HEAD)")
    parser.add_argument("--root", default="pt_invite_watcher", help="Package root to audit (default: pt_invite_watcher)")
    parser.add_argument(
        "--class",
        dest="classes",
        action="append",
        default=[],
        help="Audit methods of this class name (repeatable). Example: --class Scanner --class SqliteStore",
    )
    args = parser.parse_args(argv)

    ref = str(args.ref)
    root = str(args.root).strip().rstrip("/")

    missing, moved = audit_defs(ref, root)
    old_routes, new_routes, old_only, new_only = audit_routes(ref, root)
    class_report = audit_class_methods(ref, root, classes=args.classes)

    _print_section("Routes")
    print(f"old={len(old_routes)} new={len(new_routes)} missing_in_new={len(old_only)} new_extra={len(new_only)}")
    for method, path in sorted(old_only)[:200]:
        print(f"  MISSING {method} {path}")
    for method, path in sorted(new_only)[:200]:
        print(f"  EXTRA   {method} {path}")

    _print_section("Top-level defs removed")
    if not missing and not moved:
        print("no removed top-level defs detected")
    else:
        if moved:
            print("moved/renamed candidates:")
            for file_path, mapping in sorted(moved.items()):
                print(f"- {file_path}")
                for name, hits in sorted(mapping.items()):
                    hits_preview = ", ".join(hits[:5])
                    more = " ..." if len(hits) > 5 else ""
                    print(f"  {name} -> {hits_preview}{more}")

        if missing:
            print("POTENTIALLY DROPPED (not found anywhere):")
            for item in missing[:200]:
                print(f"  {item.old_file}: {item.name}")

    missing_methods_total = 0
    if class_report:
        _print_section("Class methods")
        for cls, (old, new) in class_report.items():
            missing_methods_raw = sorted(old.methods - new.methods)
            extra_methods = sorted(new.methods - old.methods)

            moved_candidates: dict[str, list[str]] = {}
            missing_methods: list[str] = []
            for m in missing_methods_raw:
                hits = _resolve_missing_symbol(m, search_root=root)
                hits = [h for h in hits if h not in new.files]
                if hits:
                    moved_candidates[m] = hits
                else:
                    missing_methods.append(m)

            missing_methods_total += len(missing_methods)
            print(
                f"{cls}: old={len(old.methods)} new={len(new.methods)} missing_in_new={len(missing_methods)} moved_candidates={len(moved_candidates)} new_extra={len(extra_methods)}"
            )
            if old.files:
                print(f"  old_files: {', '.join(old.files[:5])}" + (" ..." if len(old.files) > 5 else ""))
            if new.files:
                print(f"  new_files: {', '.join(new.files[:5])}" + (" ..." if len(new.files) > 5 else ""))
            for name, hits in sorted(moved_candidates.items()):
                hits_preview = ", ".join(hits[:5])
                more = " ..." if len(hits) > 5 else ""
                print(f"  MOVED_METHOD    {name} -> {hits_preview}{more}")
            for m in missing_methods[:200]:
                print(f"  MISSING_METHOD {m}")
            for m in extra_methods[:200]:
                print(f"  EXTRA_METHOD   {m}")

    ok = not old_only and not new_only and not missing and missing_methods_total == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
