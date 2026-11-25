"""环境加权：算出每种攻击属性在真实环境里有多"有威胁"。

属性克制表只回答"如果你被 X 属性打，会受几倍伤害"。
实战里真正的问题是"对手队伍里到底有没有 X 属性、会不会真的打出来"。

思路
----
从对战统计反推每种属性的**出现强度**：

    presence[T] = Σ 每只宝可梦的使用率 × 它真正能用 T 属性打人的程度

"打人程度"由两部分决定：

1. **招式威力**：40 威力的 Fake Out 和 120 威力的 Close Combat 不是一回事，
   所以按 basePower/80 加权（上限 1.5）。
2. **本系加成**：招式属性与自己属性相同时乘 1.5。

不假设"是这个属性就一定有 STAB 输出"。Indeedee-F 是普通属性，
但它只带 Follow Me / Helping Hand / Trick Room，一个普通攻击招式都没有，
不该被算成普通属性的威胁来源。

用法:
    from src.threat import meta_presence
    df = meta_presence(chaos)   # 索引是 18 种属性
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from . import abilities, dex
from .typechart import TYPES

POWER_REF = 80.0      # 以 80 威力为基准 1.0
POWER_CAP = 1.5       # 再高也只算 1.5 倍
STAB_BONUS = 1.5
KIT_CAP = 1.5         # 单只宝可梦对单一属性的最大贡献

# 招式属性转换规则来自 data/rules/abilities.json（见 src/abilities.py），
# 不在代码里写死具体特性名——新特性只要往 json 里加一条。

# 属性随天气/场地变化的招式。chaos 统计不记录队伍带了什么天气，
# 无法准确判断它实际打什么属性，所以不归入任何一个属性（见 README 的已知限制）。
CONDITIONAL_TYPE_MOVES = {"weatherball", "terrainpulse"}


def _norm_ability(ability: str) -> str:
    return (ability or "").replace("-", "").replace(" ", "").lower()


@lru_cache(maxsize=1)
def load_moves() -> dict[str, dict]:
    """招式 ID → 招式信息（属性、威力、分类）。

    会应用 Champions 对威力的修改（data/rules/moves_override.json），
    因为 Showdown 原版数值不等于 Champions 的数值。
    """
    path = dex.DATA_DIR / "moves.json"
    with open(path, encoding="utf-8") as f:
        moves = json.load(f)
    ov = dex.DATA_DIR / "rules" / "moves_override.json"
    if ov.exists():
        with open(ov, encoding="utf-8") as f:
            overrides = json.load(f).get("basePower", {})
        for mid, bp in overrides.items():
            if mid in moves:
                moves[mid] = {**moves[mid], "basePower": bp}
    return moves


def move_weight(move_id: str) -> float:
    """一个招式的"威胁权重"：变化招式和没威力的招式记 0。

    80 威力 → 1.0，40 威力 → 0.5，120 威力以上 → 1.5（封顶）。
    """
    mv = load_moves().get(move_id)
    if not mv:
        return 0.0
    bp = mv.get("basePower") or 0
    if mv.get("category") == "Status" or bp <= 0:
        return 0.0
    return min(bp / POWER_REF, POWER_CAP)


def move_type(move_id: str) -> str | None:
    mv = load_moves().get(move_id)
    return mv.get("type") if mv else None


def effective_move_type(mid: str, ability: str) -> str | None:
    """考虑特性之后，这个招式实际打出什么属性。

    比如飞行皮肤把普通系招式转成飞行系，Normalize 把所有招式变成普通系。
    具体哪些特性会转换、转成什么，都从规则文件读。
    """
    t = move_type(mid)
    if t is None:
        return None
    conv = abilities.convert(ability)
    if not conv:
        return t
    src, dst = conv.get("from"), conv.get("to")
    if src == "*" or src == t:
        return dst
    return t


def effective_move_weight(mid: str, ability: str) -> float:
    """威力权重。被特性转换过的招式按规则里的 power 倍率放大。"""
    w = move_weight(mid)
    if w == 0:
        return 0.0
    conv = abilities.convert(ability)
    if conv:
        src = conv.get("from")
        if src == "*" or src == move_type(mid):
            w = min(w * float(conv.get("power", 1.0)), POWER_CAP)
    return w


def _kit_with_ability(mon: dict, name: str, mtype: str, ability: str,
                      split: dict[str, dict[str, float]] | None = None) -> float:
    """在"这只宝可梦用这个特性"的前提下，它对 mtype 的火力贡献。

    `split` 给出气象球/大地波动实际会打成什么属性的概率分布——
    场地是全场共用的，所以这些招式不能固定归给某一个属性。
    """
    moves = mon.get("Moves") or {}
    total = sum(moves.values()) or 1
    is_stab = mtype in dex.types_of(name)
    # 伪天气（超级日光等）：自己的招式按该天气算，不参与抢天气
    pseudo = abilities.rule_of(ability).get("pseudo_weather")
    score = 0.0
    for mid, cnt in moves.items():
        share = cnt / total
        if mid in CONDITIONAL_TYPE_MOVES:
            if pseudo:
                from .fields import WEATHER_BALL_TYPE
                p_type = 1.0 if WEATHER_BALL_TYPE.get(pseudo) == mtype else 0.0
            elif not split:
                continue
            else:
                p_type = split.get(mid, {}).get(mtype, 0.0)
            if p_type <= 0:
                continue
            w = move_weight(mid)
            if w == 0:
                continue
            score += share * p_type * w * (STAB_BONUS if is_stab else 1.0)
            continue
        if effective_move_type(mid, ability) != mtype:
            continue
        w = effective_move_weight(mid, ability)
        if w == 0:
            continue
        score += share * w * (STAB_BONUS if is_stab else 1.0)
    return min(score, KIT_CAP)


def kit_share(mon: dict, name: str, mtype: str,
              split: dict[str, dict[str, float]] | None = None) -> float:
    """这只宝可梦用 mtype 打人的强度（0 ~ KIT_CAP）。

    按它实际携带的各个特性占比加权——同一只宝可梦不同配置可能带不同特性，
    比如普通形态和 Mega 形态的特性完全不同。
    """
    abilities = mon.get("Abilities") or {}
    total = sum(abilities.values())
    if not total:
        return _kit_with_ability(mon, name, mtype, "", split)
    score = sum(
        (cnt / total) * _kit_with_ability(mon, name, mtype, ab, split)
        for ab, cnt in abilities.items()
    )
    return min(score, KIT_CAP)


def meta_presence(chaos: dict) -> pd.DataFrame:
    """每种攻击属性的环境出现强度。

    返回 DataFrame，索引是属性，列：
        presence  0~1（已归一，1 = 环境里威胁最大的属性）
        raw       未归一值，可理解成"平均每队有多少单位的该属性火力"
    """
    from .fields import field_type_split

    split = field_type_split(chaos)
    raw = {t: 0.0 for t in TYPES}
    for name, mon in chaos["data"].items():
        usage = float(mon["usage"])
        for t in TYPES:
            raw[t] += usage * kit_share(mon, name, t, split)
    df = pd.DataFrame({"raw": pd.Series(raw)})
    top = df["raw"].max() or 1.0
    df["presence"] = df["raw"] / top
    return df.sort_values("raw", ascending=False)


def threat_breakdown(chaos: dict, mtype: str, top: int = 8) -> pd.DataFrame:
    """某个属性的威胁主要由谁贡献，用来检查算法合不合理。"""
    from .fields import field_type_split

    split = field_type_split(chaos)
    rows = []
    for name, mon in chaos["data"].items():
        v = float(mon["usage"]) * kit_share(mon, name, mtype, split)
        if v > 0:
            rows.append({"name": name, "contribution": v, "usage": float(mon["usage"])})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("contribution", ascending=False).head(top)
    total = sum(float(m["usage"]) * kit_share(m, n, mtype, split) for n, m in chaos["data"].items())
    df["share_of_type"] = df["contribution"] / (total or 1)
    return df.reset_index(drop=True)


def main() -> None:
    from .loader import load_chaos

    chaos = load_chaos("gen9championsvgc2026regmc-1500.json")
    df = meta_presence(chaos)
    print("环境属性威胁度（VGC 2026 Reg M-C）\n")
    print(f"{'属性':<10}{'出现强度':>9}{'火力值':>9}")
    for t, r in df.iterrows():
        print(f"{t:<10}{r['presence']*100:>8.0f}%{r['raw']:>9.2f}")

    print("\nNormal 威胁来源核对（应该只有真的带普通攻击招的）：")
    for _, r in threat_breakdown(chaos, "Normal", 6).iterrows():
        print(f"  {r['name']:<22} 贡献{r['contribution']:.3f}  占该属性{r['share_of_type']*100:.0f}%")


if __name__ == "__main__":
    main()