"""Champions 环境分析：使用率、配置拆解、克制关系、队友搭配。

用法:
    python -m src.report                                 # 默认 VGC 2026 Reg M-C 1500+
    python -m src.report gen9championsou-1500.json       # 换单打 OU
    python -m src.report gen9championsou-1500.json Rillaboom   # 指定分析哪只
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import dex  # noqa: E402
from .loader import (  # noqa: E402
    breakdown,
    checks_and_counters,
    load_chaos,
    spread_table,
    teammates,
    usage_table,
)

OUT = dex.ROOT / "output"
ACCENT = "#2f6f4f"
WARN = "#b4462f"
GREY = "#8a8f8c"
DEFAULT = "gen9championsvgc2026regmc-1500.json"


def _strip_axes(ax, sides=("top", "right")):
    for s in sides:
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8)


def fig_top_usage(chaos: dict, n: int = 20):
    df = usage_table(chaos).head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 7.5))
    bars = ax.barh(
        [dex.display_name(x) for x in df["name"]], df["usage"] * 100,
        color=ACCENT, height=0.72,
    )
    top = df["usage"].max() * 100
    for b, v in zip(bars, df["usage"] * 100):
        ax.text(v + top * 0.012, b.get_y() + b.get_height() / 2, f"{v:.1f}%",
                va="center", fontsize=8, color="#333")
    info = chaos["info"]
    ax.set_xlabel("Usage (%)")
    ax.set_title(
        f"Top {n} usage — {info['metagame']} @{info['cutoff']}\n"
        f"{info['number of battles']:,} battles",
        fontsize=11, loc="left",
    )
    ax.set_xlim(0, top * 1.14)
    _strip_axes(ax)
    fig.tight_layout()
    return fig


def fig_loadout(chaos: dict, name: str, top: int = 6):
    """道具 / 招式 两栏条形 + 特性文字栏。"""
    mon = chaos["data"][name]
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.2))

    for ax, (key, col) in zip(axes[:2], [("Items", ACCENT), ("Moves", GREY)]):
        s = breakdown(mon, key).head(top).iloc[::-1]
        bars = ax.barh([k.replace("-", " ") for k in s.index], s.values * 100,
                       color=col, height=0.65)
        vmax = max(s.values * 100) if len(s) else 100
        for b, v in zip(bars, s.values * 100):
            ax.text(v + vmax * 0.02, b.get_y() + b.get_height() / 2, f"{v:.0f}%",
                    va="center", fontsize=8)
        ax.set_title(f"{key[:-1]}  (top {top})", fontsize=10, loc="left")
        ax.set_xlim(0, vmax * 1.2)
        _strip_axes(ax)

    ax = axes[2]
    ax.axis("off")
    ax.set_title("Ability", fontsize=10, loc="left")
    s = breakdown(mon, "Abilities")
    if len(s) == 1:
        ax.text(0, 0.88, s.index[0].replace("-", " "), fontsize=13, color=ACCENT, weight="bold")
        ax.text(0, 0.74, "100% of sets", fontsize=8.5, color=GREY)
    else:
        y = 0.9
        for k, v in s.head(top).items():
            ax.text(0, y, k.replace("-", " "), fontsize=9)
            ax.text(0.95, y, f"{v*100:.0f}%", fontsize=9, ha="right")
            y -= 0.14

    fig.suptitle(f"{dex.display_name(name)} — loadout @{chaos['info']['cutoff']}",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    return fig


def fig_checks(chaos: dict, name: str, top: int = 10):
    """什么能压住它。条越长 = 对位胜率越高。"""
    df = checks_and_counters(chaos, name, top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    ax.barh([dex.display_name(x) for x in df["opponent"]], df["win_rate"] * 100,
            color=WARN, height=0.66)
    for i, v in enumerate(df["win_rate"] * 100):
        ax.text(v + 0.5, i, f"{v:.0f}%", va="center", fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Win rate when facing it (%)")
    ax.set_title(f"What beats {dex.display_name(name)}", fontsize=11, loc="left")
    _strip_axes(ax)
    fig.tight_layout()
    return fig


def fig_teammates(chaos: dict, name: str, top: int = 12):
    df = teammates(chaos, name, top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    ax.barh([dex.display_name(x) for x in df["teammate"]], df["rate"] * 100,
            color=GREY, height=0.68)
    for i, v in enumerate(df["rate"] * 100):
        ax.text(v + 0.4, i, f"{v:.0f}%", va="center", fontsize=8)
    ax.set_xlabel("Chance to be on the same team (%)")
    ax.set_title(f"Common partners of {dex.display_name(name)}", fontsize=11, loc="left")
    _strip_axes(ax)
    fig.tight_layout()
    return fig


def main(argv: list[str]) -> None:
    fname = argv[0] if argv else DEFAULT
    chaos = load_chaos(fname)
    OUT.mkdir(parents=True, exist_ok=True)

    df = usage_table(chaos)
    df.to_csv(OUT / "usage_ranking.csv", encoding="utf-8-sig")
    print(f"[ok] 使用率表 -> output/usage_ranking.csv  ({len(df)} 只)")

    star = argv[1] if len(argv) > 1 else df["name"].iloc[0]

    fig_top_usage(chaos).savefig(OUT / "top20_usage.png", dpi=130)
    print("[ok] Top20 使用率 -> output/top20_usage.png")

    fig_loadout(chaos, star).savefig(OUT / "loadout.png", dpi=130)
    print(f"[ok] {dex.display_name(star)} 配置 -> output/loadout.png")

    fig_checks(chaos, star).savefig(OUT / "checks.png", dpi=130)
    print(f"[ok] {dex.display_name(star)} 克制关系 -> output/checks.png")

    fig_teammates(chaos, star).savefig(OUT / "teammates.png", dpi=130)
    print(f"[ok] {dex.display_name(star)} 队友 -> output/teammates.png")

    # 控制台也打一份核心数据
    print(f"\n{'名次':<5}{'宝可梦':<24}{'使用率':>8}")
    for i, r in df.head(15).iterrows():
        print(f"{i:<5}{dex.display_name(r['name']):<24}{r['usage']*100:>7.2f}%")

    print(f"\n{dex.display_name(star)} 常见配置:")
    print("  性格/努力值（前 3）:")
    for _, r in spread_table(chaos['data'][star], 3).iterrows():
        print(f"    {r['nature']:<10} {r['evs']:<22} {r['share']*100:.0f}%")
    print("  被谁压制（前 5）:")
    for _, r in checks_and_counters(chaos, star, 5).iterrows():
        print(f"    {dex.display_name(r['opponent']):<22} 胜率 {r['win_rate']*100:.0f}%")


if __name__ == "__main__":
    main(sys.argv[1:])