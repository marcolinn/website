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
import json
import re
import shutil
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

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
    "footer": "本站托管在 Cloudflare",

    # 旅行页的地图。
    #
    # 底图优先用天地图：官方明确允许配合 Leaflet 使用，个人免费额度 1 万次/服务/日，
    # 而且是"具有审图号的地图"的官方来源。去 www.tianditu.gov.cn 注册（需实名）→
    # 申请"个人开发者"→ 建应用，拿到的浏览器端 key（tk）填到下面即可。
    #
    # 留空则退回高德瓦片——不用申请，但那属于非官方用法，只当临时预览用。
    # 注意：无论用哪家，公开的地图都要注明来源与审图号（见 README）。
    "map": {
        "tianditu_key": "7ca93bc423961d2f45a328b92a954f14",
    },
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


def page(title: str, current: str, body: str, desc: str = "", depth: int = 0,
         head: str = "") -> str:
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
{head}</head>
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
#  照片与地图
# ─────────────────────────────────────────────────────────────

PUBLISHED = STATIC / "photos"     # prep_photos.py 的产物，最后会被原样复制进 public/
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAP_HEAD = '<link rel="stylesheet" href="/leaflet/leaflet.css">\n'


def trip_photos(slug: str):
    """某个行程已经发布的照片（大图那批，不含 thumb/ 里的缩略图）。"""
    d = PUBLISHED / slug
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in PHOTO_EXTS)


def photo_url(slug: str, name: str, thumb: bool = False) -> str:
    """照片的网址。文件名可能是中文，所以要百分号编码。"""
    return f"/photos/{quote(slug)}/{'thumb/' if thumb else ''}{quote(name)}"


def gallery_html(slug: str) -> str:
    """行程页底部的照片墙：缩略图点开看原尺寸。"""
    photos = trip_photos(slug)
    if not photos:
        return ""
    figs = "\n".join(
        f'        <figure><a href="{photo_url(slug, p.name)}" target="_blank" rel="noopener">'
        f'<img src="{photo_url(slug, p.name, thumb=True)}" alt="" loading="lazy"></a></figure>'
        for p in photos
    )
    return f"""    <section class="block">
      <h2 class="rule"><span>照片</span><small>{len(photos)} 张</small></h2>
      <div class="gallery">
{figs}
      </div>
    </section>"""


