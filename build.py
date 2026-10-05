#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简静态站点生成器 —— 零第三方依赖，只需 Python 3.8+。

用法：
    python build.py            构建到 public/
    python build.py --serve    构建并启动本地预览 http://localhost:8000

新增内容：在 content/ 下新建 .md 文件，重新运行即可。
"""

import argparse
import html
import re
import shutil
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path

# Windows 控制台默认是 GBK，显式切成 UTF-8，否则中文和符号输出会直接报错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
PHOTOS = ROOT / "photos"          # 原图放这里，构建时压缩进 public/photos/
OUT = ROOT / "public"

# ─────────────────────────────────────────────────────────────
#  站点配置 —— 改这里就行
# ─────────────────────────────────────────────────────────────
SITE = {
    "title": "我的书房",
    "tagline": "读过的书，走过的路",
    "author": "Marco",
    "description": "一个记录阅读、旅行与生活的地方。",
    "nav": [
        ("首页", "/"),
        ("读书", "/books/"),
        ("文章", "/blog/"),
        ("旅行", "/travel/"),
        ("照片", "/photos/"),
        ("关于", "/about/"),
    ],
    "footer": "本站使用 Cloudflare Pages 托管",
}

# 读书页按这个顺序展示状态分组
BOOK_STATUS_ORDER = ["在读", "读过", "想读"]


# ─────────────────────────────────────────────────────────────
#  Markdown（够用就好）
# ─────────────────────────────────────────────────────────────

def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1" loading="lazy">', t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def smart_quotes(text: str) -> str:
    """把紧贴汉字的英文直引号换成中文引号 “ ”。

    用一个状态机跟踪"当前是否在引号里"，而不是靠左右字符判断开闭——
    因为像 把"租界"这个概念 这种写法，两个引号后面跟的都是汉字，
    单看右侧会把闭引号也误判成开引号。

    只处理紧挨汉字的引号，两侧都不是汉字的一律原样保留，
    所以代码块里的 "foo" 和网址不受影响。
    在读取 Markdown 时统一转换，这样正文、摘要、标题全都一致。
    """
    out, in_quote = [], False
    cjk = re.compile(r"[\u4e00-\u9fff]")

    for i, ch in enumerate(text):
        if ch != '"':
            out.append(ch)
            continue

        prev_cjk = bool(i and cjk.match(text[i - 1]))
        next_cjk = bool(i + 1 < len(text) and cjk.match(text[i + 1]))

        if prev_cjk and not next_cjk:          # 典型的闭引号
            out.append("”")
            in_quote = False
        elif next_cjk and not prev_cjk:        # 典型的开引号
            out.append("“")
            in_quote = True
        elif prev_cjk and next_cjk:            # 两侧都是汉字，只能看状态
            out.append("”" if in_quote else "“")
            in_quote = not in_quote
        else:                                  # 两侧都不是汉字，别乱动
            out.append(ch)

    return "".join(out)


def md(text: str) -> str:
    lines = text.split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush()
            i += 1
            continue

        if s.startswith("```"):
            flush()
            lang = s[3:].strip()
            buf, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            lv = len(m.group(1))
            out.append(f"<h{lv}>{_inline(m.group(2))}</h{lv}>")
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            flush()
            out.append("<hr>")
            i += 1
            continue

        if s.startswith(">"):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + md("\n".join(buf)) + "</blockquote>")
            continue

        if re.match(r"^[-*+]\s+", s):
            flush()
            items = []
            while i < len(lines) and re.match(r"^[-*+]\s+", lines[i].strip()):
                items.append(_inline(re.sub(r"^[-*+]\s+", "", lines[i].strip())))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", s):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(_inline(re.sub(r"^\d+\.\s+", "", lines[i].strip())))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue

        para.append(s)
        i += 1

    flush()
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────
#  内容读取
# ─────────────────────────────────────────────────────────────

def split_front(raw: str):
    """返回 (meta_dict, body)。front matter 用 --- 包住，每行 key: value。"""
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    meta = {}
    for line in raw[3:end].strip().split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            v = v.strip("'\"")
        meta[k] = v
    return meta, raw[end + 4:].strip()


def read_docs(folder: Path):
    docs = []
    if not folder.exists():
        return docs
    for p in sorted(folder.glob("*.md")):
        meta, body = split_front(smart_quotes(p.read_text(encoding="utf-8")))
        meta["slug"] = p.stem
        meta["body"] = body
        meta["html"] = md(body)
        meta["date"] = str(meta.get("date", "1970-01-01"))
        docs.append(meta)
    docs.sort(key=lambda d: d["date"], reverse=True)
    return docs


def stars(rating) -> str:
    """评分转成星标；0 或无效值返回空串（表示尚未评分）。"""
    try:
        n = int(float(rating))
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    n = min(5, n)
    dim = f'<span class="dim">{"☆" * (5 - n)}</span>' if n < 5 else ""
    return f'<span class="stars" aria-label="{n} 星">{"★" * n}{dim}</span>'


def fmt_date(s: str) -> str:
    for f in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            d = datetime.strptime(s, f)
            return f"{d.year} 年 {d.month} 月 {d.day} 日"
        except ValueError:
            continue
    return s


# ─────────────────────────────────────────────────────────────
#  模板
# ─────────────────────────────────────────────────────────────

def nav_html(current: str) -> str:
    items = []
    for label, href in SITE["nav"]:
        cls = ' class="active"' if href == current else ""
        items.append(f'<a href="{href}"{cls}>{label}</a>')
    return "\n      ".join(items)


def page(title: str, current: str, body: str, desc: str = "", depth: int = 0) -> str:
    t = f"{title} · {SITE['title']}" if title else SITE["title"]
    d = desc or SITE["description"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(t)}</title>
<meta name="description" content="{html.escape(d)}">
<link rel="stylesheet" href="/style.css">
</head>
<body>
  <header class="site-head">
    <div class="wrap head-inner">
      <a class="brand" href="/">
        <span class="brand-mark">書</span>
        <span class="brand-text">
          <strong>{html.escape(SITE['title'])}</strong>
          <em>{html.escape(SITE['tagline'])}</em>
        </span>
      </a>
      <nav class="site-nav">
      {nav_html(current)}
      </nav>
    </div>
  </header>

  <main class="wrap">
{body}
  </main>

  <footer class="site-foot">
    <div class="wrap">
      <p>© {date.today().year} {html.escape(SITE['author'])}　·　{html.escape(SITE['footer'])}</p>
    </div>
  </footer>
</body>
</html>
"""


