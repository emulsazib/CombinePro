"""tree-sitter AST skeleton extraction.

Produces the token-cheap structural view agents receive instead of the full
codebase: class/function signatures + first docstring lines, bodies elided.
Output is deterministic (sorted paths, stable truncation) so it can sit in a
prompt-cached system block without invalidating the cache between wakes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_parser

from app.core.router import is_ignored

log = logging.getLogger(__name__)

LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
}

# Definition-like node types across the grammars above.
DEF_NODE_TYPES: frozenset[str] = frozenset({
    "class_definition", "function_definition", "decorated_definition",       # python (+ c/cpp function_definition)
    "class_declaration", "function_declaration", "method_definition",        # js/ts
    "generator_function_declaration", "interface_declaration",               # js/ts
    "abstract_class_declaration", "enum_declaration",                        # ts
    "method_declaration", "type_declaration",                                # go/java
    "function_item", "struct_item", "impl_item", "trait_item", "enum_item",  # rust
    "class", "module", "method", "singleton_method",                         # ruby
    "class_specifier", "struct_specifier",                                   # c/cpp
    "constructor_declaration", "record_declaration",                         # java/c#
})


@dataclass
class SkeletonBuilder:
    byte_cap: int = 24_000
    max_file_bytes: int = 512_000
    _parsers: dict[str, Parser] = field(default_factory=dict)
    _cache: dict[str, tuple[float, int, str]] = field(default_factory=dict)  # path -> (mtime, size, skeleton)

    def _parser_for(self, ext: str) -> tuple[str, Parser] | None:
        lang = LANG_BY_EXT.get(ext)
        if lang is None:
            return None
        parser = self._parsers.get(lang)
        if parser is None:
            try:
                parser = self._parsers[lang] = get_parser(lang)
            except Exception as exc:
                log.warning("No tree-sitter grammar for '%s': %s", lang, exc)
                return None
        return lang, parser

    def skeleton_for_file(self, path: Path) -> str:
        """Skeleton of one file, cached by (mtime, size)."""
        try:
            stat = path.stat()
        except OSError:
            return ""
        key = str(path)
        cached = self._cache.get(key)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]
        if stat.st_size > self.max_file_bytes:
            return ""
        parser_info = self._parser_for(path.suffix.lower())
        if parser_info is None:
            return ""
        lang, parser = parser_info
        try:
            source = path.read_bytes()
        except OSError:
            return ""
        if b"\0" in source[:8192]:  # binary
            return ""
        tree = parser.parse(source)
        lines: list[str] = []
        self._walk(tree.root_node, source, lang, depth=0, out=lines)
        skeleton = "\n".join(lines)
        self._cache[key] = (stat.st_mtime, stat.st_size, skeleton)
        return skeleton

    def skeleton_for_domain(self, workspace: Path, folder: str) -> str:
        """Concatenated per-file skeletons for one domain folder, byte-capped
        with deterministic ordering and truncation."""
        root = workspace / folder if folder else workspace
        if not root.is_dir():
            return ""
        chunks: list[str] = []
        used = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in LANG_BY_EXT:
                continue
            rel = path.relative_to(workspace).as_posix()
            if is_ignored(rel):
                continue
            body = self.skeleton_for_file(path)
            if not body:
                continue
            chunk = f"# file: {rel}\n{body}\n"
            if used + len(chunk) > self.byte_cap:
                chunks.append(f"# ... skeleton truncated at {self.byte_cap} bytes ...")
                break
            chunks.append(chunk)
            used += len(chunk)
        return "\n".join(chunks)

    # ------------------------------------------------------------------ walk

    def _walk(self, node: Node, source: bytes, lang: str, depth: int, out: list[str]) -> None:
        for child in node.children:
            if child.is_named and child.type in DEF_NODE_TYPES:
                if child.type == "decorated_definition":
                    # Skip the decorator wrapper; emit the inner def at this depth.
                    self._walk(child, source, lang, depth, out)
                    continue
                header = self._header(child, source)
                if header:
                    out.append("    " * depth + header)
                    doc = self._docstring(child, source) if lang == "python" else ""
                    if doc:
                        out.append("    " * (depth + 1) + f'"""{doc}"""')
                self._walk(child, source, lang, depth + 1, out)
            elif child.child_count:
                # Recurse through containers (blocks, export statements, namespaces)
                # without changing depth.
                self._walk(child, source, lang, depth, out)

    def _header(self, node: Node, source: bytes) -> str:
        body = node.child_by_field_name("body")
        end = body.start_byte if body is not None else node.end_byte
        text = source[node.start_byte : end].decode("utf-8", errors="replace")
        if body is None:
            text = text.split("\n", 1)[0]
        # Collapse a multi-line signature into one line.
        header = " ".join(part.strip() for part in text.strip().splitlines() if part.strip())
        if len(header) > 300:
            header = header[:297] + "..."
        return f"{header} ..." if body is not None else header

    def _docstring(self, node: Node, source: bytes) -> str:
        body = node.child_by_field_name("body")
        if body is None or not body.named_children:
            return ""
        first = body.named_children[0]
        if first.type == "string":
            string_node = first
        elif first.type == "expression_statement" and first.children and first.children[0].type == "string":
            string_node = first.children[0]
        else:
            return ""
        raw = source[string_node.start_byte : string_node.end_byte].decode("utf-8", errors="replace")
        stripped = raw.strip().strip("rRbBuU").strip("\"'")
        first_line = next((ln.strip() for ln in stripped.splitlines() if ln.strip()), "")
        return first_line[:200]
