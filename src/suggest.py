"""补强建议模块 —— 你自己写。

这个模块解决一个真实问题：
    「我的队伍弱火，环境里前 40 名中谁既能抗火、使用率又不低？」

写完之后跑验收器检查：
    python -m src.check_suggest

规则
----
1. 只改这个文件，别改 check_suggest.py（那是验收器）
2. 可以用现成的 src/dex.py 和 src/typechart.py，别自己重写属性表
3. 卡住了先看报错信息，报错会告诉你是第几个测试没过
4. 实在写不出来再看答案——答案在 README 里，但别看太早
"""
from __future__ import annotations

from . import dex
from .typechart import TYPES, effectiveness


def resists(name: str, attack_type: str) -> float:
    """返回这只宝可梦承受 attack_type 的倍率。

    参数
    ----
    name : chaos 里的名字，例如 "Garchomp"、"Charizard-Mega-Y"
    attack_type : 18 种属性之一，例如 "Fire"、"Ice"

    返回
    ----
    浮点数：
        0.0        免疫
        0.25 / 0.5 抗性
        1.0        普通
        2.0 / 4.0  弱点

    提示
    ----
    - 用 dex.types_of(name) 拿到这只宝可梦的属性列表（可能是 1 个或 2 个）
    - 用 effectiveness(attack_type, 属性列表) 算倍率，这个函数已经写好了
    - 名字查不到时，dex.types_of 会返回空列表，这时应该抛 ValueError

    例子
    ----
    resists("Garchomp", "Ice")    -> 4.0   （龙/地，双重弱冰）
    resists("Garchomp", "Fire")   -> 0.5   （龙抗火）
    resists("Kingambit", "Psychic") -> 0.0  （恶免疫超能）
    """
    # TODO: 你来实现（大约 5 行）
    raise NotImplementedError("resists 还没写")


def candidates(chaos: dict, attack_type: str, min_usage: float = 0.02,
               top: int = 8) -> list[tuple[str, float]]:
    """从环境数据里筛出能抗住 attack_type 的宝可梦。

    参数
    ----
    chaos :  loader.load_chaos() 读出来的字典，结构是
             {"info": {...}, "data": {名字: {"usage": 0.36, ...}, ...}}
    attack_type : 要抗的属性
    min_usage   : 使用率下限，低于这个的不要（默认 0.02 即 2%）
    top         : 最多返回几只

    返回
    ----
    列表，每项是 (名字, 使用率)，按使用率从高到低排。

    判断标准
    --------
    「抗住」= 倍率严格小于 1，也就是 0 / 0.25 / 0.5 都算，
    1.0（普通）和 2.0 以上（弱点）不算。

    提示
    ----
    1. 遍历 chaos["data"].items()，每项是 (名字, 该宝可梦的数据字典)
    2. 使用率在 mon["usage"] 里，是 0~1 的小数
    3. 先用 min_usage 过滤，再判断抗性，能少算很多
    4. 排序：用 sorted() 配合 key=lambda，或者先 append 再 sort
    5. 名字查不到的（dex.types_of 返回空列表）直接跳过，别抛异常

    例子
    ----
    res = candidates(chaos, "Ice")
    print(res[0])   # 大概是 ("Corviknight", 0.0396) 之类的
    """
    # TODO: 你来实现（大约 10 行）
    raise NotImplementedError("candidates 还没写")