#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建产物自检：检查每个页面有没有样式表、有没有一级标题，以及所有内部链接是否有效。

用法：
    python check.py

加完内容或改完 build.py 之后跑一下，比在浏览器里一页页点省事。
"""

import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

OUT = Path(__file__).resolve().parent / "public"

if not OUT.exists():
    sys.exit("还没有构建产物，先运行：python build.py")


def main() -> int:
    errors, pages, links = [], 0, 0

    for f in sorted(OUT.rglob("*.html")):
        pages += 1
        txt = f.read_text(encoding="utf-8")
        rel = f.relative_to(OUT).as_posix()

        if 'href="/style.css"' not in txt:
            errors.append(f"{rel}: 缺少样式表引用")
        if "<h1" not in txt:
            errors.append(f"{rel}: 没有一级标题")

        for url in re.findall(r'(?:href|src)="(/[^"#]*)"', txt):
            links += 1
            target = OUT / url.lstrip("/")
            if url.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{rel}: 死链 {url}")

    print(f"页面 {pages} 个，内部链接 {links} 条")

    if errors:
        print(f"\n发现 {len(errors)} 个问题：")
        for e in errors:
            print("  ✗", e)
        return 1

    print("✓ 全部链接有效，每页都有样式表和一级标题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
