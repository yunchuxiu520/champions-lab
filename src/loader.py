"""读取 Smogon 的 chaos 月度对战统计。

一个 chaos 文件的结构：
    {
      "info": {"metagame": "gen9championsvgc2026regmc", "cutoff": 1500,
               "number of battles": 1649648},
      "data": {
        "Rillaboom": {
            "usage": 0.3613,
            "Raw count": 1173979,
            "Abilities": {"grassysurge": 0.99, "overgrow": 0.01},   # 加权计数
            "Items": {...}, "Moves": {...}, "Spreads": {...},
            "Checks and Counters": {"Incineroar": {"n":..., "p":..., "d":...}},
            "Teammates": {"Incineroar": 12345.6, ...}
        }
      }
    }

注意：Abilities / Items / Moves 里的值是"加权计数"，不是百分比，
要自己除以总和才是占比。Spreads 的键形如 "Jolly:252/252/0/0/4/0"。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_chaos(fname: str) -> dict:
    """读一份 chaos 文件。fname 只写文件名，会自动去 data/ 找。"""
    path = Path(fname)
    if not path.is_absolute():
        path = DATA_DIR / path
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def usage_table(chaos: dict) -> pd.DataFrame:
    """使用率排行，按使用率降序，索引从 1 开始当名次用。"""
    rows = [
        {
            "name": name,
            "usage": float(mon["usage"]),
            "raw_count": int(mon.get("Raw count", 0)),
        }
        for name, mon in chaos["data"].items()
    ]
    df = pd.DataFrame(rows).sort_values("usage", ascending=False).reset_index(drop=True)
    df.index += 1
    return df


def breakdown(mon: dict, key: str) -> pd.Series:
    """把 Items / Moves / Abilities / Tera Types 归一成 0~1 的占比。"""
    counts = mon.get(key) or {}
    total = sum(counts.values())
    if total <= 0:
        return pd.Series(dtype="float64")
    s = pd.Series({k: v / total for k, v in counts.items()})
    return s.sort_values(ascending=False)


def spread_table(mon: dict, top: int = 8) -> pd.DataFrame:
    """性格 + 努力值配置。键形如 "Jolly:252/252/0/0/4/0"。"""
    spreads = mon.get("Spreads") or {}
    total = sum(spreads.values()) or 1
    rows = []
    for k, v in spreads.items():
        nature, _, evs = k.partition(":")
        rows.append({"nature": nature or k, "evs": evs, "share": v / total})
    df = pd.DataFrame(rows).sort_values("share", ascending=False)
    return df.head(top).reset_index(drop=True)


def teammates(chaos: dict, name: str, top: int = 12) -> pd.DataFrame:
    """同队共现频率。除以自身 raw_count，近似"带这只时有多大比例带某伙伴"。"""
    mon = chaos["data"][name]
    mates = mon.get("Teammates") or {}
    base = max(int(mon.get("Raw count", 0)), 1)
    rows = [
        {"teammate": k, "rate": v / base}
        for k, v in mates.items()
        if k in chaos["data"]
    ]
    return (
        pd.DataFrame(rows).sort_values("rate", ascending=False).head(top).reset_index(drop=True)
    )


def checks_and_counters(chaos: dict, name: str, top: int = 10) -> pd.DataFrame:
    """什么能压制这只宝可梦。

    chaos 里每项是 {"n": 加权样本, "p": 对位胜率, "d": 优势程度}。
    p 越高说明对手越能稳吃它。
    """
    mon = chaos["data"][name]
    cc = mon.get("Checks and Counters") or {}
    rows = [
        {"opponent": k, "win_rate": v.get("p", 0), "score": v.get("d", 0), "n": v.get("n", 0)}
        for k, v in cc.items()
        if k in chaos["data"]
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("win_rate", ascending=False).head(top).reset_index(drop=True)