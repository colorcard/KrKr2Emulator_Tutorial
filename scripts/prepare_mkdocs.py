#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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


def collect_series_modules() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    front_matter_modules: list[tuple[str, str]] = []
    project_modules: list[tuple[str, str]] = []

    for child in sorted(ROOT.iterdir(), key=entry_sort_key):
        if not child.is_dir() or child.name in IGNORE_DIRS:
            continue

        item = (humanize_name(child.name), f"./{child.name}/")
        if child.name.startswith("P"):
            front_matter_modules.append(item)
        elif child.name.startswith("M"):
            project_modules.append(item)

    return front_matter_modules, project_modules


def build_homepage_content() -> str:
    front_matter_modules, project_modules = collect_series_modules()

    def render_module_cards(items: list[tuple[str, str]], prefix: str) -> str:
        cards: list[str] = []
        for title, link in items:
            code = title.split(" · ", 1)[0]
            label = "前置技术" if prefix == "P" else "项目模块"
            cards.append(
                f'<a class="home-module-card" href="{link}">'
                f'<span class="home-module-code">{code}</span>'
                f"<strong>{title}</strong>"
                f"<em>{label}</em>"
                f"</a>"
            )
        return "\n".join(cards)

    def render_route(items: list[tuple[str, str]]) -> str:
        route: list[str] = []
        for index, (title, _) in enumerate(items):
            route.append(f"<span>{title.split(' · ', 1)[0]}</span>")
            if index != len(items) - 1:
                route.append("<i>→</i>")
        return "\n".join(route)

    p_cards = render_module_cards(front_matter_modules, "P")
    m_cards = render_module_cards(project_modules, "M")
    p_route = render_route(front_matter_modules)
    m_route = render_route(project_modules)

    return f"""---
layout: home
hero:
  name: KrKr2 教程文档
  text: 面向 C++ 基础开发者的完整学习路径
  tagline: 站点把 README 的信息结构重写成更适合进入页的“首屏 + 卡片 + 路线 + 模块墙”，并直接部署到 VitePress。
  actions:
    - theme: brand
      text: 从 P01 开始
      link: /P01-现代CMake与构建工具链/
    - theme: alt
      text: 查看学习路线
      link: /#推荐学习路线
    - theme: alt
      text: 教程体系PRD
      link: /教程体系PRD
features:
  - title: 12 个前置技术模块
    details: 从构建工具链、图形与音视频，到编译原理、逆向工程和现代 UI。
  - title: 13 个项目模块
    details: 按子系统拆解 KrKr2，覆盖构建、渲染、音频、视频、脚本、插件与 CI/CD。
  - title: 在线部署
    details: GitHub Actions 自动构建，GitHub Pages 在线预览。
---

# 在线预览

> 这里不是简单的目录页，而是把 README 中的模块索引、学习路线和项目说明重新整理成一个“先看什么、怎么学、点哪里”的入口页。

<div class="home-metrics">
  <div class="home-metric">
    <strong>{len(front_matter_modules)}</strong>
    <span>P 系列</span>
  </div>
  <div class="home-metric">
    <strong>{len(project_modules)}</strong>
    <span>M 系列</span>
  </div>
  <div class="home-metric">
    <strong>{len(front_matter_modules) + len(project_modules)}</strong>
    <span>教程模块</span>
  </div>
  <div class="home-metric">
    <strong>GitHub Pages</strong>
    <span>自动部署</span>
  </div>
</div>

<div class="home-grid home-grid--preview">
  <div class="home-panel home-panel--accent">
    <h3>站点入口</h3>
    <p>VitePress 负责页面框架，GitHub Actions 负责构建，GitHub Pages 负责发布。</p>
  </div>
  <div class="home-panel">
    <h3>阅读顺序</h3>
    <p>P 系列先打基础，M 系列后看项目；两条线都按编号排序，避免目录跳读。</p>
  </div>
  <div class="home-panel">
    <h3>首页风格</h3>
    <p>参考 README 的信息结构，但把表格改成卡片、路线和模块墙，让入口更像产品首页。</p>
  </div>
  <div class="home-panel">
    <h3>源码入口</h3>
    <p>首页由 `scripts/prepare_mkdocs.py` 生成，样式来自 `stylesheets/extra.css`。</p>
  </div>
</div>

## 文档规划

<div class="home-grid home-grid--plan">
  <a class="home-panel home-panel--accent" href="./教程体系PRD/">
    <h3>教程体系 PRD</h3>
    <p>先看完整规划，再进入模块学习，避免走回头路。</p>
  </a>
  <a class="home-panel" href="./更新日志/">
    <h3>更新日志</h3>
    <p>看最近一次整理了什么，方便追踪站点和内容变化。</p>
  </a>
  <a class="home-panel" href="./P01-现代CMake与构建工具链/">
    <h3>从 P01 开始</h3>
    <p>从构建工具链起步，建立项目阅读和编译的基本功。</p>
  </a>
  <a class="home-panel" href="./M01-项目导览与环境搭建/">
    <h3>进入项目模块</h3>
    <p>直接看 KrKr2 的结构、入口、平台和实战路径。</p>
  </a>
</div>

## 教程地图

### P 系列

<div class="home-module-grid">
{p_cards}
</div>

### M 系列

<div class="home-module-grid">
{m_cards}
</div>

## 推荐学习路线

<div class="home-route-block">
  <div class="home-route-title">基础路线</div>
  <div class="home-route">{p_route}</div>
</div>

<div class="home-route-block">
  <div class="home-route-title">项目路线</div>
  <div class="home-route">{m_route}</div>
</div>

## 目标读者

- 具备 C++ 基础（语法、STL、面向对象）。
- 没有跨平台项目、图形渲染、音视频、逆向工程经验。
- 希望完全掌握本项目，能修 Bug、加功能、开发插件、替换 UI 框架。

## 设计说明

- 首页参考 README 的信息结构，但把表格入口改成了更适合首屏阅读的卡片与路线条。
- P 系列始终在前，M 系列始终在后，导航和入口保持一致。
- 视觉风格采用更强的留白、卡片、分层背景和中文字体栈，避免默认文档站的平铺感。
"""


def write_vitepress_config() -> None:
    vitepress_dir = VITEPRESS_DIR
    vitepress_dir.mkdir(parents=True, exist_ok=True)
    theme_dir = vitepress_dir / "theme"
    theme_dir.mkdir(parents=True, exist_ok=True)

    if (ROOT / "CNAME").exists():
        vitepress_base = "/"
    else:
        vitepress_base = os.environ.get("VITEPRESS_BASE", "/")

    nav_json = json.dumps(build_nav(), ensure_ascii=False, indent=2)
    sidebar_json = json.dumps(build_sidebar(), ensure_ascii=False, indent=2)
    config = f"""import {{ defineConfig }} from 'vitepress'

const nav = {nav_json}
const sidebar = {sidebar_json}

export default defineConfig({{
  lang: 'zh-CN',
  title: 'KrKr2 教程文档',
  description: 'KrKr2 模拟器的中文教程与项目文档站点。',
  base: {json.dumps(vitepress_base)},
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
    if src.name == "README.md" and src.parent == ROOT:
        内容 = build_homepage_content()
        dest.write_text(内容, encoding="utf-8")
        return
    else:
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

    cname_source = ROOT / "CNAME"
    if cname_source.exists():
        public_dir = SOURCE / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cname_source, public_dir / "CNAME")

    write_vitepress_config()


if __name__ == "__main__":
    main()
