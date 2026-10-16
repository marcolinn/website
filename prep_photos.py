#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 photos/<行程>/ 里的手机原图，压缩成网站用的照片。

    原图      photos/<行程>/*.jpg          ← 你自己留着，不进仓库（见 .gitignore）
    成品      static/photos/<行程>/*.jpg   ← 长边 1600，进仓库，线上就是这份
    缩略图    static/photos/<行程>/thumb/  ← 长边 480，给列表和地图气泡用

两个必须知道的点：

1. **发布出去的那份会剥掉全部 EXIF**，包括 GPS 坐标。手机原图里带着你拍照的
   精确位置，直接传上网等于把行程轨迹公开。原图留在 photos/ 里不受影响。
2. 这个脚本只能在本地跑（需要 Pillow），**不会**在 Cloudflare 上跑。所以
   static/photos/ 的产物要一起提交进仓库。

用法：
    python prep_photos.py            # 只处理有新照片的行程
    python prep_photos.py --force    # 全部重压
    python prep_photos.py huizhou-7days   # 只处理指定行程
"""

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("需要 Pillow：python -m pip install Pillow")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "photos"                 # 原图
DST = ROOT / "static" / "photos"      # 成品（会被 build.py 原样复制进 public/）

FULL_EDGE = 1600      # 正文大图长边
THUMB_EDGE = 480      # 缩略图长边
QUALITY = 82
THUMB_QUALITY = 78

# 这些是 Pillow 12 能直接解的格式。HEIC/HEIF **不在**里面（本机没装 pillow-heif），
# iPhone 默认拍的就是 HEIC，所以遇到时下面会给明确提示，而不是静默跳过。
SRC_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".avif",
            ".bmp", ".tif", ".tiff", ".gif"}
OUT_EXT = ".jpg"


def _hint_unsupported(files):
    """遇到不认识的扩展名时，给出可照做的下一步。"""
    exts = {p.suffix.lower() for p in files}
    if exts & {".heic", ".heif"}:
        print("   iPhone 默认拍 HEIC，本机没有 HEIC 解码器。两个办法：")
        print("     ① 手机上「设置 → 相机 → 格式」改成“兼容性最佳”，以后拍的就是 JPEG；")
        print("     ② 或先把这些 .HEIC 转成 .JPG 再放进 photos/。")
    else:
        print(f"   这些文件不是照片，跳过：{', '.join(sorted(p.name for p in files)[:5])}"
              + ("…" if len(files) > 5 else ""))


# ─────────────────────────────────────────────────────────────
#  EXIF
# ─────────────────────────────────────────────────────────────

def _num(v):
    """EXIF 里的有理数可能是 Fraction、IFDRational，也可能是 (分子, 分母)。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    try:
        return v[0] / v[1]
    except Exception:
        return 0.0


def _dms(coord, ref):
    """把 (度, 分, 秒) 转成十进制度数，南纬/西经取负。"""
    try:
        d, m, s = (_num(x) for x in coord)
    except (TypeError, ValueError):
        return None
    val = d + m / 60.0 + s / 3600.0
    if str(ref).upper() in ("S", "W"):
        val = -val
    return round(val, 6)


def exif_of(path: Path):
    """读出拍摄日期与 GPS。读不到就返回 None —— 不报错，只是没得自动填。"""
    info = {"date": None, "lat": None, "lng": None, "camera": None}
    try:
        with Image.open(path) as im:
            ex = im.getexif()
    except Exception:
        return info

    raw = ex.get(36867) or ex.get(306)          # DateTimeOriginal / DateTime
    if raw:
        s = str(raw).strip().replace(":", "-", 2)   # 2026:04:12 15:31:07 → 2026-04-12 15:31:07
        if len(s) >= 10:
            info["date"] = s[:10]

    model = ex.get(272)                          # Model
    if model:
        info["camera"] = str(model).strip()

    gps = None
    try:
        gps = ex.get_ifd(0x8825)                 # GPS IFD
    except Exception:
        gps = None
    if gps:
        lat = gps.get(2)
        lng = gps.get(4)
        if lat and lng:
            info["lat"] = _dms(lat, gps.get(1, "N"))
            info["lng"] = _dms(lng, gps.get(3, "E"))
    return info


# ─────────────────────────────────────────────────────────────
#  压缩
# ─────────────────────────────────────────────────────────────

def _flatten(im: Image.Image) -> Image.Image:
    """统一成 RGB：带透明通道的贴到白底上。"""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    if im.mode not in ("RGB", "L"):
        return im.convert("RGB")
    return im


def _save(im: Image.Image, dest: Path, edge: int, quality: int):
    out = im.copy()
    out.thumbnail((edge, edge), Image.LANCZOS)
    out = _flatten(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 不传 exif= 参数 → 新文件里没有任何 EXIF，GPS 就此消失
    out.save(dest, "JPEG", quality=quality, optimize=True, progressive=True)


def photo_name(path: Path) -> str:
    """输出文件名：小写、空格换连字符、统一 .jpg。"""
    stem = path.stem.strip().lower().replace(" ", "-")
    keep = "".join(c for c in stem if c.isalnum() or c in "-_.")
    return (keep or "photo") + OUT_EXT


def process_trip(folder: Path, force: bool, verbose: bool = True):
    slug = folder.name
    all_files = [p for p in folder.iterdir() if p.is_file()]
    srcs = sorted(p for p in all_files if p.suffix.lower() in SRC_EXTS)
    unsupported = [p for p in all_files if p.suffix.lower() not in SRC_EXTS]
    if not srcs:
        if verbose:
            print(f"── {slug}")
            if unsupported:
                print(f"   没有可处理的照片：{len(unsupported)} 个文件，扩展名都不在支持列表里。")
                print(f"   支持：{'、'.join(sorted(SRC_EXTS))}")
                _hint_unsupported(unsupported)
            else:
                print("   原图目录是空的，跳过。")
        return 0, 0

    full_dir = DST / slug
    thumb_dir = full_dir / "thumb"
    expected = {}
    used = {}
    for p in srcs:
        name = photo_name(p)
        if name in used:                      # 同名不同扩展名，加序号区分
            used[name] += 1
            name = f"{Path(name).stem}-{used[name]}{OUT_EXT}"
        used[name] = used.get(name, 0)
        expected[name] = p

    # 删掉已经不在原图里的旧成品（比如你删了照片）
    if full_dir.is_dir():
        for old in full_dir.glob("*"):
            if old.is_file() and old.name not in expected:
                old.unlink()
        if thumb_dir.is_dir():
            for old in thumb_dir.glob("*"):
                if old.is_file() and old.name not in expected:
                    old.unlink()

    made, skipped, big = 0, 0, []
    for name, src in expected.items():
        dest = full_dir / name
        thumb = thumb_dir / name
        if (not force and dest.exists() and thumb.exists()
                and dest.stat().st_mtime >= src.stat().st_mtime):
            skipped += 1
            continue
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)   # 按 EXIF 方向转正，再压
                _save(im, dest, FULL_EDGE, QUALITY)
                _save(im, thumb, THUMB_EDGE, THUMB_QUALITY)
            made += 1
            kb = dest.stat().st_size / 1024
            big.append((name, kb))
        except Exception as e:
            print(f"   ! {src.name} 处理失败：{e}")

    if verbose:
        total = sum(kb for _, kb in big)
        print(f"── {slug}")
        print(f"   原图 {len(srcs)} 张　→ 处理 {made} 张、跳过 {skipped} 张")
        if big:
            print(f"   成品共 {total / 1024:.1f} MB（平均 {total / len(big):.0f} KB/张）")
        if unsupported:
            print(f"   ! 另有 {len(unsupported)} 个文件扩展名不支持，已跳过：")
            _hint_unsupported(unsupported)
    return made, skipped


def report_exif(folder: Path):
    """只报告每张原图的拍摄时间与 GPS，不做压缩。

    用途：写 content/travel/<slug>.md 的 lat/lng/stops 时，从这里抄坐标。
    """
    slug = folder.name
    srcs = sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in SRC_EXTS)
    if not srcs:
        print(f"── {slug}\n   原图目录是空的。")
        return

    lats, lngs = [], []
    print(f"── {slug}")
    for p in srcs:
        info = exif_of(p)
        lat, lng = info.get("lat"), info.get("lng")
        coord = ""
        if lat is not None and lng is not None:
            coord = f"{lat:.5f}, {lng:.5f}"
            lats.append(lat)
            lngs.append(lng)
        cam = info.get("camera") or ""
        print(f"   {p.name:24s} {info.get('date') or '（无拍摄时间）':12s} "
              f"{coord or '（无 GPS）':20s} {cam}")

    if lats:
        # 自动备好一行可直接粘进 front matter 的坐标
        print(f"\n   可粘进 front matter（按文件顺序）：")
        print(f"   lat: {', '.join(f'{v:.5f}' for v in lats)}")
        print(f"   lng: {', '.join(f'{v:.5f}' for v in lngs)}")
    else:
        print("\n   这些照片都没有 GPS；坐标可以在高德网页版右键“复制坐标”，手动填到 .md 里。")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    want_exif = "--exif" in sys.argv

    if not SRC.is_dir():
        sys.exit(f"没有 {SRC} 这个目录。")

    folders = sorted(d for d in SRC.iterdir() if d.is_dir())
    if args:
        folders = [d for d in folders if d.name in args]
        if not folders:
            sys.exit(f"photos/ 里没有这几个行程目录：{', '.join(args)}")

    if not folders:
        print("photos/ 下还没有行程目录。")
        print("建一个 photos/<行程>/ ，把手机照片丢进去，再跑一次本脚本。")
        return

    if want_exif:
        for d in folders:
            report_exif(d)
        return

    # 提示哪些目录名对不上 content/travel/ 里的 slug
    travel_dir = ROOT / "content" / "travel"
    slugs = {p.stem for p in travel_dir.glob("*.md")} if travel_dir.is_dir() else set()

    total_made = total_skipped = 0
    for d in folders:
        made, skipped = process_trip(d, force)
        total_made += made
        total_skipped += skipped
        if slugs and d.name not in slugs:
            print(f"   ! photos/{d.name}/ 在 content/travel/ 里没有对应的 .md，"
                  f"这些照片目前不会出现在任何行程页上。")

    print(f"\n✓ 完成：新压 {total_made} 张，跳过 {total_skipped} 张")
    print(f"  成品在 {DST}")
    print("  下一步：python build.py && python check.py")


if __name__ == "__main__":
    main()
