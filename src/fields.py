"""环境场地/天气分析：设定者强度、被抢风险、以及"慢速抢快"的方向。

三条容易搞错、而这里专门处理的机制
--------------------------------
1. **异名场地/天气会互相覆盖，同名不会。** 所以 rain 和 sun 互抢，
   两个都开 rain 的队伍不冲突。
2. **抢赢的是速度更慢的那只。** 天气/场地特性在登场时触发，同一回合里
   后行动的一方最后触发，所以最终生效的是**慢**的那只。快的先手开出来
   会被慢的后手顶掉。
3. **Levitate / 飞行系不吃地面场地效果，但仍会触发场地种子道具。**
   种子看的是场地是否存在，与脚下是否接地无关。

本模块只做"环境层"的估算，不模拟具体对局。所有概率都是上限近似，
不是精确的期望值。

用法:
    python -m src.fields
"""
from __future__ import annotations

import math

import pandas as pd

from . import abilities, dex
from .loader import load_chaos

# 场地/天气对属性的直接加成
FIELD_BOOST = {
    "Grassy Terrain": {"boost": "Grass", "mult": 1.3},
    "Psychic Terrain": {"boost": "Psychic", "mult": 1.3},
    "Electric Terrain": {"boost": "Electric", "mult": 1.3},
    "Misty Terrain": {"boost": "Fairy", "mult": 1.3},
    "Rain": {"boost": "Water", "mult": 1.5},
    "Sun": {"boost": "Fire", "mult": 1.5},
    "Sand": {"boost": None, "mult": 1.0},
    "Snow": {"boost": "Ice", "mult": 1.0},
}

# 同组之间会互相覆盖
WEATHER = {"Rain", "Sun", "Sand", "Snow"}
TERRAIN = {"Grassy Terrain", "Psychic Terrain", "Electric Terrain", "Misty Terrain"}

# 气象球/大地波动随场地变属性。**场地是全场的，不是谁开的归谁用。**
# 所以你开了晴天，对手的水属性气象球也会变成火属性打你。
WEATHER_BALL_TYPE = {"Sun": "Fire", "Rain": "Water", "Sand": "Rock", "Snow": "Ice"}
TERRAIN_PULSE_TYPE = {
    "Electric Terrain": "Electric",
    "Grassy Terrain": "Grass",
    "Psychic Terrain": "Psychic",
    "Misty Terrain": "Fairy",
}
NO_FIELD_BALL_TYPE = "Normal"  # 没有天气/场地时气象球是普通系

# 速度差转"抢赢概率"的尺度：差 15 点速度大约对应 70/30
SPEED_SCALE = 15.0

FIELD_NOTES = [
    "**场地/天气是全场共用的，不是开的人独占。** 你开晴天，对手的水属性气象球也会变成"
    "火属性——大嘴鸥带气象球 22%，在你的晴天下就是火系打你的草系。开场地前先想清楚"
    "自己是不是在给对手送强化。",
    "**抢天气/场地的是速度更慢的那只**：特性在登场时触发，同回合后动的最后触发。"
    "所以快的场地手先开出来会被慢的顶掉，慢速队反而更容易控场。",
    "**同名之间不会互顶，但也不会延长。** 同一种天气/场地的第二只设定者登场时，"
    "回合数不会重置——所以冗余设定者换不来更多时间，只有在被对手抢掉后能再抢回来"
    "这一种备用价值。环境数据佐证：同场地设定者共现率几乎为 0（Indeedee-F 与 Indeedee "
    "0.00%，Pelipper 与 Politoed 0.12%），玩家普遍不带冗余。",
    "Levitate / 飞行系不受地面场地效果影响，但仍会吃到场地种子道具"
    "（电气种子、青草种子等），因为种子看的是场地是否存在而不是脚下是否接地。",
    "场地伤害加成与状态免疫只对「在地面上」的宝可梦生效；天气加成对所有宝可梦生效。",
    "**无天气(Cloud Nine) / 气闸(Air Lock) 会压制所有天气效果**：在场时天气伤害加成为零、"
    "天气加速类特性失效、气象球变回普通系。天气本身仍算存在，只是效果被压制，"
    "所以它「消除不了」对手开出来的晴天，只能让它不起作用。本条不影响场地。",
    "天气/场地的持续回合数本模块不建模：特性天气通常只有 5 回合，到点自行消失，"
    "hold_rate 只回答「会不会被对手抢掉」，不含「自己到期」。",
]


