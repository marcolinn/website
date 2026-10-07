#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「手工网页」书籍的详情页从原稿目录同步进站点。

这些书的详情页不是 build.py 用 Markdown 生成的，而是单独做好的独立网页，
原稿在站点仓库之外。Cloudflare 的构建机看不到原稿目录，所以要把网页真正
用到的文件复制进 static/books/<slug>/，跟着仓库一起提交。

对应的 Markdown 只起「挂名」作用（content/books/<slug>.md 里写了
custom_page: true），提供书单页用的书名、作者、评分、状态等字段，
每一本都要和这里的 slug 对得上。

目前有两本：

  中国租界通史   D:\\Data\\Onedrive\\DSH\\Book\\中国租界通史_网页
                 取 index.html、chapters.html、assets/（39 张图）
                 原稿共 177 个文件 14.7 MB，其余（assets_raw/ 93 张原图、
                 chapters/ 正文素材与构建脚本、几个 .py 和 README.md）不进站点。

  青龍造         D:\\Data\\Onedrive\\DSH\\Book\\青龍造\\site
                 取 index.html、images/（17 张图，其中 title.jpg 未被页面引用）
                 原稿共 60 个文件 7.1 MB，extract/、summaries/、tools/ 不进站点。

原稿改动之后重新跑一次：

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

BOOKS = [
    {
        "slug": "zhongguo-zujie-tongshi",
        "source": Path(r"D:\Data\Onedrive\DSH\Book\中国租界通史_网页"),
        "files": ["index.html", "chapters.html"],
        "dirs": ["assets"],
    },
    {
        "slug": "qinglong-zao",
        "source": Path(r"D:\Data\Onedrive\DSH\Book\青龍造\site"),
        "files": ["index.html"],
        "dirs": ["images"],
    },
]


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


def referenced_assets(book: dict) -> set:
    """从该书的 HTML 里抽出所有指向本地资源目录的引用（src= 和 href= 都算）。

    只保留以 dirs 里某个目录名开头的路径，这样页内锚点（#top）、外链、
    以及别的相对路径都不会混进来。用来核对原稿是不是自洽的。
    """
    prefixes = tuple(d + "/" for d in book["dirs"])
    found = set()
    for name in book["files"]:
        text = (book["source"] / name).read_text(encoding="utf-8")
        found |= set(re.findall(r'(?:href|src)="([^"?#]+)"', text))
    return {r for r in found if r.startswith(prefixes)}


def sync_one(book: dict) -> bool:
    """同步一本书。返回 True 表示成功（含「这台机器上没有原稿，跳过」）。"""
    slug = book["slug"]
    source = book["source"]
    dest = ROOT / "static" / "books" / slug

    print(f"── {slug}")

    if not source.exists():
        print(f"   找不到原稿目录：{source}")
        print("   这台机器上没有它就不用同步 —— static/ 里已经有一份提交进 git 的拷贝。")
        print()
        return True

    for name in book["files"] + book["dirs"]:
        if not (source / name).exists():
            print(f"   原稿里缺少 {name}，先把它生成出来再同步。")
            print()
            return False

    # 先核对：页面引用的图在原稿里都在
    refs = referenced_assets(book)
    missing = sorted(r for r in refs if not (source / r).exists())
    if missing:
        print(f"   原稿引用了 {len(missing)} 个不存在的文件：")
        for m in missing[:10]:
            print("     ", m)
        print()
        return False

    # 再同步。先清空目标目录，免得原稿删掉的图在站点里留下来
    clean_dir(dest)
    dest.mkdir(parents=True, exist_ok=True)

    total = 0
    for name in book["files"]:
        shutil.copy2(source / name, dest / name)
        total += 1
    for name in book["dirs"]:
        shutil.copytree(source / name, dest / name, dirs_exist_ok=True)
        total += sum(1 for _ in (dest / name).rglob("*") if _.is_file())

    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"   {len(book['files'])} 个页面 + {len(book['dirs'])} 个目录，"
          f"共 {total} 个文件，{size / 1024 / 1024:.1f} MB")
    print(f"   ✓ → {dest}")
    print()
    return True


def main() -> int:
    print(f"同步 {len(BOOKS)} 本手工网页书籍\n")
    ok = all(sync_one(b) for b in BOOKS)
    if not ok:
        print("有书没同步成功，上面有原因。")
        return 1
    print("全部同步完成。接下来：python build.py && python check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
