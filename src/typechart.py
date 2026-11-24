"""属性克制表（第 6 世代之后，含妖精属性）。

只做一件事：给一个攻击属性和一个或多个防御属性，算出倍率。
2.0 = 效果拔群，0.5 = 效果不好，0 = 无效。
"""
from __future__ import annotations

TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
    "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
]

# 只列出不为 1 的组合，其余默认 1 倍
_RAW: dict[str, dict[str, float]] = {
    "Normal":   {"Rock": .5, "Ghost": 0, "Steel": .5},
    "Fire":     {"Fire": .5, "Water": .5, "Grass": 2, "Ice": 2, "Bug": 2,
                 "Rock": .5, "Dragon": .5, "Steel": 2},
    "Water":    {"Fire": 2, "Water": .5, "Grass": .5, "Ground": 2, "Rock": 2, "Dragon": .5},
    "Electric": {"Water": 2, "Electric": .5, "Grass": .5, "Ground": 0,
                 "Flying": 2, "Dragon": .5},
    "Grass":    {"Fire": .5, "Water": 2, "Grass": .5, "Poison": .5, "Ground": 2,
                 "Flying": .5, "Bug": .5, "Rock": 2, "Dragon": .5, "Steel": .5},
    "Ice":      {"Fire": .5, "Water": .5, "Grass": 2, "Ice": .5, "Ground": 2,
                 "Flying": 2, "Dragon": 2, "Steel": .5},
    "Fighting": {"Normal": 2, "Ice": 2, "Poison": .5, "Flying": .5, "Psychic": .5,
                 "Bug": .5, "Rock": 2, "Ghost": 0, "Dark": 2, "Steel": 2, "Fairy": .5},
    "Poison":   {"Grass": 2, "Poison": .5, "Ground": .5, "Rock": .5, "Ghost": .5,
                 "Steel": 0, "Fairy": 2},
    "Ground":   {"Fire": 2, "Electric": 2, "Grass": .5, "Poison": 2, "Flying": 0,
                 "Bug": .5, "Rock": 2, "Steel": 2},
    "Flying":   {"Electric": .5, "Grass": 2, "Fighting": 2, "Bug": 2, "Rock": .5, "Steel": .5},
    "Psychic":  {"Fighting": 2, "Poison": 2, "Psychic": .5, "Dark": 0, "Steel": .5},
    "Bug":      {"Fire": .5, "Grass": 2, "Fighting": .5, "Poison": .5, "Flying": .5,
                 "Psychic": 2, "Ghost": .5, "Dark": 2, "Steel": .5, "Fairy": .5},
    "Rock":     {"Fire": 2, "Ice": 2, "Fighting": .5, "Ground": .5, "Flying": 2,
                 "Bug": 2, "Steel": .5},
    "Ghost":    {"Normal": 0, "Psychic": 2, "Ghost": 2, "Dark": .5},
    "Dragon":   {"Dragon": 2, "Steel": .5, "Fairy": 0},
    "Dark":     {"Fighting": .5, "Psychic": 2, "Ghost": 2, "Dark": .5, "Fairy": .5},
    "Steel":    {"Fire": .5, "Water": .5, "Electric": .5, "Ice": 2, "Rock": 2,
                 "Steel": .5, "Fairy": 2},
    "Fairy":    {"Fire": .5, "Fighting": 2, "Poison": .5, "Dragon": 2, "Dark": 2, "Steel": .5},
}

CHART: dict[str, dict[str, float]] = {
    atk: {dfn: _RAW.get(atk, {}).get(dfn, 1.0) for dfn in TYPES}
    for atk in TYPES
}


def effectiveness(attack: str, defenders: list[str]) -> float:
    """某个攻击属性，对拥有 defenders 这些属性的宝可梦是几倍。"""
    mult = 1.0
    for d in defenders:
        mult *= CHART[attack][d]
    return mult


def weakness_profile(types: list[str]) -> dict[str, float]:
    """一只宝可梦面对 18 种属性时的倍率表。"""
    return {atk: effectiveness(atk, types) for atk in TYPES}


def label(mult: float) -> str:
    """把倍率转成人话。"""
    return {0: "免疫", 0.25: "1/4", 0.5: "1/2", 1: "普通", 2: "弱点", 4: "双重弱点"}.get(mult, f"x{mult:g}")