def setter_table(chaos: dict) -> pd.DataFrame:
    """列出每只场地/天气设定者：它开什么、权重多少、基础速度多少。

    权重 = 使用率 × 该特性在该宝可梦身上的占比。
    速度取图鉴的基础速度（不含性格与努力值，见已知限制）。
    """
    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    rows = []
    for name, mon in chaos["data"].items():
        abs_ = mon.get("Abilities") or {}
        tot = sum(abs_.values()) or 1
        for ability, cnt in abs_.items():
            f = abilities.field_of(ability)
            if not f:
                continue
            w = float(mon["usage"]) * (cnt / tot)
            if w <= 0:
                continue
            spe = dex.base_stats(name).get("spe", 0)
            rows.append({"name": name, "field": f, "ability": ability,
                         "weight": w, "slot_rate": w / total_usage, "speed": spe})
    df = pd.DataFrame(rows)
    return df.sort_values("weight", ascending=False).reset_index(drop=True) if not df.empty else df


def _group_of(field: str) -> set[str]:
    if field in WEATHER:
        return WEATHER
    if field in TERRAIN:
        return TERRAIN
    return {field}


def field_contest(chaos: dict) -> pd.DataFrame:
    """估算每种场地/天气能站稳的概率，已考虑"慢速抢快"。

    步骤
    ----
    1. `位置率 = 设定者权重 / 6`（VGC 每队 6 格，chaos 的 usage 之和就是 6）
    2. 竞品 = 同组里**其他**场地/天气的位置率（同名不互抢）
    3. 对手从 6 只带 4 只，带进至少一只竞品的概率 = 1 - (1 - 竞品率)^4
    4. 抢赢方向：**我方设定者越慢越占优**。用双方平均基础速度的差算一个
       逻辑斯蒂概率 win_bias = 1 / (1 + exp((我方速度 - 对方速度) / 15))
       —— 我方越慢，这个值越接近 1。
    5. hold_rate = 对手没带竞品 + 带了但被我方抢赢
                  = (1 - p) + p × win_bias
    """
    st = setter_table(chaos)
    if st.empty:
        return pd.DataFrame()

    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    # 每个场地：自身权重、自身加权平均速度
    self_w: dict[str, float] = {}
    self_speed: dict[str, float] = {}
    for f, g in st.groupby("field"):
        self_w[f] = float(g["weight"].sum())
        self_speed[f] = float((g["weight"] * g["speed"]).sum() / max(g["weight"].sum(), 1e-9))

    destroy_risk = terrain_destroy_risk(chaos)[0]
    rows = []
    for f, w in self_w.items():
        group = _group_of(f)
        comp_w = sum(self_w.get(k, 0.0) for k in group if k != f)
        # 竞品的加权平均速度
        comp_rows = st[st["field"].isin(group) & (st["field"] != f)]
        if not comp_rows.empty and comp_rows["weight"].sum() > 0:
            comp_speed = float(
                (comp_rows["weight"] * comp_rows["speed"]).sum() / comp_rows["weight"].sum()
            )
        else:
            comp_speed = self_speed[f]

        p_comp = comp_w / total_usage
        p_comp = min(p_comp, 1.0)
        bring_risk = 1 - (1 - p_comp) ** 4

        # 我方越慢越占优
        win_bias = 1 / (1 + math.exp((self_speed[f] - comp_speed) / SPEED_SCALE))
        hold = (1 - bring_risk) + bring_risk * win_bias

        # 场地还会被冰旋/铁滚轮/清除雾直接拆掉；天气没有对应招式，不受此影响
        if f in TERRAIN:
            hold *= (1 - destroy_risk)

        mult = FIELD_BOOST.get(f, {}).get("mult", 1.0)
        rows.append({
            "field": f,
            "self_slot": w / total_usage,
            "comp_slot": p_comp,
            "bring_risk": bring_risk,
            "self_speed": self_speed[f],
            "comp_speed": comp_speed,
            "slower_than_comp": self_speed[f] < comp_speed,
            "win_bias": win_bias,
            "hold_rate": hold,
            "expected_mult": 1 + (mult - 1) * hold,
        })
    return pd.DataFrame(rows).set_index("field").sort_values("hold_rate", ascending=False)