def card(title, href, meta_line, excerpt, extra=""):
    return f"""      <a class="card" href="{href}">
        <div class="card-body">
          <h3>{html.escape(title)}</h3>
          <p class="meta">{meta_line}</p>
          {f'<p class="excerpt">{html.escape(excerpt)}</p>' if excerpt else ''}
          {extra}
        </div>
      </a>"""


# ─────────────────────────────────────────────────────────────
#  页面构建
# ─────────────────────────────────────────────────────────────

def clean_out():
    """清空 public/。

    项目放在 OneDrive 目录里时，同步进程经常锁住文件夹，直接 rmtree 会抛
    PermissionError。所以：先整体删（带重试）→ 不行就逐个文件从深到浅删
    → 都不行才放弃，改为原地覆盖。
    """
    if not OUT.exists():
        return

    for attempt in range(3):
        try:
            shutil.rmtree(OUT)
            return
        except OSError:
            time.sleep(0.3 * (attempt + 1))

    # rmtree 失败（OneDrive 经常锁住文件夹）：从深到浅逐个删。
    # 删两轮 —— OneDrive 删完文件后目录枚举会短暂返回幽灵条目，第二轮会清掉。
    for _ in range(2):
        for p in sorted(OUT.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            try:
                p.rmdir() if p.is_dir() else p.unlink()
            except OSError:
                pass
        time.sleep(0.4)

    # 关键：文件都能删掉，只有目录本身可能因为 OneDrive 持有句柄而删不掉。
    # 空目录留下来无害（构建时会直接覆盖内容），所以只在还有文件残留时才报警。
    left_files = [p for p in OUT.rglob("*") if p.is_file()]
    if left_files:
        print(f"! public/ 里有 {len(left_files)} 个文件删不掉（多半是 OneDrive 正在同步）：")
        for p in left_files[:5]:
            print("   ", p.relative_to(OUT).as_posix())
        if len(left_files) > 5:
            print(f"    …… 另有 {len(left_files) - 5} 个")
        print("  过期的页面会继续留在站点里。暂停 OneDrive 同步后再跑一次 python build.py 即可。")


def build():
    books = read_docs(CONTENT / "books")
    posts = read_docs(CONTENT / "blog")
    trips = read_docs(CONTENT / "travel")
    about_meta, about_body = split_front(smart_quotes((CONTENT / "about.md").read_text(encoding="utf-8"))) \
        if (CONTENT / "about.md").exists() else ({}, "还没写。")

    clean_out()
    OUT.mkdir(parents=True, exist_ok=True)

    def write_page(rel: str, content: str):
        p = OUT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # ── 首页 ──
    recent_books = books[:4]
    recent_posts = posts[:3]
    book_cards = "\n".join(
        card(
            b.get("title", b["slug"]),
            f"/books/{b['slug']}/",
            f"{html.escape(b.get('author',''))}　{stars(b.get('rating',''))}",
            (b.get("summary") or b["body"][:70]).replace("\n", " "),
        ) for b in recent_books
    ) or '      <p class="empty">还没有添加书籍。在 content/books/ 下新建 .md 文件即可。</p>'
    post_cards = "\n".join(
        card(
            p.get("title", p["slug"]),
            f"/blog/{p['slug']}/",
            fmt_date(p["date"]),
            (p.get("summary") or p["body"][:70]).replace("\n", " "),
        ) for p in recent_posts
    ) or '      <p class="empty">还没有文章。</p>'

    write_page("index.html", page("", "/", f"""    <section class="hero">
      <h1>{html.escape(SITE['tagline'])}</h1>
      <p>{html.escape(SITE['description'])}</p>
      <p class="hero-links">
        <a class="btn" href="/books/">看看书单</a>
        <a class="btn ghost" href="/about/">关于我</a>
      </p>
    </section>

    <section class="block">
      <div class="block-head">
        <h2>最近读的书</h2>
        <a class="more" href="/books/">全部书单 →</a>
      </div>
      <div class="grid">
{book_cards}
      </div>
    </section>

    <section class="block">
      <div class="block-head">
        <h2>最近写的</h2>
        <a class="more" href="/blog/">全部文章 →</a>
      </div>
      <div class="grid">
{post_cards}
      </div>
    </section>"""))

    # ── 读书 ──
    groups = {}
    for b in books:
        groups.setdefault(b.get("status", "读过"), []).append(b)
    order = [s for s in BOOK_STATUS_ORDER if s in groups] + [s for s in groups if s not in BOOK_STATUS_ORDER]

    sections = []
    for st in order:
        rows = []
        for b in sorted(groups[st], key=lambda d: d["date"], reverse=True):
            year = b["date"][:4]
            rows.append(f"""        <a class="book" href="/books/{b['slug']}/">
          <div class="book-main">
            <h3>{html.escape(b.get('title', b['slug']))}</h3>
            <p class="meta">{html.escape(b.get('author',''))}{'　·　' + html.escape(b.get('publisher','')) if b.get('publisher') else ''}　·　{year}</p>
            <p class="excerpt">{html.escape((b.get('summary') or b['body'][:80]).replace(chr(10),' '))}</p>
          </div>
          <div class="book-rate">{stars(b.get('rating',''))}</div>
        </a>""")
        sections.append(f"""    <section class="block">
      <h2 class="rule"><span>{html.escape(st)}</span><small>{len(groups[st])} 本</small></h2>
      <div class="book-list">
{chr(10).join(rows)}
      </div>
    </section>""")

    write_page("books/index.html", page("读书", "/books/",
        '    <h1 class="page-title">读书</h1>\n' +
        ("\n".join(sections) or '    <p class="empty">还没有添加书籍。</p>')))

    # 单本书
    for b in books:
        tags = b.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        tag_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)
        write_page(f"books/{b['slug']}/index.html", page(b.get("title", b["slug"]), "/books/", f"""    <article class="detail">
      <p class="crumb"><a href="/books/">← 返回书单</a></p>
      <h1>{html.escape(b.get('title', b['slug']))}</h1>
      <p class="byline">{html.escape(b.get('author',''))}</p>
      <dl class="facts">
        {('<div><dt>评分</dt><dd>' + stars(b.get('rating')) + '</dd></div>') if stars(b.get('rating')) else ''}
        {'<div><dt>状态</dt><dd>' + html.escape(str(b.get('status',''))) + '</dd></div>' if b.get('status') else ''}
        {'<div><dt>出版社</dt><dd>' + html.escape(str(b.get('publisher',''))) + '</dd></div>' if b.get('publisher') else ''}
        {'<div><dt>读完</dt><dd>' + fmt_date(b['date']) + '</dd></div>' if b.get('date') and b.get('status') != '在读' else ''}
        {'<div><dt>译者</dt><dd>' + html.escape(str(b.get('translator',''))) + '</dd></div>' if b.get('translator') else ''}
      </dl>
      {f'<p class="tags">{tag_html}</p>' if tag_html else ''}
      <div class="prose">
{b['html']}
      </div>
    </article>""", depth=2))

    # ── 文章 ──
    post_cards = "\n".join(
        card(p.get("title", p["slug"]), f"/blog/{p['slug']}/", fmt_date(p["date"]),
             (p.get("summary") or p["body"][:90]).replace("\n", " "))
        for p in posts
    ) or '      <p class="empty">还没有文章。</p>'
    write_page("blog/index.html", page("文章", "/blog/",
        f'    <h1 class="page-title">文章</h1>\n    <div class="grid">\n{post_cards}\n    </div>'))
    for p in posts:
        write_page(f"blog/{p['slug']}/index.html", page(p.get("title", p["slug"]), "/blog/", f"""    <article class="detail">
      <p class="crumb"><a href="/blog/">← 返回文章</a></p>
      <h1>{html.escape(p.get('title', p['slug']))}</h1>
      <p class="byline">{fmt_date(p['date'])}</p>
      <div class="prose">
{p['html']}
      </div>
    </article>""", depth=2))

    # ── 旅行 ──
    trip_cards = "\n".join(
        card(t.get("title", t["slug"]), f"/travel/{t['slug']}/",
             f"{html.escape(str(t.get('place','')))}　·　{fmt_date(t['date'])}",
             (t.get("summary") or t["body"][:90]).replace("\n", " "))
        for t in trips
    ) or '      <p class="empty">还没有旅行记录。在 content/travel/ 下新建 .md 文件即可。</p>'
    write_page("travel/index.html", page("旅行", "/travel/",
        f'    <h1 class="page-title">旅行</h1>\n    <div class="grid">\n{trip_cards}\n    </div>'))
    for t in trips:
        write_page(f"travel/{t['slug']}/index.html", page(t.get("title", t["slug"]), "/travel/", f"""    <article class="detail">
      <p class="crumb"><a href="/travel/">← 返回旅行</a></p>
      <h1>{html.escape(t.get('title', t['slug']))}</h1>
      <p class="byline">{html.escape(str(t.get('place','')))}　·　{fmt_date(t['date'])}</p>
      <div class="prose">
{t['html']}
      </div>
    </article>""", depth=2))

    # ── 照片 ──
    photos = []
    if PHOTOS.exists():
        photos = [p for p in sorted(PHOTOS.rglob("*"))
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")]
    tiles = "\n".join(
        f'      <figure><img src="/photos/{p.relative_to(PHOTOS).as_posix()}" alt="" loading="lazy"></figure>'
        for p in photos
    ) or '      <p class="empty">还没有照片。把图片放进 <code>photos/</code> 文件夹，重新运行 <code>python build.py</code> 即可。</p>'
    write_page("photos/index.html", page("照片", "/photos/",
        f'    <h1 class="page-title">照片</h1>\n    <div class="gallery">\n{tiles}\n    </div>'))

    # ── 关于 ──
    write_page("about/index.html", page("关于", "/about/", f"""    <article class="detail">
      <h1>关于</h1>
      <div class="prose">
{md(about_body)}
      </div>
    </article>"""))

    # ── 静态资源 ──
    if STATIC.exists():
        for item in STATIC.iterdir():
            dest = OUT / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # 照片原图
    if photos:
        for p in photos:
            dest = OUT / "photos" / p.relative_to(PHOTOS)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)

    print(f"✓ 构建完成 → {OUT}")
    print(f"  书籍 {len(books)} 本　文章 {len(posts)} 篇　旅行 {len(trips)} 条　照片 {len(photos)} 张")


def serve():
    import http.server
    import socketserver
    import os
    port = 8000

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(OUT), **kw)

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), Handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"  本地预览：{url}   (Ctrl+C 停止)")
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  已停止。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建静态站点")
    ap.add_argument("--serve", action="store_true", help="构建后启动本地预览")
    args = ap.parse_args()
    build()
    if args.serve:
        serve()
