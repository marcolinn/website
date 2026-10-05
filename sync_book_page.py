#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把《中国租界通史》介绍页从原稿目录同步进站点。

原稿是单独做的一套独立网页，在站点仓库之外：

    D:\\Data\\Onedrive\\DSH\\Book\\中国租界通史_网页

它里面有 177 个文件、14.7 MB，但网页真正用到的只有三个：

    index.html      介绍页（单文件，样式与脚本都内联）
    chapters.html   分章导读（16 篇）
    assets/         页面用图 39 张，约 1.9 MB

其余（assets_raw/ 93 张原图 11 MB、chapters/ 正文素材与构建脚本 1.4 MB、
几个 .py 和 README.md）都不进站点。

同步之后那三个要提交进 git —— Cloudflare 的构建机看不到原稿目录，
它只认仓库里的文件。

原稿改动之后重新跑一次这个脚本即可：

    python sync_book_page.py
    python build.py
    python check.py
"""

import re
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"D:\Data\Onedrive\DSH\Book\中国租界通史_网页")
DEST = ROOT / "static" / "books" / "zhongguo-zujie-tongshi"

FILES = ["index.html", "chapters.html"]
DIRS = ["assets"]


def clean_dir(p: Path):
    """删掉一棵目录树。

    项目在 OneDrive 里，同步进程经常锁住文件夹导致 rmtree 抛 PermissionError，
    所以失败后退回逐个文件删 —— 跟 build.py 里的 clean_out() 是同一套办法。
    """
    if not p.exists():
        return
    try:
        shutil.rmtree(p)
        return
    except OSError:
        pass
    for item in sorted(p.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        try:
            item.rmdir() if item.is_dir() else item.unlink()
        except OSError:
            pass
    try:
        p.rmdir()
    except OSError:
        pass


def referenced_assets() -> set:
    """从两个 HTML 里抽出所有 assets/xxx 引用，用来核对原稿是不是自洽的。"""
    found = set()
    for name in FILES:
        text = (SOURCE / name).read_text(encoding="utf-8")
        found |= set(re.findall(r'(?:href|src)="(assets/[^"?#]+)"', text))
    return found


def main() -> int:
    if not SOURCE.exists():
        print(f"找不到原稿目录：{SOURCE}")
        print("这台机器上没有它的话，就不用同步 —— static/ 里已经有一份提交进 git 的拷贝。")
        return 1

    for name in FILES + DIRS:
        if not (SOURCE / name).exists():
            print(f"原稿里缺少 {name}，先把它生成出来再同步。")
            return 1

    # 先核对：页面引用的图在原稿里都在
    refs = referenced_assets()
    missing = sorted(r for r in refs if not (SOURCE / r).exists())
    if missing:
        print(f"原稿引用了 {len(missing)} 个不存在的图：")
        for m in missing[:10]:
            print("   ", m)
        return 1
    print(f"原稿自洽：{len(refs)} 个图片引用全部存在")

    # 再同步。先清空目标目录，免得原稿删掉的图在站点里留下来
    clean_dir(DEST)
    DEST.mkdir(parents=True, exist_ok=True)

    total = 0
    for name in FILES:
        shutil.copy2(SOURCE / name, DEST / name)
        total += 1
    for name in DIRS:
        shutil.copytree(SOURCE / name, DEST / name, dirs_exist_ok=True)
        total += sum(1 for _ in (DEST / name).rglob("*") if _.is_file())

    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"✓ 同步完成 → {DEST}")
    print(f"  {len(FILES)} 个页面 + {len(DIRS)} 个目录，共 {total} 个文件，{size / 1024 / 1024:.1f} MB")
    print("  接下来：python build.py && python check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