def field_presence(chaos: dict) -> pd.DataFrame:
    """设定者强度——**不是**它能稳定存在多久，覆盖率看 field_contest 的 hold_rate。"""
    st = setter_table(chaos)
    if st.empty:
        return pd.DataFrame()
    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    raw = st.groupby("field")["weight"].sum()
    df = pd.DataFrame({"raw": raw})
    df["presence"] = df["raw"] / (df["raw"].max() or 1)
    df["slot_rate"] = df["raw"] / total_usage
    df["boost_type"] = [FIELD_BOOST.get(f, {}).get("boost") for f in df.index]
    df["boost_mult"] = [FIELD_BOOST.get(f, {}).get("mult", 1.0) for f in df.index]
    return df.sort_values("raw", ascending=False)


def field_speed_users(chaos: dict) -> pd.DataFrame:
    """该天气下速度翻倍的宝可梦。"""
    rows = []
    for name, mon in chaos["data"].items():
        abs_ = mon.get("Abilities") or {}
        tot = sum(abs_.values()) or 1
        for ability, cnt in abs_.items():
            f = abilities.field_speed(ability)
            if f and cnt / tot >= 0.3:
                rows.append({"name": name, "ability": ability, "field": f,
                             "usage": float(mon["usage"]), "share": cnt / tot})
    df = pd.DataFrame(rows)
    return df.sort_values("usage", ascending=False).reset_index(drop=True) if not df.empty else df


