"""读取 Showdown 的 pokedex.json，提供"宝可梦名 → 属性/种族值/特性"查询。

对战的 chaos 数据里只有名字，没有属性；做队伍分析必须补上这一层。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def toid(name: str) -> str:
    """Showdown 的内部 ID：小写并去掉所有非字母数字。

    "Scovillain-Mega" -> "scovillainmega"
    "Slowking-Galar"  -> "slowkinggalar"
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


@lru_cache(maxsize=1)
def load_dex() -> dict:
    path = DATA_DIR / "pokedex.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lookup(name: str) -> dict | None:
    """按 chaos 里的名字查图鉴条目，查不到返回 None。"""
    return load_dex().get(toid(name))


def types_of(name: str) -> list[str]:
    """返回属性列表，比如 ["Grass", "Fire"]。查不到给空列表。"""
    mon = lookup(name)
    return list(mon.get("types", [])) if mon else []


def base_stats(name: str) -> dict[str, int]:
    mon = lookup(name)
    return dict(mon.get("baseStats", {})) if mon else {}


def abilities_of(name: str) -> list[str]:
    """返回这只宝可梦可以拥有的特性名列表。"""
    mon = lookup(name)
    if not mon:
        return []
    return [v for v in (mon.get("abilities") or {}).values() if v]


def display_name(name: str) -> str:
    """把 chaos 名转成好看的显示名：Scovillain-Mega -> Mega Scovillain。"""
    mon = lookup(name)
    return mon.get("name", name) if mon else name