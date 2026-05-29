#!/usr/bin/env python3
from __future__ import annotations

import json
from html import escape as html_escape
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".mkdocs-src"
VITEPRESS_DIR = SOURCE / ".vitepress"
IGNORE_DIRS = {
    ".git",
    ".github",
    ".mkdocs-src",
    ".mkdocs-site",
    ".vitepress",
    "node_modules",
    "site",
}

HOME_FRONTMATTER = """---
layout: home
hero:
  name: KrKr2 教程文档
  text: 面向 C++ 基础开发者的完整学习路径
  tagline: P 系列前置技术，M 系列项目实战，保留原始 Markdown 结构并直接部署到 VitePress。
  actions:
    - theme: brand
      text: 从 P01 开始
      link: /P01-现代CMake与构建工具链/
    - theme: alt
      text: 查看项目模块
      link: /M01-项目导览与环境搭建/
---

"""

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
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})")
SORT_NAME_RE = re.compile(r"^((?:[PM])?\d+)[-_](.+)$")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_:-]*\b[^>]*>")
GITHUB_EXPR_RE = re.compile(r"\$\{\{([^}]+)\}\}")


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


def escape_xml_like_tags(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith("<details") or stripped.startswith("</details"):
        return line
    if stripped.startswith("<summary") or stripped.startswith("</summary"):
        return line

    parts = line.split("`")
    for index in range(0, len(parts), 2):
        parts[index] = HTML_TAG_RE.sub(
            lambda match: html_escape(match.group(0)),
            parts[index],
        )
    line = "`".join(parts)
    return GITHUB_EXPR_RE.sub(
        lambda match: f"&#36;&#123;&#123;{html_escape(match.group(1).strip())}&#125;&#125;",
        line,
    )


def humanize_name(name: str) -> str:
    match = SORT_NAME_RE.match(name)
    if match:
        return f"{match.group(1)} · {match.group(2)}"

    return name.replace("_", " ")


def sort_name(name: str) -> tuple[int, int, int, str]:
    match = SORT_NAME_RE.match(name)
    if match:
        prefix = match.group(1)
        number = prefix[1:] if prefix[:1] in {"P", "M"} else prefix
        series = prefix[:1]
        series_order = 0 if series == "P" else 1 if series == "M" else 2
        return (0, series_order, int(number), match.group(2).casefold())

    if name.isdigit():
        return (1, 0, int(name), "")

    return (2, 0, 0, name.casefold())


def entry_sort_key(path: Path) -> tuple[int, int, int, str]:
    name = path.stem if path.is_file() else path.name
    kind_order = 1 if path.is_file() else 0
    return (kind_order, *sort_name(name))

def route_for_relative(relative: Path) -> str:
    if relative.name == "index.md":
        if relative.parent == Path("."):
            return "/"
        return f"/{relative.parent.as_posix()}/"

    return f"/{relative.with_suffix('').as_posix()}"


def build_nav() -> list[dict[str, object]]:
    nav: list[dict[str, object]] = []
    pages = (
        ("首页", Path("index.md")),
        ("教程体系PRD", Path("教程体系PRD.md")),
        ("更新日志", Path("更新日志.md")),
    )

    for text, relative in pages:
        if (SOURCE / relative).exists():
            nav.append({"text": text, "link": route_for_relative(relative)})

    front_matter_modules: list[dict[str, object]] = []
    project_modules: list[dict[str, object]] = []
    for child in sorted(SOURCE.iterdir(), key=entry_sort_key):
        if not child.is_dir():
            continue

        item = {
            "text": humanize_name(child.name),
            "link": route_for_relative(Path(child.name) / "index.md"),
        }
        if child.name.startswith("P"):
            front_matter_modules.append(item)
        elif child.name.startswith("M"):
            project_modules.append(item)

    if front_matter_modules:
        nav.append({"text": "前置技术模块", "items": front_matter_modules})
    if project_modules:
        nav.append({"text": "项目模块", "items": project_modules})

    return nav


def has_markdown_descendants(path: Path) -> bool:
    return any(nested.is_file() and nested.suffix == ".md" for nested in path.rglob("*.md"))


def build_sidebar_entries(directory: Path, relative: Path, include_index: bool) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    if include_index and (directory / "index.md").exists():
        entries.append(
            {
                "text": "概览",
                "link": route_for_relative(relative / "index.md"),
            }
        )

    for child in sorted(directory.iterdir(), key=entry_sort_key):
        if child.name.startswith(".") or child.name in IGNORE_DIRS:
            continue

        if child.is_dir():
            if not has_markdown_descendants(child):
                continue

            child_relative = relative / child.name
            child_items = build_sidebar_entries(child, child_relative, False)
            item: dict[str, object] = {
                "text": humanize_name(child.name),
                "link": route_for_relative(child_relative / "index.md"),
            }
            if child_items:
                item["collapsed"] = False
                item["items"] = child_items
            entries.append(item)
            continue

        if child.suffix == ".md" and child.name != "index.md":
            entries.append(
                {
                    "text": humanize_name(child.stem),
                    "link": route_for_relative(relative / child.name),
                }
            )

    return entries


def build_sidebar() -> dict[str, list[dict[str, object]]]:
    sidebar: dict[str, list[dict[str, object]]] = {}

    for child in sorted(SOURCE.iterdir(), key=entry_sort_key):
        if not child.is_dir():
            continue
        if child.name.startswith("P") or child.name.startswith("M"):
            sidebar[f"/{child.name}/"] = build_sidebar_entries(
                child,
                Path(child.name),
                True,
            )

    return sidebar


def write_vitepress_config() -> None:
    vitepress_dir = VITEPRESS_DIR
    vitepress_dir.mkdir(parents=True, exist_ok=True)
    theme_dir = vitepress_dir / "theme"
    theme_dir.mkdir(parents=True, exist_ok=True)

    nav_json = json.dumps(build_nav(), ensure_ascii=False, indent=2)
    sidebar_json = json.dumps(build_sidebar(), ensure_ascii=False, indent=2)
    config = f"""import {{ defineConfig }} from 'vitepress'

const nav = {nav_json}
const sidebar = {sidebar_json}

export default defineConfig({{
  lang: 'zh-CN',
  title: 'KrKr2 教程文档',
  description: 'KrKr2 模拟器的中文教程与项目文档站点。',
  base: process.env.VITEPRESS_BASE ?? '/',
  cleanUrls: true,
  lastUpdated: false,
  ignoreDeadLinks: true,
  themeConfig: {{
    siteTitle: 'KrKr2 教程文档',
    nav,
    sidebar
  }}
}})
"""
    (vitepress_dir / "config.mts").write_text(config, encoding="utf-8")

    theme_index = """import Theme from 'vitepress/theme'
import './custom.css'

export default Theme
"""
    (theme_dir / "index.ts").write_text(theme_index, encoding="utf-8")

    css_source = ROOT / "stylesheets" / "extra.css"
    if css_source.exists():
        shutil.copy2(css_source, theme_dir / "custom.css")


def transform_markdown(content: str) -> str:
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    in_fence = False
    fence_marker = ""

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
            line = escape_xml_like_tags(line)
            line = rewrite_links(line)

        output.append(line)

    return "".join(output)


def copy_markdown(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    内容 = src.read_text(encoding="utf-8")
    if src.name == "README.md" and src.parent == ROOT:
        内容 = HOME_FRONTMATTER + 内容
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

    for directory in sorted(source_dirs, key=lambda p: (len(p.parts), sort_name(p.name))):
        if directory in entry_dirs:
            continue

        children = []
        source_directory = ROOT / directory
        for child in sorted(source_directory.iterdir(), key=entry_sort_key):
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

        title = humanize_name(directory.name) if directory.parts else "文档"
        lines = [f"# {title}\n\n", "本目录中的页面如下，已按编号排序。\n\n"]
        for name, link in children:
            lines.append(f"- [{humanize_name(name)}]({link})\n")

        index_target = SOURCE / directory / "index.md"
        index_target.parent.mkdir(parents=True, exist_ok=True)
        index_target.write_text("".join(lines), encoding="utf-8")

    样式源 = ROOT / "stylesheets" / "extra.css"
    if 样式源.exists():
        样式目标 = SOURCE / "stylesheets" / "extra.css"
        样式目标.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(样式源, 样式目标)

    write_vitepress_config()


if __name__ == "__main__":
    main()
