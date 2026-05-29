#!/usr/bin/env python3
from __future__ import annotations

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


def should_skip_dir(path: Path) -> bool:
    return path.name in IGNORE_DIRS


def copy_markdown(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    内容 = src.read_text(encoding="utf-8")
    内容 = 内容.replace("README.md", "index.md")
    dest.write_text(内容, encoding="utf-8")


def main() -> None:
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)

    for path in ROOT.rglob("*.md"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        relative = path.relative_to(ROOT)
        target = SOURCE / relative
        copy_markdown(path, target)

        if path.name == "README.md":
            index_target = target.with_name("index.md")
            copy_markdown(path, index_target)


if __name__ == "__main__":
    main()