def main() -> None:
    chaos = load_chaos("gen9championsvgc2026regmc-1500.json")

    print("=== 1) 设定者强度（有多少宝可梦会开它，不是它能待多久）===\n")
    df = field_presence(chaos)
    print(f"{'场地/天气':<18}{'相对强度':>9}{'位置率':>8}   加成")
    for f, r in df.iterrows():
        bt = r["boost_type"]
        boost = "—" if pd.isna(bt) else f"{bt} x{r['boost_mult']:g}"
        print(f"{f:<18}{r['presence']*100:>8.0f}%{r['slot_rate']*100:>7.1f}%   {boost}")

    print("\n=== 2) 被抢风险（异名互抢；慢速者抢赢）===\n")
    con = field_contest(chaos)
    print(f"{'场地/天气':<18}{'对手带竞品':>9}{'我方速度':>8}{'竞品速度':>8}{'我慢?':>6}{'站稳率':>7}{'期望加成':>8}")
    for f, r in con.iterrows():
        slower = "是" if r["slower_than_comp"] else "否"
        print(f"{f:<18}{r['bring_risk']*100:>8.0f}%{r['self_speed']:>8.0f}"
              f"{r['comp_speed']:>8.0f}{slower:>6}{r['hold_rate']*100:>6.0f}%{r['expected_mult']:>8.2f}")

    print("\n=== 3) 天气加速手 ===\n")
    sp = field_speed_users(chaos)
    for _, r in sp.head(8).iterrows():
        print(f"  {r['name']:<22}{r['usage']*100:5.2f}%  {r['ability']} → {r['field']}")

    print("\n=== 4) 场地共用风险：你开它，对手会拿到什么 ===\n")
    for f in ["Sun", "Rain", "Grassy Terrain", "Psychic Terrain"]:
        risk = shared_field_risk(chaos, f)
        if risk.empty:
            continue
        ball = risk["becomes"].iloc[0]
        parts = []
        for _, r in risk.head(4).iterrows():
            mark = "*" if r["is_stab"] else ""
            parts.append(f"{r['name']}{mark}({r['carry']*100:.0f}%)")
        print(f"  {f:<18} → 气象球变 {ball}：{'、'.join(parts)}")

    print("    （* = 变成的属性与该宝可梦本系相同，吃本系加成）")
    sup = weather_suppressed(chaos)
    print(f"\n  天气被压制概率：{sup*100:.2f}%（对手 4 只里至少带一只无天气/气闸）")

    print("\n=== 5) 气象球/大地波动的属性分布 ===")
    for k, bucket in field_type_split(chaos).items():
        parts = ", ".join(f"{t} {p*100:.0f}%" for t, p in sorted(bucket.items(), key=lambda x: -x[1]))
        print(f"  {k:<14}{parts}")

    print("\n=== 6) 场地破坏（招式，不是特性）===\n")
    risk, d = terrain_destroy_risk(chaos)
    print(f"  对手 4 只里带拆场地招式的概率：{risk*100:.2f}%")
    if not d.empty:
        for _, r in d.head(4).iterrows():
            tag = "（需场地在场才生效）" if r["reactive"] else ""
            print(f"    {r['name']:<22}{r['move']:<14}携带 {r['carry']*100:3.0f}%"
                  f"  使用率 {r['usage']*100:5.2f}%{tag}")
    print("  换场(Court Change) 会直接抢走你的场地，当前环境无人携带。")

    print("\n=== 7) 容易漏的交互 ===\n")
    for n in FIELD_NOTES:
        print("  - " + n)

    print("\n已知限制：速度用图鉴基础速度，未计性格与努力值；"
          "抢赢概率用双方加权平均速度近似，实际是逐只对位。")



RULES_FIELDS = dex.DATA_DIR / "rules" / "fields.json"


def load_field_rules() -> dict:
    """读「拆场地/换场」招式规则。"""
    import json
    with open(RULES_FIELDS, encoding="utf-8") as f:
        return json.load(f)


def terrain_destroyers(chaos: dict) -> pd.DataFrame:
    """谁带了拆场地的招式、携带率多少。

    这些不是特性而是招式效果，独立统计。
    """
    rules = load_field_rules()
    rows = []
    for name, mon in chaos["data"].items():
        mv = mon.get("Moves") or {}
        tot = sum(mv.values()) or 1
        for move_id, meta in rules.items():
            if move_id.startswith("_") or not isinstance(meta, dict):
                continue
            if meta.get("destroys") != "terrain":
                continue
            if move_id in mv and mv[move_id] / tot >= 0.03:
                rows.append({
                    "name": name,
                    "move": move_id,
                    "carry": mv[move_id] / tot,
                    "usage": float(mon["usage"]),
                    "weight": float(mon["usage"]) * (mv[move_id] / tot),
                    "reactive": bool(meta.get("requires_field")),
                })
    df = pd.DataFrame(rows)
    return df.sort_values("weight", ascending=False).reset_index(drop=True) if not df.empty else df


def terrain_destroy_risk(chaos: dict) -> tuple[float, pd.DataFrame]:
    """对手 4 只里至少带一只拆场地招式的概率。

    返回 (概率, 携带者表)。场地被拆后回合数直接归零，所以这个概率
    要从场地的站稳率里扣掉。
    """
    d = terrain_destroyers(chaos)
    if d.empty:
        return 0.0, d
    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    p_slot = d["weight"].sum() / total_usage
    return _p_bring(p_slot), d


