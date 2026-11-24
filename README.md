# champions-lab

宝可梦**《宝可梦 Champions》**环境数据分析工具。基于 Smogon 公开的天梯对战统计，做三件事：

1. **环境分析** —— 谁在用、怎么配、被谁压
2. **队伍弱点分析** —— 输入 6 只，输出整队的弱点/抗性分布
3. **可复用数据层** —— 任意格式、任意月份都能接

> 主攻 Champions，朱/紫只作对照。

---

## 数据来源

| 内容 | 地址 |
|---|---|
| 月度对战统计 | `https://www.smogon.com/stats/{YYYY-MM}/chaos/{格式}-{分段}.json` |
| 宝可梦图鉴（属性/种族值/特性） | `https://play.pokemonshowdown.com/data/pokedex.json` |

已下载的数据（2026-10）：

| 文件 | 对局数 | 宝可梦数 |
|---|---:|---:|
| `gen9championsvgc2026regmc-1500.json` | **1,649,648** | 323 |
| `gen9championsou-1500.json` | 106,694 | 306 |
| `gen9championsou-1630.json` | 106,694 | 267 |
| `gen9championsou-0.json` | 106,694 | 323 |
| `gen9championsuu-1500.json` | 1,160 | 253 |
| `gen9championsmegaevolutionbattle-1500.json` | 940 | 143 |
| `pokedex.json` | — | 1518（含 101 个 Mega 形态） |

**VGC 2026 规则 M-C 是赛事主格式，165 万场对局，数据量最大。**

---

## 快速开始

```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 下载数据（已有会跳过）
python -m src.fetch

# 3. 环境分析（默认 VGC 2026 Reg M-C）
python -m src.report

# 4. 换单打 OU，并指定分析 Rillaboom
python -m src.report gen9championsou-1500.json Rillaboom

# 5. 队伍弱点分析（名字用 Showdown 写法）
python -m src.team Rillaboom Sneasler Incineroar Kingambit Archaludon Indeedee-F
```

⚠️ 带空格或后缀的名字要加引号：`"Charizard-Mega-Y"`、`"Slowking-Galar"`

Windows PowerShell 若报编码错误，先跑 `chcp 65001`。

---

## 目录结构

```
champions-lab/
├── data/
│   ├── gen9champions*.json     # 对战统计
│   └── pokedex.json            # 属性/种族值/特性
├── src/
│   ├── loader.py               # chaos json → pandas
│   ├── dex.py                  # 名字 → 属性（含 Mega 形态）
│   ├── typechart.py            # 18×18 属性克制表
│   ├── report.py               # 环境分析 CLI
│   ├── team.py                 # 队伍弱点分析 CLI
│   └── fetch.py                # 下载
├── output/                     # PNG + CSV
└── requirements.txt
```

---

## 用法细节

### 环境分析输出什么

```
output/top20_usage.png    使用率 Top20
output/loadout.png        使用率第一的道具/招式/特性拆解
output/checks.png         什么能压住它（对位胜率）
output/teammates.png      常见队友
output/usage_ranking.csv  完整使用率表
```

控制台还会打印性格/努力值配置和被谁压制。

### 队伍弱点分析输出什么

```
output/team_matrix.png    18 属性 × 队伍成员 热力图
output/team_danger.png    整队危险分
```

**危险分算法**：`弱点人数 × 2 − 抗性人数 − 免疫人数 × 2`

分数越高说明该属性越容易打穿整队。≥3 只被克时会单独提示。

---

## 数据结构备忘

chaos JSON 里几个容易踩的点：

1. **`Items` / `Moves` / `Abilities` 的值是加权计数，不是百分比**，必须除以总和。
2. `usage` 是 0~1 的比例。
3. `Spreads` 的键形如 `Adamant:32/32/0/0/2/0`，第一个是性格，后面 6 个是努力值。
4. `Checks and Counters` 是 `{对手: {n: 样本, p: 对位胜率, d: 优势程度}}`。
5. `Teammates` 是共现计数，除以自身 `Raw count` 可近似成共现率。

### 名字映射

chaos 用 `Scovillain-Mega`，pokedex 用 `scovillainmega`。
`dex.toid()` 负责转换：小写 + 去掉所有非字母数字。

已测：VGC 323 只、OU 306 只，**映射覆盖率 100%**。

---

## 已发现的 Champions 环境事实

VGC 2026 Reg M-C（165 万场）使用率 Top 5：

```
1. Rillaboom       36.13%
2. Sneasler        33.20%
3. Incineroar      29.40%
4. Kingambit       20.23%
5. Archaludon      18.48%
```

单打 Champions OU（10.7 万场）Top 5：

```
1. Corviknight     39.56%
2. Garchomp        36.37%
3. Samurott-Hisui  28.28%
4. Slowking-Galar  21.78%
5. Glimmora        19.06%
```

**两个格式的环境完全不同**，不能混用数据。

Mega 形态确认在环境中活跃：`Charizard-Mega-Y` 16.0%、`Raichu-Mega-Y` 15.0%、
`Garchomp-Mega-Z` 12.7%、`Golisopod-Mega` 12.5%。

---

## 路线图

- [x] 数据层（多格式、多分段）
- [x] 图鉴层（属性/种族值/Mega 形态）
- [x] 环境分析（使用率/配置/克制/队友）
- [x] 队伍弱点分析（属性矩阵 + 危险分）
- [ ] 伤害计算器（对接 Showdown damage-calc 规则）
- [ ] 规则数据化（json 配置，不硬编码特性）
- [ ] QQ 机器人接入

---

## 参考

- Smogon 统计目录：<https://www.smogon.com/stats/>
- 伤害计算权威实现：<https://github.com/smogon/damage-calc>
- GitHub 镜像（下载 release / 仓库）：`https://gh-proxy.com/https://github.com/...`