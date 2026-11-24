"""队伍弱点分析：理论弱点 + 实战弱点，双轨输出，已考虑特性。

用法:
    python -m src.team Rillaboom Sneasler Incineroar Kingambit Archaludon Indeedee-F

    # 指定用哪份环境数据做加权（默认 VGC 2026 Reg M-C）
    python -m src.team --meta gen9championsou-1500.json Rillaboom Garchomp ...

三件事
------
1. **特性会被算进去**：Levitate 免疫地面、厚脂肪减半火/冰、飞行皮肤改招式属性等，
   规则来自 data/rules/abilities.json，代码不硬编码机制。
2. **理论的危险分**：只看属性表 + 双方特性，回答"结构上你怕什么"。
3. **实战的风险分**：再乘上该属性在当前环境的真实火力，回答"实战里会被什么打"。

名字用 Showdown 写法，带后缀要加引号："Charizard-Mega-Y"
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import abilities, dex  # noqa: E402
from .loader import load_chaos  # noqa: E402
from .threat import meta_presence  # noqa: E402
from .typechart import TYPES, effectiveness, label, weakness_profile  # noqa: E402

OUT = dex.ROOT / "output"
ACCENT = "#2f6f4f"
WARN = "#b4462f"
GREY = "#8a8f8c"
COOL = "#4a6f8a"
DEFAULT_META = "gen9championsvgc2026regmec-1500.json".replace("mec", "c")
DEFAULT_META = "gen9championsvgc2026regmc-1500.json"


def _ability_shares(mon: dict | None) -> dict[str, float]:
    """把 Abilities 归一成 {特性: 占比}。没有数据返回空。"""
    if not mon:
        return {}
    ab = mon.get("Abilities") or {}
    total = sum(ab.values())
    if not total:
        return {}
    return {k: v / total for k, v in ab.items()}


def build_matrix(members: list[str], chaos: dict | None = None) -> pd.DataFrame:
    """每只宝可梦 × 18 种攻击属性的承受倍率（已考虑特性，多特性按占比加权）。"""
    profiles = {}
    for m in members:
        types = dex.types_of(m)
        if not types:
            print(f"[警告] 查不到 {m} 的属性，已跳过")
            continue
        mon = ((chaos or {}).get("data") or {}).get(m)
        profiles[m] = abilities.defensive_profile(m, mon)
    return pd.DataFrame(profiles)


def expected_counts(members: list[str], atk: str, chaos: dict | None = None) -> tuple[float, float, float]:
    """某攻击属性下，队伍里有几只弱点 / 抗性 / 免疫——按各特性的占比算期望值。

    同一只宝可梦可能有多个特性（不同配置），所以结果可能是小数，
    比如 50% 带 Levitate 的宝可梦对地面的期望"免疫数"是 0.5。
    """
    weak = resist = immune = 0.0
    for m in members:
        types = dex.types_of(m)
        if not types:
            continue
        base = {t: effectiveness(t, types) for t in TYPES}
        shares = _ability_shares(((chaos or {}).get("data") or {}).get(m))
        if not shares:
            v = base[atk]
            weak += 1.0 if v >= 2 else 0.0
            immune += 1.0 if v == 0 else 0.0
            resist += 1.0 if 0 < v < 1 else 0.0
            continue
        for ab, w in shares.items():
            v = abilities.apply_defensive_rule(base, ab)[atk]
            if v >= 2:
                weak += w
            elif v == 0:
                immune += w
            elif v < 1:
                resist += w
    return weak, resist, immune


def summarize(members: list[str], matrix: pd.DataFrame,
              chaos: dict | None, presence: pd.Series | None = None) -> pd.DataFrame:
    n = len(matrix.columns)
    rows = []
    for atk in TYPES:
        weak, resist, immune = expected_counts(members, atk, chaos)
        col = matrix.loc[atk]
        neutral = max(n - weak - resist - immune, 0.0)
        p = float(presence[atk]) if presence is not None else float("nan")
        rows.append({
            "attacking_type": atk,
            "weak": weak,
            "neutral": neutral,
            "resist": resist,
            "immune": immune,
            "danger": weak * 2 - resist - immune * 2,
            "presence": p,
            "risk": (weak / n) * p * 100 if presence is not None else float("nan"),
        })
    return pd.DataFrame(rows)


def print_report(members: list[str], matrix: pd.DataFrame, summary: pd.DataFrame,
                 chaos: dict | None, has_meta: bool) -> None:
    print("\n" + "=" * 60)
    print("  队伍成员（含特性影响）")
    print("=" * 60)
    for m in matrix.columns:
        types = dex.types_of(m)
        prof = matrix[m]
        mon = ((chaos or {}).get("data") or {}).get(m)
        weak = [f"{t}({prof[t]:.3g})" for t in TYPES if prof[t] >= 2]
        resist = [t for t in TYPES if 0 < prof[t] < 1]
        immune = [t for t in TYPES if prof[t] <= 0]
        print(f"\n{dex.display_name(m):<22} {'/'.join(types)}")
        print(f"  弱点 {len(weak):>2}：{', '.join(weak) if weak else '无'}")
        print(f"  抗性 {len(resist):>2}：{', '.join(resist) if resist else '无'}")
        if immune:
            print(f"  免疫 {len(immune):>2}：{', '.join(immune)}")
        notes = abilities.defensive_ability_notes(m, mon)
        if notes:
            for nline in notes:
                print(f"  特性影响：{nline}")

    print("\n" + "=" * 60)
    print("  理论弱点（属性表 + 特性，假设有人一定用这个属性打你）")
    print("=" * 60)
    print(f"{'属性':<10}{'弱点':>6}{'普通':>6}{'抗性':>6}{'免疫':>6}{'危险分':>8}")
    theo = summary.sort_values(["danger", "weak"], ascending=False)
    for _, r in theo.head(10).iterrows():
        flag = "  ← 打穿整队" if r["weak"] >= 2.5 else ""
        print(f"{r['attacking_type']:<10}{r['weak']:>6.1f}{r['neutral']:>6.1f}"
              f"{r['resist']:>6.1f}{r['immune']:>6.1f}{r['danger']:>8.1f}{flag}")

    if not has_meta:
        return

    print("\n" + "=" * 60)
    print("  实战风险（理论 × 该属性在环境里的真实火力）")
    print("=" * 60)
    print(f"{'属性':<10}{'弱点':>6}{'环境火力':>10}{'风险分':>8}")
    for _, r in summary.sort_values("risk", ascending=False).head(10).iterrows():
        print(f"{r['attacking_type']:<10}{r['weak']:>6.1f}"
              f"{r['presence']*100:>9.0f}%{r['risk']:>8.1f}")

    print("\n" + "-" * 60)
    print("  两张表的差异（理论名次 vs 实战名次）")
    print("-" * 60)
    diff = summary.copy()
    diff["theo_rank"] = diff["danger"].rank(ascending=False)
    diff["real_rank"] = diff["risk"].rank(ascending=False)
    diff["gap"] = diff["theo_rank"] - diff["real_rank"]
    print("  ▲ 实战比理论更危险（属性表容易低估）")
    for _, r in diff.sort_values("gap", ascending=False).head(3).iterrows():
        print(f"    {r['attacking_type']:<10} 理论第 {int(r['theo_rank']):>2} / "
              f"实战第 {int(r['real_rank']):>2}   环境火力 {r['presence']*100:>3.0f}%")
    print("  ▼ 理论吓人、实战威胁小（可以少防）")
    for _, r in diff.sort_values("gap").head(3).iterrows():
        print(f"    {r['attacking_type']:<10} 理论第 {int(r['theo_rank']):>2} / "
              f"实战第 {int(r['real_rank']):>2}   环境火力 {r['presence']*100:>3.0f}%")

    top = summary.sort_values("risk", ascending=False).iloc[0]
    print("\n" + "-" * 60)
    print(f"⚠ 实战最该防：{top['attacking_type']}"
          f"（你的队伍 {top['weak']:.1f} 只弱它，环境火力 {top['presence']*100:.0f}%）")


def plot_matrix(matrix: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(1.1 * len(matrix.columns) + 2.6, 6.2))
    data = matrix.values
    im = ax.imshow(data, cmap="RdYlGn_r", vmin=0, vmax=4, aspect="auto")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels([dex.display_name(c) for c in matrix.columns],
                       rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(TYPES)))
    ax.set_yticklabels(TYPES, fontsize=8)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = float(data[i, j])
            txt = {0: "0", 0.25: "¼", 0.5: "½", 1: "", 2: "2", 4: "4"}.get(round(v, 2), f"{v:g}" if v % 1 else "")
            if txt:
                light_bg = 1 <= v <= 2
                ax.text(j, i, txt, ha="center", va="center", fontsize=7,
                        color="#1a1a1a" if light_bg else "white")
    ax.set_title("Type matchup incl. abilities — attacker (rows) vs team (cols)",
                 fontsize=10, loc="left")
    fig.colorbar(im, ax=ax, shrink=0.6, label="damage multiplier")
    fig.tight_layout()
    return fig


def plot_dual(summary: pd.DataFrame, has_meta: bool):
    if has_meta:
        fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.8))
    else:
        fig, axes = plt.subplots(1, 1, figsize=(6.6, 4.8))
        axes = [axes]

    theo = summary.sort_values("danger", ascending=False).head(8).iloc[::-1]
    bars = axes[0].barh(theo["attacking_type"], theo["danger"],
                        color=[WARN if d >= 4 else GREY for d in theo["danger"]], height=0.66)
    for b, (d, w) in zip(bars, zip(theo["danger"], theo["weak"])):
        axes[0].text(d + (0.08 if d >= 0 else -0.08), b.get_y() + b.get_height() / 2,
                     f"{w:.1f} weak", va="center", ha="left" if d >= 0 else "right", fontsize=8)
    axes[0].axvline(0, color="#999", lw=0.8)
    axes[0].set_title("Theory — type chart + abilities", fontsize=10, loc="left")
    axes[0].set_xlabel("danger = weak x2 - resist - immune x2", fontsize=8.5)

    if has_meta:
        real = summary.sort_values("risk", ascending=False).head(8).iloc[::-1]
        mx = max(real["risk"]) or 1
        bars = axes[1].barh(real["attacking_type"], real["risk"], color=COOL, height=0.66)
        for b, (v, w, p) in zip(bars, zip(real["risk"], real["weak"], real["presence"])):
            axes[1].text(v + mx * 0.02, b.get_y() + b.get_height() / 2,
                         f"{w:.1f} weak / {p*100:.0f}% meta", va="center", fontsize=7.5)
        axes[1].set_title("Practice — theory x real meta presence", fontsize=10, loc="left")
        axes[1].set_xlabel("risk = (weak share) x presence", fontsize=8.5)
        axes[1].set_xlim(0, mx * 1.45)

    for ax in axes:
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    return fig


def main(argv: list[str]) -> None:
    meta_file = DEFAULT_META
    args = list(argv)
    if "--meta" in args:
        i = args.index("--meta")
        meta_file = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        raise SystemExit(1)

    chaos = None
    try:
        chaos = load_chaos(meta_file)
    except FileNotFoundError:
        print(f"[提示] 找不到 {meta_file}，只做理论分析，且不考虑特性")

    matrix = build_matrix(args, chaos)
    if matrix.empty:
        raise SystemExit("没有一只能查到属性，检查名字拼写")

    presence = meta_presence(chaos)["presence"] if chaos else None
    summary = summarize(list(matrix.columns), matrix, chaos, presence)
    print_report(list(matrix.columns), matrix, summary, chaos, presence is not None)

    OUT.mkdir(parents=True, exist_ok=True)
    plot_matrix(matrix).savefig(OUT / "team_matrix.png", dpi=130)
    plot_dual(summary, presence is not None).savefig(OUT / "team_danger.png", dpi=130)
    print("\n[ok] 热力图（含特性） -> output/team_matrix.png")
    print("[ok] 理论与实战对比图 -> output/team_danger.png")


if __name__ == "__main__":
    main(sys.argv[1:])