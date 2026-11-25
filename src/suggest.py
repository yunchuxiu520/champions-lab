"""补强建议：从环境数据里找出能补队伍弱点的候选宝可梦。

三个层次
--------
1. `resists()` —— 只看属性的抗性判断（最基础）
2. `resists_with_ability()` —— 连带特性一起算（Levitate 免疫地面这类）
3. `advise_team()` —— 给一支队伍，算出最该补的属性，并推荐候选

用法:
    # 看谁能抗冰（纯属性）
    python -m src.suggest --resist Ice

    # 带特性算（Levitate 之类会被算成免疫）
    python -m src.suggest --resist Ice --ability

    # 给队伍做补强建议
    python -m src.suggest --team "Salamence-Mega" "Charizard-Mega-Y" Garchomp Rillaboom Sneasler Kingambit

    # 看具体两只的对位
    python -m src.suggest --check "Garchomp" Ice
"""
from __future__ import annotations

import sys

from . import abilities, dex
from .loader import load_chaos
from .typechart import TYPES, effectiveness

DEFAULT_META = "gen9championsvgc2026regmc-1500.json"


# ---------------------------------------------------------------- 基础判断

def resists(name: str, attack_type: str) -> float:
    """某只宝可梦承受 attack_type 的倍率，只看属性，不看特性。

    返回 0.0（免疫）/ 0.25 / 0.5（抗性）/ 1.0（普通）/ 2.0 / 4.0（弱点）。
    名字查不到时抛 ValueError——因为"查不到"和"不抗"是两件事，
    前者是调用方写错了名字，不该被悄悄当成普通来处理。
    """
    types = dex.types_of(name)
    if not types:
        raise ValueError(f"查不到 {name!r} 的属性，检查名字拼写")
    return effectiveness(attack_type, types)


def resists_with_ability(name: str, attack_type: str, mon: dict | None = None) -> float:
    """连带特性一起算的倍率。

    比 resists 更接近实战：Levitate 的宝可梦吃地面是 0，不是 1。
    需要 mon（chaos 里那只宝可梦的数据）才能知道它带什么特性；
    不传就退回纯属性判断。
    """
    if mon is None:
        return resists(name, attack_type)
    return abilities.defensive_profile(name, mon)[attack_type]


# ---------------------------------------------------------------- 环境筛选

def candidates(chaos: dict, attack_type: str, min_usage: float = 0.02,
               top: int = 8) -> list[tuple[str, float]]:
    """从环境里筛出能抗 attack_type 的宝可梦，按使用率降序。

    min_usage 是过滤门槛：使用率低于它的不参与，避免把冷门宝可梦推给你。
    倍率严格小于 1 才算抗（0 / 0.25 / 0.5 都算，1.0 和 2.0 以上不算）。
    """
    out: list[tuple[str, float]] = []
    for name, mon in chaos["data"].items():
        usage = float(mon["usage"])
        if usage < min_usage:
            continue
        types = dex.types_of(name)
        if not types:
            continue
        if effectiveness(attack_type, types) < 1:
            out.append((name, usage))
    out.sort(key=lambda pair: pair[1], reverse=True)
    return out[:top]


def candidates_with_ability(chaos: dict, attack_type: str, min_usage: float = 0.02,
                            top: int = 8) -> list[tuple[str, float, float]]:
    """同 candidates，但把特性算进去，返回 (名字, 使用率, 倍率) 三元组。"""
    out: list[tuple[str, float, float]] = []
    for name, mon in chaos["data"].items():
        usage = float(mon["usage"])
        if usage < min_usage:
            continue
        if not dex.types_of(name):
            continue
        mult = abilities.defensive_profile(name, mon)[attack_type]
        if mult < 1:
            out.append((name, usage, mult))
    out.sort(key=lambda t: t[1], reverse=True)
    return out[:top]


# ---------------------------------------------------------------- 队伍补强

def team_risks(chaos: dict, team: list[str], top: int = 3) -> list[tuple[str, float, float]]:
    """算出这支队伍最该补的属性，返回 (属性, 弱点只数, 环境火力) 三元组。

    排序依据：弱点只数 × 环境火力。只看属性表会误判，
    所以乘上该属性在环境里的真实火力（threat.meta_presence）。
    """
    from .threat import meta_presence

    presence = meta_presence(chaos)["presence"]
    rows = []
    for atk in TYPES:
        weak = 0.0
        for name in team:
            mon = chaos["data"].get(name)
            if not mon or not dex.types_of(name):
                continue
            if abilities.defensive_profile(name, mon)[atk] >= 2:
                weak += 1
        if weak <= 0:
            continue
        rows.append((atk, weak, float(presence[atk]), weak * float(presence[atk])))
    rows.sort(key=lambda r: r[3], reverse=True)
    return [(a, w, p) for a, w, p, _ in rows[:top]]


