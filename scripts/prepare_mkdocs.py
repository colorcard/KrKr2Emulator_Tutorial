#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".mkdocs-src"
IGNORE_DIRS = {
    ".git",
    ".github",
    ".mkdocs-src",
    ".mkdocs-site",
    ".vitepress",
    "node_modules",
    "site",
}

SECTION_STYLES = {
    "本节目标": "goal",
    "术语预览": "terms",
    "动手实践": "practice",
    "对照项目源码": "source",
    "本节小结": "summary",
    "练习题与答案": "quiz",
    "下一步": "next",
}

LINK_RE = re.compile(r"(!?\[[^\]]+\]\()([^)#\s]+)(#[^)]+)?(\))")
TARGET_HEADING_RE = re.compile(
    r"^(##)\s+(本节目标|术语预览|动手实践|对照项目源码|本节小结|练习题与答案|下一步)\s*$"
)
ANY_H1_H2_RE = re.compile(r"^(#{1,2})\s+")
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})")


def rewrite_link_target(target: str) -> str:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target

    fragment = ""
    if "#" in target:
        target, fragment = target.split("#", 1)
        fragment = "#" + fragment

    if target.endswith("/"):
        target = target.rstrip("/") + "/index.md"
    else:
        name = Path(target).name
        if name == "README.md":
            target = target[: -len("README.md")] + "index.md"

    return f"{target}{fragment}"


def rewrite_links(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, target, fragment, suffix = match.groups()
        return f"{prefix}{rewrite_link_target(target)}{fragment or ''}{suffix}"

    return LINK_RE.sub(replace, line)


def transform_markdown(content: str) -> str:
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    in_fence = False
    fence_marker = ""
    active_section = ""

    for line in lines:
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif line.lstrip().startswith(fence_marker):
                in_fence = False
                fence_marker = ""

        if not in_fence:
            line = rewrite_links(line)

            heading_match = TARGET_HEADING_RE.match(line.rstrip("\n"))
            if heading_match:
                if active_section:
                    output.append("</div>\n")
                style = SECTION_STYLES[heading_match.group(2)]
                output.append(f'<div class="doc-section doc-section--{style}" markdown="1">\n')
                output.append(line)
                active_section = style
                continue

            if active_section and ANY_H1_H2_RE.match(line):
                output.append("</div>\n")
                active_section = ""

        output.append(line)

    if active_section:
        output.append("</div>\n")

    return "".join(output)


def copy_markdown(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    内容 = src.read_text(encoding="utf-8")
    dest.write_text(transform_markdown(内容), encoding="utf-8")


def main() -> None:
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)

    source_dirs: set[Path] = set()
    entry_dirs: set[Path] = set()

    for path in ROOT.rglob("*.md"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        relative = path.relative_to(ROOT)
        source_dirs.add(relative.parent)

        if path.name == "README.md":
            target = SOURCE / relative.with_name("index.md")
            entry_dirs.add(relative.parent)
        elif path.name == "index.md":
            target = SOURCE / relative
            entry_dirs.add(relative.parent)
        else:
            target = SOURCE / relative

        copy_markdown(path, target)

    for directory in sorted(source_dirs, key=lambda p: (len(p.parts), str(p))):
        if directory in entry_dirs:
            continue

        children = []
        source_directory = ROOT / directory
        for child in sorted(source_directory.iterdir(), key=lambda p: (p.is_file(), p.name)):
            if child.name.startswith(".") or child.name in IGNORE_DIRS:
                continue
            if child.is_dir():
                if any(
                    not any(part in IGNORE_DIRS for part in nested.parts)
                    and nested.suffix == ".md"
                    for nested in child.rglob("*")
                ):
                    children.append((child.name, f"./{child.name}/index.md"))
                continue
            if child.suffix == ".md":
                children.append((child.stem, f"./{child.name}"))

        if not children:
            continue

        title = directory.name if directory.parts else "文档"
        lines = [f"# {title}\n\n", "本目录中的页面如下。\n\n"]
        for name, link in children:
            lines.append(f"- [{name}]({link})\n")

        index_target = SOURCE / directory / "index.md"
        index_target.parent.mkdir(parents=True, exist_ok=True)
        index_target.write_text("".join(lines), encoding="utf-8")

    样式源 = ROOT / "stylesheets" / "extra.css"
    if 样式源.exists():
        样式目标 = SOURCE / "stylesheets" / "extra.css"
        样式目标.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(样式源, 样式目标)


if __name__ == "__main__":
    main()