def _as_list(v):
    """front matter 的值可能是字符串，也可能是 `[a, b]` 解析出来的列表。"""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    s = str(v or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [x.strip() for x in s.split(",") if x.strip()]


def _points(t):
    """把坐标解析成 [(纬度, 经度, 地名), ...]；没写或写坏就返回空表。

    一次旅行能标好几个点：lat 和 lng 各写一串逗号分隔的等长数字，
    再用可选的 stops 一行给每个点起名（跟 lat/lng 一一对应）。
    """
    names = _as_list(t.get("stops"))
    out = []
    for i, (a, b) in enumerate(zip(_as_list(t.get("lat")), _as_list(t.get("lng")))):
        try:
            out.append((float(a), float(b), names[i] if i < len(names) else ""))
        except ValueError:
            continue
    return out


def _map_layers():
    """底图图层表。配了天地图 key 就用天地图（矢量底图 + 中文注记两层），否则退回高德瓦片。

    天地图是官方认定的"具有审图号的地图"来源，也明确允许配合 Leaflet 使用；
    高德瓦片直连只是免申请的临时方案，不算官方用法。
    """
    key = str(SITE["map"].get("tianditu_key", "")).strip()
    if key:
        tk = quote(key)
        base = ("https://t{s}.tianditu.gov.cn/DataServer"
                "?T=%s&x={x}&y={y}&l={z}&tk=" + tk)
        return [
            {"u": base % "vec_w", "s": "01234567", "a": "© 天地图", "z": 18},
            {"u": base % "cva_w", "s": "01234567", "a": "", "z": 18},
        ]
    return [{
        "u": "https://webrd0{s}.is.autonavi.com/appmaptile"
             "?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "s": "1234", "a": "© 高德地图", "z": 18,
    }]


def map_section(trips) -> str:
    """旅行页顶部的地图。只有 front matter 里写了 lat/lng 的行程才有标记。"""
    marks = []
    for t in trips:
        pts = _points(t)
        if not pts:
            continue
        photos = trip_photos(t["slug"])
        title = str(t.get("title", t["slug"]))
        cover = photo_url(t["slug"], photos[0].name, thumb=True) if photos else ""
        for lat, lng, stop in pts:
            marks.append({
                "x": lat, "y": lng,
                "t": f"{title} · {stop}" if stop else title,
                "u": f"/travel/{t['slug']}/",
                "d": fmt_date(str(t.get("date", ""))),
                "p": str(t.get("place", "")),
                "s": (t.get("summary") or t.get("body", "")[:70]).replace("\n", " "),
                "i": cover,
            })

    if not marks:
        return """    <p class="empty map-empty">地图还空着。在 <code>content/travel/</code> 的 .md
      里补上 <code>lat</code> 和 <code>lng</code> 两行，重新构建就有标记了；
      一趟走了好几个地方的话，两行各写一串逗号分隔的数字，再用 <code>stops</code> 给每个点起名。</p>"""

    js = """    <div id="trip-map" class="trip-map"></div>
    <script src="/leaflet/leaflet.js"></script>
    <script>
    (function () {
      var places = @PLACES@;
      var el = document.getElementById('trip-map');

      function init() {
        if (!window.L) {
          el.innerHTML = '<p class="map-failed">地图脚本没加载出来，刷新试试。</p>';
          return;
        }
        L.Icon.Default.prototype.options.imagePath = '/leaflet/images/';
        var map = L.map(el, { scrollWheelZoom: false });
        @LAYERS@.forEach(function (lyr) {
          L.tileLayer(lyr.u, {
            subdomains: lyr.s, attribution: lyr.a, maxZoom: lyr.z, minZoom: 3
          }).addTo(map);
        });

        var pts = [];
        places.forEach(function (p) {
          var pop = '<div class="map-pop">'
            + (p.i ? '<a href="' + p.u + '"><img src="' + p.i + '" alt=""></a>' : '')
            + '<strong><a href="' + p.u + '">' + p.t + '</a></strong>'
            + '<em>' + p.d + (p.p ? '　·　' + p.p : '') + '</em>'
            + (p.s ? '<span>' + p.s + '</span>' : '')
            + '</div>';
          L.marker([p.x, p.y]).addTo(map).bindPopup(pop, { maxWidth: 250 });
          pts.push([p.x, p.y]);
        });

        function look() {
          if (pts.length === 1) {
            map.setView(pts[0], 11);
          } else {
            map.fitBounds(pts, { padding: [50, 50], maxZoom: 11 });
          }
        }
        look();
        // 图片/字体加载完之后容器尺寸才最终确定，这时再量一次并对准视野，
        // 否则 Leaflet 会拿解析期的宽度去算缩放（会算出离谱的层级）。
        window.addEventListener('load', function () {
          map.invalidateSize();
          look();
        });

        // 默认不抢滚轮：点一下地图才允许滚轮缩放，鼠标移开就还回去
        el.addEventListener('click', function () { map.scrollWheelZoom.enable(); });
        el.addEventListener('mouseleave', function () { map.scrollWheelZoom.disable(); });
      }

      // 这段脚本在文档还没解析完时就会执行，那时容器宽度还量不准，
      // 所以等 DOM 就绪再建地图。
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
      } else {
        init();
      }
    })();
    </script>
    <p class="map-hint">点击标记看那一次的照片和记录　·　<a href="#trips">看文字记录 ↓</a></p>"""

    for token, value in (
        ("@PLACES@", json.dumps(marks, ensure_ascii=False)),
        ("@LAYERS@", json.dumps(_map_layers(), ensure_ascii=False)),
    ):
        js = js.replace(token, value)
    return js


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
        # front matter 里写了 custom_page: true 的，说明这一页是手工做的完整网页，
        # 放在 static/books/<slug>/ 下，靠本文件末尾的静态资源复制带进 public/。
        # 这里必须跳过，否则会被下面这个简易详情页覆盖掉。
        if str(b.get("custom_page", "")).strip().lower() in ("true", "yes", "1"):
            continue
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
             f"{html.escape(str(t.get('place','')))}　·　{fmt_date(t['date'])}"
             + (f"　·　{len(trip_photos(t['slug']))} 张照片" if trip_photos(t["slug"]) else ""),
             (t.get("summary") or t["body"][:90]).replace("\n", " "))
        for t in trips
    ) or '      <p class="empty">还没有旅行记录。在 content/travel/ 下新建 .md 文件即可。</p>'
    write_page("travel/index.html", page("旅行", "/travel/", f"""    <h1 class="page-title">旅行</h1>
{map_section(trips)}
    <div class="grid" id="trips">
{trip_cards}
    </div>""", head=MAP_HEAD))
    for t in trips:
        write_page(f"travel/{t['slug']}/index.html", page(t.get("title", t["slug"]), "/travel/", f"""    <article class="detail">
      <p class="crumb"><a href="/travel/">← 返回旅行</a></p>
      <h1>{html.escape(t.get('title', t['slug']))}</h1>
      <p class="byline">{html.escape(str(t.get('place','')))}　·　{fmt_date(t['date'])}</p>
      <div class="prose">
{t['html']}
      </div>
{gallery_html(t['slug'])}
    </article>""", depth=2))

    # ── 照片 ──
    # 只收 prep_photos.py 压过的那批（static/photos/ 下），原图留在 photos/ 不进站点
    all_photos = []
    if PUBLISHED.is_dir():
        for d in sorted(PUBLISHED.iterdir()):
            if d.is_dir():
                all_photos += [(d.name, p) for p in trip_photos(d.name)]
    tiles = "\n".join(
        f'      <figure><a href="{photo_url(slug, p.name)}" target="_blank" rel="noopener">'
        f'<img src="{photo_url(slug, p.name, thumb=True)}" alt="" loading="lazy"></a></figure>'
        for slug, p in all_photos
    ) or ('      <p class="empty">还没有照片。把原图放进 '
          '<code>photos/&lt;行程&gt;/</code>，跑 <code>python prep_photos.py</code>，'
          '再跑 <code>python build.py</code>。</p>')
    write_page("photos/index.html", page("照片", "/photos/",
        f'    <h1 class="page-title">照片</h1>\n    <div class="gallery">\n{tiles}\n    </div>'))

    # ── 关于 ──
    write_page("about/index.html", page("关于", "/about/", f"""    <article class="detail">
      <h1>关于</h1>
      <div class="prose">
{md(about_body)}
      </div>
    </article>"""))

    # ── 404 ──
    write_page("404.html", page("没找到这一页", "", f"""    <article class="detail">
      <h1>没找到这一页</h1>
      <div class="prose">
        <p>这个地址上没有东西。可能是链接写错了，也可能是这一页还没写。</p>
        <p><a href="/">回首页</a>　·　<a href="/books/">去看书单</a></p>
      </div>
    </article>"""))

    # ── 静态资源 ──
    # static/ 原样搬进 public/：style.css、leaflet/、books/<slug>/ 的手工页，
    # 以及 prep_photos.py 压好的 static/photos/<行程>/（照片就靠这一步上线）
    if STATIC.exists():
        for item in STATIC.iterdir():
            dest = OUT / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    print(f"✓ 构建完成 → {OUT}")
    print(f"  书籍 {len(books)} 本　文章 {len(posts)} 篇　旅行 {len(trips)} 条　照片 {len(all_photos)} 张")


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
