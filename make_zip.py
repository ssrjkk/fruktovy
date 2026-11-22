#!/usr/bin/env python3
"""Собрать fruktovy-dvorets-release.zip рядом с файлами релиза.

По умолчанию кладёт 9 текстовых файлов витрины (то же самое, что отдаёт кнопка
«Скачать ZIP-архив проекта» в футере сайта). Флаг --with-assets добавляет
фото, шрифты, иконки и превью — полный офлайн-комплект.

    python make_zip.py
    python make_zip.py --with-assets -o /tmp/full.zip

Stdlib, внешних зависимостей нет.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    # Windows консоль по умолчанию в cp1251 и ломает русские сообщения.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TEXT_FILES = (
    "index.html",
    "robots.txt",
    "sitemap.xml",
    "manifest.webmanifest",
    "404.html",
    "README.md",
    "AGENT_DEPLOY.md",
    "NEXT_AGENT_PROMPT.md",
    "scripts/gate.mjs",
    "make_zip.py",
)

ASSET_DIRS = ("assets/img", "assets/fonts")
ASSET_FILES = (
    "assets/fonts.css",
    "assets/logo.svg",
    "assets/qr.svg",
    "assets/og.png",
    "assets/icon-192.png",
    "assets/icon-512.png",
    "assets/CREDITS.txt",
)

MAGIC = {
    ".jpg": b"\xff\xd8",
    ".jpeg": b"\xff\xd8",
    ".png": b"\x89PNG",
    ".woff2": b"wOF2",
}

# Минимальный осмысленный размер: короткие служебные файлы проверяются по содержимому,
# а не по длине.
MIN_SIZE = {
    "index.html": 100_000,
    "README.md": 2_500,
    "AGENT_DEPLOY.md": 2_500,
    "NEXT_AGENT_PROMPT.md": 2_500,
    "manifest.webmanifest": 300,
    "404.html": 800,
    "make_zip.py": 1_000,
}

MUST_CONTAIN = {
    "robots.txt": ("User-agent: *", "Sitemap:"),
    "sitemap.xml": ("<urlset", "<loc>"),
}


def check(path: Path) -> str | None:
    """Вернуть текст проблемы или None, если файл выглядит целым."""
    data = path.read_bytes()
    if path.suffix.lower() in (".jpg", ".jpeg"):
        if data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
            return "битый JPEG (нет SOI/EOI)"
    else:
        want = MAGIC.get(path.suffix.lower())
        if want and data[: len(want)] != want:
            return f"подпись файла не {path.suffix}"
    if data[:3] == b"\xef\xbb\xbf":
        return "в файле UTF-8 BOM"
    if b"\r\n" in data and path.suffix.lower() in (".html", ".md", ".py", ".txt", ".xml"):
        return "CRLF вместо LF"
    for needle in MUST_CONTAIN.get(path.name, ()):
        if needle.encode() not in data:
            return f"нет обязательной строки {needle!r}"
    floor = MIN_SIZE.get(path.name, 200 if path.suffix.lower() not in (".txt", ".xml") else 40)
    if len(data) < floor:
        return f"файл {len(data)} байт, ожидалось не меньше {floor}"
    return None


def collect(root: Path, with_assets: bool) -> list[Path]:
    wanted = list(TEXT_FILES) + (list(ASSET_FILES) if with_assets else [])
    paths = []
    missing = []
    for name in wanted:
        p = root / name
        if p.is_file():
            problem = check(p)
            if problem:
                missing.append(f"{name}: {problem}")
            else:
                paths.append(p)
        else:
            missing.append(f"{name}: не найден")
    if with_assets:
        for sub in ASSET_DIRS:
            d = root / sub
            if not d.is_dir():
                missing.append(f"{sub}: каталог не найден")
                continue
            for p in sorted(d.iterdir()):
                if not p.is_file():
                    continue
                problem = check(p)
                if problem:
                    missing.append(f"{sub}/{p.name}: {problem}")
                else:
                    paths.append(p)
    if missing:
        for m in missing:
            print(f"ОШИБКА {m}", file=sys.stderr)
        sys.exit(1)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default="fruktovy-dvorets-release.zip")
    ap.add_argument("--with-assets", action="store_true", help="добавить фото, шрифты и иконки")
    ap.add_argument("--root", default=".", help="каталог с файлами релиза")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.output)
    if out.suffix != ".zip":
        out = out / "fruktovy-dvorets-release.zip"
    paths = collect(root, args.with_assets)

    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in paths:
            zf.write(p, p.relative_to(root).as_posix())
            total += p.stat().st_size

    print(
        f"{out.name}: файлов {len(paths)}, {total / 1048576:.2f} MiB внутри, "
        f"{out.stat().st_size / 1048576:.2f} MiB на диске"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