def weather_suppressed(chaos: dict) -> float:
    """对手 4 只里至少带一只「无天气/气闸」的概率。

    这类特性在场时所有天气效果失效，所以天气带来的收益要按这个概率打折。
    气闸同理，目前环境里只统计得到 cloudnine。
    """
    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    w = 0.0
    for _, mon in chaos["data"].items():
        ab = mon.get("Abilities") or {}
        tot = sum(ab.values()) or 1
        for ability, cnt in ab.items():
            if abilities.rule_of(ability).get("negates_weather"):
                w += float(mon["usage"]) * (cnt / tot)
    return _p_bring(w / total_usage)


def _p_bring(p_slot: float) -> float:
    """某一格是该场地手的概率 → 从 6 只带 4 只时至少带一只的概率。"""
    return 1 - (1 - min(p_slot, 1.0)) ** 4


def field_type_split(chaos: dict) -> dict[str, dict[str, float]]:
    """气象球和大地波动分别会打成什么属性的概率分布。

    两者属性池不同，不能混在一起：
    - 气象球：Sun→火、Rain→水、Sand→岩、Snow→冰，没天气时是普通系
    - 大地波动：电气场地→电、青草场地→草、精神场地→超能、雾之场地→妖精，
      没场地时是普通系

    场地/天气是全场共用的，所以按"环境里它们出现的概率"来分。
    """
    st = setter_table(chaos)
    total_usage = sum(float(m["usage"]) for m in chaos["data"].values()) or 1
    out: dict[str, dict[str, float]] = {"weatherball": {}, "terrainpulse": {}}
    if st.empty:
        return {"weatherball": {NO_FIELD_BALL_TYPE: 1.0},
                "terrainpulse": {NO_FIELD_BALL_TYPE: 1.0}}

    for f, g in st.groupby("field"):
        p_slot = float(g["weight"].sum()) / total_usage
        p = _p_bring(p_slot)
        if f in WEATHER_BALL_TYPE:
            bucket = out["weatherball"]
            t = WEATHER_BALL_TYPE[f]
        elif f in TERRAIN_PULSE_TYPE:
            bucket = out["terrainpulse"]
            t = TERRAIN_PULSE_TYPE[f]
        else:
            continue
        bucket[t] = bucket.get(t, 0.0) + p

    # 天气被无天气/气闸压制时，气象球会变回普通系
    sup = weather_suppressed(chaos)
    wb = out["weatherball"]
    moved = 0.0
    for t in list(wb):
        if t == NO_FIELD_BALL_TYPE:
            continue
        cut = wb[t] * sup
        wb[t] -= cut
        moved += cut
    wb[NO_FIELD_BALL_TYPE] = wb.get(NO_FIELD_BALL_TYPE, 0.0) + moved

    for key, bucket in out.items():
        total = sum(bucket.values())
        if total > 1:
            bucket = {k: v / total for k, v in bucket.items()}
            total = 1.0
            out[key] = bucket
        bucket[NO_FIELD_BALL_TYPE] = bucket.get(NO_FIELD_BALL_TYPE, 0.0) + (1.0 - total)
    return out


def shared_field_risk(chaos: dict, field: str) -> pd.DataFrame:
    """你开了这个场地/天气之后，对手哪些招式会变属性、能打穿你队里的谁。

    这是"场地是共用的"最直接的后果：开晴天能让对手的水属性气象球变成火属性。
    """
    ball = WEATHER_BALL_TYPE.get(field) or TERRAIN_PULSE_TYPE.get(field)
    if not ball:
        return pd.DataFrame()
    rows = []
    for name, mon in chaos["data"].items():
        mv = mon.get("Moves") or {}
        tot = sum(mv.values()) or 1
        for move_id in ("weatherball", "terrainpulse"):
            if move_id not in mv:
                continue
            share = mv[move_id] / tot
            if share < 0.05:
                continue
            own = dex.types_of(name)
            rows.append({
                "name": name,
                "move": move_id,
                "carry": share,
                "usage": float(mon["usage"]),
                "becomes": ball,
                "is_stab": ball in own,
                "own_types": "/".join(own),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("usage", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    main()
