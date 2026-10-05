#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建产物自检：每页有没有样式表和一级标题，以及所有内部链接是否有效。

用法：
    python check.py

返回 0 = 一切正常，返回 1 = 有死链或缺东西。
Cloudflare 的构建命令是 `python3 build.py && python3 check.py`，
所以这里报错会让整次部署失败、保留上一个能用的版本 —— 坏页面不会上线。
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

LINK_RE = re.compile(r'(?:href|src)="([^"]*)"')

# 这些不是站内文件，不用查
EXTERNAL = ("#", "http://", "https://", "//", "mailto:", "tel:", "data:", "javascript:")


def resolve(url: str, page: Path):
    """把一个链接解析成 public/ 下的实际路径；不需要检查的返回 None。"""
    url = url.split("#", 1)[0].split("?", 1)[0].strip()
    if not url or url.startswith(EXTERNAL):
        return None
    target = OUT / url.lstrip("/") if url.startswith("/") else page.parent / url
    if url.endswith("/"):
        target = target / "index.html"
    return target


def main() -> int:
    errors, pages, links = [], 0, 0

    for f in sorted(OUT.rglob("*.html")):
        pages += 1
        txt = f.read_text(encoding="utf-8")
        rel = f.relative_to(OUT).as_posix()

        # build.py 模板生成的页面都有 site-head；手工做的独立页面（比如
        # 中国租界通史那一套）样式是内联的，不要求引 /style.css。
        if 'class="site-head"' in txt and 'href="/style.css"' not in txt:
            errors.append(f"{rel}: 缺少样式表引用")
        if "<h1" not in txt:
            errors.append(f"{rel}: 没有一级标题")

        for url in LINK_RE.findall(txt):
            target = resolve(url, f)
            if target is None:
                continue
            links += 1
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
