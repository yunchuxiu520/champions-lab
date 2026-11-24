"""下载 Smogon 月度对战统计（chaos JSON）和 Showdown 图鉴数据。

用法:
    python -m src.fetch                          # 抓默认的 Champions 格式
    python -m src.fetch 2026-10                  # 指定月份
    python -m src.fetch 2026-10 gen9championsou-1500.json
    python -m src.fetch --dex                    # 只更新图鉴数据

国内直连 smogon 较慢（单个大文件 1~4 分钟），已做重试和断点跳过。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from .dex import DATA_DIR

STATS = "https://www.smogon.com/stats/{month}/chaos/{fname}"
POKEDEX = "https://play.pokemonshowdown.com/data/pokedex.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) champions-lab/1.0"}

DEFAULT_MONTH = "2026-10"
DEFAULT_FILES = [
    "gen9championsou-0.json",
    "gen9championsou-1500.json",
    "gen9championsou-1630.json",
    "gen9championsuu-1500.json",
    "gen9championsvgc2026regmc-1500.json",
    "gen9championsmegaevolutionbattle-1500.json",
]


def _get(url: str, timeout: int = 180) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def fetch_chaos(month: str, fname: str, retries: int = 3) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / fname
    if out.exists() and out.stat().st_size > 100_000:
        print(f"[skip] {fname} 已存在 ({out.stat().st_size/1e6:.1f}MB)")
        return out

    url = STATS.format(month=month, fname=fname)
    for i in range(1, retries + 1):
        try:
            t0 = time.time()
            print(f"[get ] {fname}  第 {i} 次…")
            blob = _get(url)
            json.loads(blob)  # 确认是合法 JSON 再落盘
            out.write_bytes(blob)
            d = json.loads(blob)
            print(f"[ok  ] {fname}  {len(blob)/1e6:.2f}MB  {time.time()-t0:.0f}s  "
                  f"{d['info']['number of battles']:,} 场 / {len(d['data'])} 只")
            return out
        except Exception as e:  # noqa: BLE001
            print(f"[fail] {type(e).__name__}: {str(e)[:80]}")
            time.sleep(3 * i)
    raise SystemExit(f"下载失败: {url}")


def fetch_dex() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "pokedex.json"
    t0 = time.time()
    blob = _get(POKEDEX, timeout=60)
    out.write_bytes(blob)
    d = json.loads(blob)
    print(f"[ok  ] pokedex.json  {len(blob)/1e6:.2f}MB  {time.time()-t0:.0f}s  {len(d)} 条目")
    return out


def main(argv: list[str]) -> None:
    if "--dex" in argv:
        fetch_dex()
        return
    month = DEFAULT_MONTH
    files = list(DEFAULT_FILES)
    rest = [a for a in argv if not a.startswith("--")]
    if rest:
        month = rest[0]
        if len(rest) > 1:
            files = rest[1:]
    for f in files:
        fetch_chaos(month, f)
    if not (DATA_DIR / "pokedex.json").exists():
        fetch_dex()


if __name__ == "__main__":
    main(sys.argv[1:])