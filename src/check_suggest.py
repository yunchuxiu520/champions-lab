"""验收器：检查 src/suggest.py 写得对不对。别改这个文件。

用法:
    cd ~/champions-lab && source .venv/bin/activate
    python -m src.check_suggest

只有两种结果：全部通过，或者告诉你第几项没过、期望什么、你返回了什么。
"""
from __future__ import annotations

import sys

PASS = "\033[32m通过\033[0m"
FAIL = "\033[31m没过\033[0m"

results: list[tuple[bool, str, str]] = []


def check(label: str, got, want, hint: str = "") -> None:
    ok = got == want
    msg = "" if ok else f"期望 {want!r}，你返回 {got!r}" + (f"  [{hint}]" if hint else "")
    results.append((ok, label, msg))


def approx(label: str, got, want, hint: str = "") -> None:
    try:
        ok = got is not None and abs(float(got) - want) < 1e-9
    except (TypeError, ValueError):
        ok = False
    msg = "" if ok else f"期望 {want}，你返回 {got!r}" + (f"  [{hint}]" if hint else "")
    results.append((ok, label, msg))


def main() -> None:
    try:
        from . import suggest
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} 导入 src/suggest.py 就失败了：{type(e).__name__}: {e}")
        print("  检查文件是否有语法错误（比如缩进、少括号）")
        raise SystemExit(1)

    from .loader import load_chaos

    # ---------------- resists ----------------
    print("== resists() ==")
    tests = [
        ("Garchomp", "Ice", 4.0, "龙/地 双重弱冰"),
        ("Garchomp", "Fire", 0.5, "龙抗火"),
        ("Kingambit", "Psychic", 0.0, "恶免疫超能"),
        ("Rillaboom", "Water", 0.5, "草抗水"),
        ("Charizard-Mega-Y", "Rock", 4.0, "火/飞 双重弱岩"),
        ("Eelektross-Mega", "Ground", 2.0, "纯电属性，属性上弱地面（鳗鳗高升的免疫是特性，本函数不管特性）"),
    ]
    for name, atk, want, hint in tests:
        try:
            approx(f"resists({name!r}, {atk!r})", suggest.resists(name, atk), want, hint)
        except NotImplementedError:
            results.append((False, f"resists({name!r}, {atk!r})", "函数还是 NotImplementedError"))
        except Exception as e:  # noqa: BLE001
            results.append((False, f"resists({name!r}, {atk!r})", f"抛异常 {type(e).__name__}: {e}"))

    # 查不到的名字应该抛 ValueError
    try:
        suggest.resists("NotARealPokemon", "Fire")
        results.append((False, "resists('NotARealPokemon', 'Fire')", "应该抛 ValueError，但没抛"))
    except ValueError:
        results.append((True, "resists('NotARealPokemon', 'Fire') 抛 ValueError", ""))
    except NotImplementedError:
        results.append((False, "查不到名字的处理", "函数还是 NotImplementedError"))
    except Exception as e:  # noqa: BLE001
        results.append((False, "查不到名字的处理", f"抛了 {type(e).__name__}，应该是 ValueError"))

    # ---------------- candidates ----------------
    print("== candidates() ==")
    chaos = load_chaos("gen9championsvgc2026regmc-1500.json")
    for atk in ["Ice", "Fire", "Fairy"]:
        try:
            res = suggest.candidates(chaos, atk)
        except NotImplementedError:
            results.append((False, f"candidates(chaos, {atk!r})", "函数还是 NotImplementedError"))
            continue
        except Exception as e:  # noqa: BLE001
            results.append((False, f"candidates(chaos, {atk!r})", f"抛异常 {type(e).__name__}: {e}"))
            continue

        # 结构检查
        ok_struct = isinstance(res, list) and all(
            isinstance(x, (tuple, list)) and len(x) == 2 for x in res)
        results.append((ok_struct, f"candidates({atk!r}) 返回 [(名字, 使用率), ...]",
                        "" if ok_struct else f"返回的是 {type(res).__name__}，元素也要是二元组"))
        if not ok_struct or not res:
            if ok_struct:
                results.append((False, f"candidates({atk!r}) 结果为空", "一个都没筛出来"))
            continue

        names = [x[0] for x in res]
        usages = [x[1] for x in res]

        # 每个都真的抗？
        bad = []
        for n in names:
            m = suggest.resists(n, atk)
            if not (m < 1):
                bad.append((n, m))
        results.append((not bad, f"candidates({atk!r}) 里每只都真的抗（倍率 < 1）",
                        "" if not bad else f"这些不是抗性：{bad[:3]}"))

        # 按使用率降序
        desc = all(usages[i] >= usages[i + 1] for i in range(len(usages) - 1))
        results.append((desc, f"candidates({atk!r}) 按使用率从高到低",
                        "" if desc else f"实际顺序 {[round(u, 3) for u in usages]}"))

        # 默认 top=8、min_usage=0.02
        results.append((len(res) <= 8, f"candidates({atk!r}) 不超过 8 条",
                        "" if len(res) <= 8 else f"返回了 {len(res)} 条"))
        low = [n for n, u in zip(names, usages) if u < 0.02]
        results.append((not low, f"candidates({atk!r}) 使用率都 ≥ 2%",
                        "" if not low else f"这些低于 2%：{low[:3]}"))

    # 自定义参数
    try:
        r2 = suggest.candidates(chaos, "Ice", min_usage=0.05, top=3)
        results.append((len(r2) <= 3, "candidates(..., min_usage=0.05, top=3) 尊重参数",
                        "" if len(r2) <= 3 else f"返回了 {len(r2)} 条"))
        low2 = [n for n, u in r2 if u < 0.05]
        results.append((not low2, "min_usage=0.05 生效", "" if not low2 else f"{low2[:3]}"))
    except NotImplementedError:
        results.append((False, "自定义参数", "函数还是 NotImplementedError"))
    except Exception as e:  # noqa: BLE001
        results.append((False, "自定义参数", f"抛异常 {type(e).__name__}: {e}"))

    # ---------------- 汇报 ----------------
    print()
    failed = [r for r in results if not r[0]]
    for ok, label, msg in results:
        if ok:
            print(f"  {PASS}  {label}")
        else:
            print(f"  {FAIL}  {label}")
            if msg:
                print(f"        {msg}")
    print()
    if not failed:
        print(f"全部通过（{len(results)} 项）。截图发我，我给你下一步。")
        raise SystemExit(0)
    print(f"{len(failed)} / {len(results)} 项没过。按顺序修，改完再跑一次。")
    raise SystemExit(1)


if __name__ == "__main__":
    main()