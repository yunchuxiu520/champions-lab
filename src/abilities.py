"""特性规则层：从 data/rules/abilities.json 读规则，不把机制写死在代码里。

这样做的理由
------------
Champions 会持续加入新特性（比如狠辣椒的辣椒喷发），如果把每个特性写成
`if ability == "xxx"` 分支，代码会无限膨胀，而且每加一个都要改逻辑。
规则放进 json 后，加特性只是加一条数据。

本模块只负责"读规则 + 套用规则"，包含两部分：

- 防御侧：`defensive_profile()` 调整一只宝可梦对 18 种属性的承受倍率
- 进攻侧：`convert()` / `stab_multiplier()` 给 impact 计算用

没有收录在规则文件里的特性不会报错，只是不产生调整。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import dex
from .typechart import TYPES, effectiveness

RULES_PATH = dex.DATA_DIR / "rules" / "abilities.json"


def normalize(ability: str) -> str:
    """特性名规范化：去空格和连字符、转小写。aerilate / Aeri-late 都能对上。"""
    return (ability or "").replace("-", "").replace(" ", "").lower()


@lru_cache(maxsize=1)
def load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def rule_of(ability: str) -> dict:
    """取某个特性的规则；没有就返回空字典。"""
    rules = load_rules()
    key = normalize(ability)
    r = rules.get(key)
    return r if isinstance(r, dict) else {}


def has_rule(ability: str) -> bool:
    return bool(rule_of(ability))


# ---------------------------------------------------------------- 防御侧

def apply_defensive_rule(profile: dict[str, float], ability: str) -> dict[str, float]:
    """把一条特性的防御效果套到倍率表上。

    profile 是 {属性: 倍率}，返回新的字典，不改原对象。
    """
    r = rule_of(ability)
    if not r:
        return dict(profile)
    out = dict(profile)

    for t in r.get("immune_types", []):
        if t in out:
            out[t] = 0.0

    for t, m in (r.get("type_mult") or {}).items():
        if t in out:
            out[t] *= m

    se = r.get("se_mult")
    if se is not None:
        for t in out:
            if out[t] >= 2:
                out[t] *= se

    fh = r.get("full_hp_mult")
    if fh is not None:
        # 满血时减伤，用"最优情况"估算：整体乘上，并在标签里注明
        for t in out:
            out[t] *= fh

    return out


def defensive_profile(name: str, mon: dict | None = None) -> dict[str, float]:
    """一只宝可梦对 18 种属性的承受倍率，已考虑特性。

    同一只宝可梦可能有多个特性（不同配置），按 Abilities 里的占比加权。
    没有特性数据时退回纯属性表。
    """
    types = dex.types_of(name)
    base = {t: effectiveness(t, types) for t in TYPES}
    if not mon:
        return base

    abilities = mon.get("Abilities") or {}
    total = sum(abilities.values())
    if not total:
        return base

    acc = {t: 0.0 for t in TYPES}
    for ability, cnt in abilities.items():
        w = cnt / total
        adj = apply_defensive_rule(base, ability)
        for t in TYPES:
            acc[t] += w * adj[t]
    # 多个特性加权后会累积浮点误差（2.0 变成 1.9999999），
    # 导致后面 ">= 2 判定为弱点" 失效，所以统一收敛到 4 位小数。
    return {t: round(v, 4) for t, v in acc.items()}


def defensive_ability_notes(name: str, mon: dict | None = None) -> list[str]:
    """列出这只宝可梦真正起作用的防御类特性，用来在报告里说明差异来源。"""
    if not mon:
        return []
    abilities = mon.get("Abilities") or {}
    total = sum(abilities.values()) or 1
    out = []
    for ability, cnt in abilities.items():
        r = rule_of(ability)
        if not r:
            continue
        if not any(k in r for k in ("immune_types", "type_mult", "se_mult", "full_hp_mult")):
            continue
        share = cnt / total
        if share < 0.10:
            continue  # 占比太低，说明不是主流配置
        bits = []
        if r.get("immune_types"):
            bits.append("免疫 " + "/".join(r["immune_types"]))
        if r.get("type_mult"):
            bits.append(
                "减伤 "
                + ", ".join(f"{t}×{m:g}" for t, m in r["type_mult"].items())
            )
        if r.get("se_mult"):
            bits.append(f"效果拔群 ×{r['se_mult']:g}")
        if r.get("full_hp_mult"):
            bits.append(f"满血减伤 ×{r['full_hp_mult']:g}")
        out.append(f"{ability}（{share*100:.0f}%）: " + "；".join(bits))
    return out


# ---------------------------------------------------------------- 进攻侧

def convert(ability: str) -> dict | None:
    """这条特性的招式属性转换规则，没有则 None。"""
    return rule_of(ability).get("convert")


def stab_multiplier(ability: str) -> float:
    return float(rule_of(ability).get("stab_mult", 1.5))


def field_of(ability: str) -> str | None:
    return rule_of(ability).get("field")


def field_speed(ability: str) -> str | None:
    return rule_of(ability).get("field_speed")


def main() -> None:
    """自检：把规则覆盖情况和环境占比打出来。"""
    from .loader import load_chaos

    chaos = load_chaos("gen9championsvgc2026regmc-1500.json")
    weighted: dict[str, float] = {}
    for name, mon in chaos["data"].items():
        ab = mon.get("Abilities") or {}
        tot = sum(ab.values()) or 1
        for a, cnt in ab.items():
            k = normalize(a)
            weighted[k] = weighted.get(k, 0.0) + float(mon["usage"]) * (cnt / tot)

    defs = [k for k, r in load_rules().items() if isinstance(r, dict) and any(
        x in r for x in ("immune_types", "type_mult", "se_mult", "full_hp_mult"))]
    offs = [k for k, r in load_rules().items() if isinstance(r, dict) and any(
        x in r for x in ("convert", "stab_mult", "aura"))]
    flds = [k for k, r in load_rules().items() if isinstance(r, dict) and any(
        x in r for x in ("field", "field_speed"))]

    print(f"规则文件收录：防御 {len(defs)} / 进攻 {len(offs)} / 场地 {len(flds)}\n")
    print("防御类特性在环境中的占比（只列进入前 60 的）：")
    for k in sorted(defs, key=lambda x: -weighted.get(x, 0))[:15]:
        if weighted.get(k, 0) > 0:
            print(f"  {k:<16}{weighted[k]*100:6.2f}")
    print("\n场地类特性：")
    for k in sorted(flds, key=lambda x: -weighted.get(x, 0))[:12]:
        if weighted.get(k, 0) > 0:
            print(f"  {k:<16}{weighted[k]*100:6.2f}  → {field_of(k) or field_speed(k)}")

    covered = sum(weighted.get(k, 0) for k in defs + offs + flds)
    totalw = sum(weighted.values())
    print(f"\n已建规则覆盖的环境特性占比：{covered/totalw*100:.1f}%")


if __name__ == "__main__":
    main()