def advise_team(chaos: dict, team: list[str], per_risk: int = 3,
                min_usage: float = 0.03) -> list[dict]:
    """给队伍做补强建议。

    对每个主要风险属性，列出能抗它、且使用率够高的候选。
    同时算一个「净收益」：补掉几个队内弱点 − 自己又给队伍添了几个新弱点。

    候选只从「当前队伍没有的宝可梦」里挑。
    """
    risks = team_risks(chaos, team)
    if not risks:
        return []

    # 只把「最该补的前 5 个风险」当作要填的洞。
    # 如果把队伍所有弱点属性都算成洞，数字会虚高到「补 9 个洞」这种看不懂的说法。
    holes = {r[0] for r in team_risks(chaos, team, top=5)}
    # 全属性弱点集合，用来判断候选会不会添新洞
    team_weak_all = set()
    for atk in TYPES:
        for name in team:
            mon = chaos["data"].get(name)
            if mon and dex.types_of(name) and \
                    abilities.defensive_profile(name, mon)[atk] >= 2:
                team_weak_all.add(atk)
                break

    result = []
    for risk_type, weak_count, presence in risks:
        scored = []
        for name, usage, mult in candidates_with_ability(
                chaos, risk_type, min_usage=min_usage, top=40):
            if name in team:
                continue
            mon = chaos["data"][name]
            profile = abilities.defensive_profile(name, mon)
            # 它填掉了几个"主要风险"
            covered_types = [t for t in holes if profile[t] < 1]
            covered = len(covered_types)
            # 它自己给队伍添了几个原先没有的弱点
            added_types = [t for t in TYPES if profile[t] >= 2 and t not in team_weak_all]
            added = len(added_types)
            scored.append({
                "name": name,
                "usage": usage,
                "mult": mult,
                "covered": covered,
                "covered_types": covered_types,
                "added": added,
                "added_types": added_types,
                "net": covered - added,
            })
        scored.sort(key=lambda d: (-d["net"], -d["usage"]))
        result.append({
            "risk": risk_type,
            "weak_count": weak_count,
            "presence": presence,
            "picks": scored[:per_risk],
        })
    return result


# ---------------------------------------------------------------- CLI

def _print_resist(chaos: dict, attack_type: str, with_ability: bool) -> None:
    rows = (candidates_with_ability(chaos, attack_type) if with_ability
            else [(n, u, resists(n, attack_type)) for n, u in candidates(chaos, attack_type)])
    title = "含特性" if with_ability else "只看属性"
    print(f"\n能抗住 {attack_type} 的常见宝可梦（{title}，使用率 ≥2%）\n")
    print(f"{'#':>3} {'宝可梦':<24}{'使用率':>8}{'倍率':>7}")
    for i, (name, usage, mult) in enumerate(rows, 1):
        print(f"{i:>3} {dex.display_name(name):<24}{usage*100:>7.2f}%{mult:>7.2f}")


def _print_advice(chaos: dict, team: list[str]) -> None:
    advice = advise_team(chaos, team)
    if not advice:
        print("队伍里没有能被属性克制的成员，或者名字都查不到。")
        return
    print("\n" + "=" * 62)
    print("  队伍补强建议")
    print("=" * 62)
    print("  净收益 = 能补掉的队内弱点数 − 自己添的新弱点数。越高越值得换进来。\n")
    for item in advice:
        print(f"【最该补：{item['risk']}】队伍 {item['weak_count']:.0f} 只弱它，"
              f"环境火力 {item['presence']*100:.0f}%")
        for p in item["picks"]:
            flag = "★" if p["net"] >= 2 else " "
            fills = "/".join(p["covered_types"]) or "—"
            adds = "/".join(p["added_types"]) or "无"
            print(f"  {flag} {dex.display_name(p['name']):<22}"
                  f"使用率 {p['usage']*100:5.2f}%  抗 {item['risk']} 到 {p['mult']:.2f}")
            print(f"      填补：{fills}（{p['covered']} 项）   新增弱点：{adds}（{p['added']} 项）"
                  f"   净 {p['net']:+d}")
        print()


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        raise SystemExit(1)

    chaos = load_chaos(DEFAULT_META)
    args = list(argv)

    if "--check" in args:
        i = args.index("--check")
        name, atk = args[i + 1], args[i + 2]
        mon = chaos["data"].get(name)
        pure = resists(name, atk)
        full = resists_with_ability(name, atk, mon)
        note = "（特性没有改变它）" if abs(pure - full) < 1e-9 else "（特性改变了它）"
        print(f"{dex.display_name(name)} 承受 {atk}："
              f"纯属性 {pure:.2f} → 含特性 {full:.2f} {note}")
        return

    if "--team" in args:
        i = args.index("--team")
        _print_advice(chaos, args[i + 1:])
        return

    if "--resist" in args:
        i = args.index("--resist")
        _print_resist(chaos, args[i + 1], "--ability" in args)
        return

    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])