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
│   ├── pokedex.json            # 属性/种族值/特性
│   ├── moves.json              # 招式类型与威力
│   └── rules/abilities.json    # 特性规则（属性免疫/减伤/换算/场地）
├── src/
│   ├── loader.py               # chaos json → pandas
│   ├── dex.py                  # 名字 → 属性（含 Mega 形态）
│   ├── typechart.py            # 18×18 属性克制表
│   ├── abilities.py            # 特性规则层：读 json，应用防御/进攻效果
│   ├── threat.py               # 环境火力：每种属性在环境里有多强
│   ├── fields.py               # 场地/天气分布与交互
│   ├── report.py               # 环境分析 CLI
│   ├── team.py                 # 队伍分析 CLI（理论 + 实战）
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
output/team_danger.png    理论 vs 实战 双栏对比
```

**两个分数的区别（这是本项目的核心）**

| 分数 | 算法 | 回答的问题 |
|---|---|---|
| **理论危险分** | `弱点人数×2 − 抗性 − 免疫×2` | 属性表上你怕什么 |
| **实战风险分** | `(弱点人数/6) × 该属性环境火力` | 实战里真的会被什么打 |

**只看属性表会误判。** 示例：一支队伍 3 只弱冰，理论危险分最高，
但 VGC 环境里冰属性的火力只有 27%（前 60 名里冰属性宝可梦只有 2 只），
所以实战风险只排第 6。真正该防的是**火**——队伍 2 只弱火，环境火力 100%。

### 环境火力怎么算

`src/threat.py` 从对战统计反推每种属性的出现强度：

```
presence[T] = Σ 每只宝可梦的使用率 × 它真正能用 T 属性打人的程度
```

"打人程度"由三件事决定：

1. **招式威力**：按 `basePower/80` 加权（上限 1.5），40 威力的 Fake Out 不等于 120 威力的 Close Combat
2. **特性转换属性**：见下
3. **本系加成**：转换后的属性与自身属性相同时 ×1.5

**不假设"是这个属性就一定有输出"。** Indeedee-F 是普通属性，但它只带
Follow Me / Helping Hand / Trick Room，一个普通攻击招式都没有，
不该被算成普通属性的威胁。

### 特性规则层（`src/abilities.py` + `data/rules/abilities.json`）

**机制写在 json 里，代码只负责读规则和套规则。** 加新特性 = 加一条数据，不改逻辑。

环境里 212 种特性，前 45 名里真正影响对位的分四类：

| 类别 | 规则文件字段 | 环境代表 |
|---|---|---|
| 属性免疫 | `immune_types` | **Levitate 21.5%**、Flash Fire 5.6%、Water Absorb、Volt Absorb、Sap Sipper、Earth Eater |
| 属性减伤 | `type_mult` | Thick Fat（火/冰 ×0.5）、Heatproof、Water Bubble、Fluffy（火 ×2）、Dry Skin（火 ×1.25） |
| 效果拔群减伤 | `se_mult` | Filter / Solid Rock / Prism Armor（×0.75） |
| 满血减伤 | `full_hp_mult` | Multiscale / Shadow Shield（×0.5） |
| **天气压制** | `negates_weather` | **Cloud Nine 无天气（1.18%）**、Air Lock 气闸（环境中暂无） |

**Levitate 是这里最关键的一条**：环境里 21.5% 的宝可梦无视地面系。
不算这个，队伍分析会把它们当"弱地面"，把 Ground 的风险算高一大截。

同一只宝可梦的不同配置可能带不同特性，所以按 `Abilities` 里各特性的占比
加权算期望值——结果可能是小数（比如 50% 带 Levitate 的宝可梦对地面的
期望"免疫数"是 0.5）。

**纯数值增幅不进对位计算**（硬爪 ×1.3、技术高手、无防守、威吓等），
它们不改变属性关系，单独记在规则文件的 `offense_boost` 里备查。

### 场地与天气（`src/fields.py`）

```
python -m src.fields
```

三件必须搞清的事：

1. **异名之间互相覆盖，同名不会——但同名也不延长。** rain 和 sun 互抢；
   两个都开 rain 不冲突，可是**回合数不会重置**，第二只冗余设定者换不来更多时间。
   环境数据佐证：同场地设定者共现率几乎为 0（Indeedee-F 与 Indeedee 0.00%，
   Pelipper 与 Politoed 0.12%）。第二名同名设定者只有"被抢掉后能再抢回来"的备用价值。
2. **抢赢的是速度更慢的那只。** 特性在登场时触发，同回合后动的最后触发。
   快的场地手先开会被慢的顶掉，**慢速队反而更能控场**。
3. **Levitate / 飞行系不吃地面场地效果，但仍会触发场地种子道具**
   （种子看场地是否存在，不看脚下是否接地）。

**设定者强度**（有多少宝可梦会开它，不等于它能待多久）：

| 场地/天气 | 相对强度 | 位置率 | 属性加成 |
|---|---:|---:|---|
| 青草场地 | 100% | 6.0% | 草 ×1.3 |
| 精神场地 | 69% | 4.2% | 超能 ×1.3 |
| 下雨 | 62% | 3.7% | 水 ×1.5 |
| 晴天 | 60% | 3.6% | 火 ×1.5 |
| 沙暴 | 28% | 1.7% | — |
| 下雪 | 24% | 1.4% | 冰 ×1 |
| 电气场地 | 18% | 1.1% | 电 ×1.3 |

**被抢风险与站稳率**（已按慢速抢快折算）：

| 场地/天气 | 对手带竞品 | 我方均速 | 竞品均速 | 我方更慢 | 站稳率 | 期望加成 |
|---|---:|---:|---:|---|---:|---:|
| 下雨 | 24% | 67 | 84 | 是 | **94%** | 1.47 |
| 青草场地 | 19% | 85 | 91 | 是 | 92% | 1.28 |
| 沙暴 | 31% | 67 | 80 | 是 | 91% | 1.00 |
| 精神场地 | 25% | 88 | 87 | 否 | 87% | 1.26 |
| 晴天 | 25% | 81 | 76 | 否 | 86% | 1.43 |
| 电气场地 | 35% | 101 | 86 | 否 | 75% | 1.22 |
| 下雪 | 32% | 111 | 72 | 否 | **71%** | 1.00 |

**下雪和电气场地最容易掉**——不是因为设定者少，而是因为它们的设定者速度快
（九尾阿罗拉、雷丘系），一上场就被慢速对手顶掉。雨天由 Pelipper / Politoed
这类慢速手控制，所以最稳。

**场地会被拆掉（招式，不是特性）**

除了被对手抢，场地还能被招式直接清除：

| 招式 | 效果 | 环境里谁带 |
|---|---|---|
| **冰旋** Ice Spinner | 命中后场地消失 | Weavile(13%)、Starmie-Mega(10%) |
| **铁滚轮** Steel Roller | 130 威力，命中后场地消失，**没有场地时会失败** | Metagross-Mega(11%) |
| 清除雾 Defog | 顺带清场地 | 环境中无人带 |
| 换场 Court Change | **把你的场地直接换给对手** | 环境中无人带 |

规则在 `data/rules/fields.json`。按"对手 4 只里至少带一只"折算，
**拆场地概率 0.46%**——很低，但会从场地站稳率里扣掉。

铁滚轮有个特点：**没有场地时它会失败**，所以它属于"你开场地我才用"的
反制型招式，针对性比冰旋强。

天气没有对应的拆解招式，只能被新天气覆盖或被 Cloud Nine 压制。

**天气会被压制**

`Cloud Nine`（无天气）/ `Air Lock`（气闸）在场时，**所有天气效果失效**：
天气伤害归零、Swift Swim 等加速失效、气象球变回普通系。

注意它**消除不了**天气本身——对手开的晴天仍然"存在"，只是不起作用，
所以你抢回来的天气也不会因此变成你独占。

环境里 `cloudnine` 加权 1.18%（Drampa、Altaria），按"对手 4 只里至少带一只"
折算，**天气被压制的概率约 0.79%**，影响很小但已计入气象球的属性分布。
这条**不影响场地**。

**已知限制**

- 速度用图鉴基础速度，未计性格与努力值
- 抢赢概率用双方加权平均速度的逻辑斯蒂近似，实际是逐只对位
- **持续回合数不建模**：特性天气通常 5 回合，到点自行消失。
  `hold_rate` 只回答"会不会被对手抢掉"，不含"自己到期"

### 场地是共用的，不是开的人独占

**这是最容易吃亏的一点。** 天气/场地对全场生效，所以开场地可能是在给对手送强化。

```
python -m src.fields     # 第 4 节：场地共用风险
```

晴天之下，对手的气象球全部变成火属性：

| 场地 | 气象球变成 | 谁受益（* = 本系加成） |
|---|---|---|
| **晴天** | **火** | Charizard-Mega-Y\*(23%)、**Pelipper(22%)**、Politoed(20%)、Torkoal\*(15%) |
| 下雨 | 水 | Charizard-Mega-Y(23%)、**Pelipper\*(22%)**、Politoed\*(20%)、Torkoal(15%) |
| 青草场地 | 草 | 全部非本系 |
| 精神场地 | 超能 | 全部非本系 |

**实战后果**：Pelipper（水/飞）在**你的晴天**里，气象球变成火属性，
打你的草系（比如轰擂金刚猩）是效果拔群。等于你开的晴天帮对手补了一手火系打击面。

`threat.py` 里气象球/大地波动不再排除，而是按"环境里各场地出现的概率"把贡献
拆到对应属性上：

```
weatherball   Normal 60%, Water 14%, Fire 14%, Rock 7%, Ice 6%
terrainpulse  Normal 58%, Grass 22%, Psychic 16%, Electric 4%
```

两者属性池不同（气象球不会变草/超能，大地波动不会变火/水），所以分开算。
场地是共用的，这个分布同时代表"我方会被什么打"。

### 特性会把招式属性转掉（重要）

| 特性 | 效果 | 环境里的代表 |
|---|---|---|
| `aerilate` 飞行皮肤 | 普通系招式 → 飞行系，威力 ×1.2 | Salamence-Mega（巨声）、Pinsir-Mega |
| `pixilate` 妖精皮肤 | 普通系招式 → 妖精系，威力 ×1.2 | Sylveon、Gardevoir-Mega、Altaria-Mega |
| `refrigerate` 冰冻皮肤 | 普通系招式 → 冰系 | Glalie-Mega |
| `galvanize` | 普通系招式 → 电系 | — |
| `normalize` | 所有招式 → 普通系 | — |

**不处理这个会算错。** 超级暴飞龙 100% 带飞行皮肤，巨声 23% 使用率，
按普通系算会让 Normal 虚高、Flying 虚低。修正前后：

| 属性 | 修正前 | 修正后 |
|---|---:|---:|
| Normal | 69% | **37%** |
| Fairy | 41% | **63%** |
| Flying | 34% | **47%** |

同一只宝可梦的多套配置可能带不同特性，所以按 `Abilities` 里各特性的占比加权。

### 已知限制

- **气象球/大地波动按场地的出现概率分配属性**，不再排除（见下节）。但天气没有
  常驻时的 100 威力翻倍没有建模，权重仍按基础 50 威力算。
- **Fake Out 这类低威力但带效果的招式**按威力计权（40 BP → 0.5），
  它的价值在先行+畏缩而不是伤害，所以无法完全反映其战术意义。
- 低使用率宝可梦的对位胜率样本太少，`checks` 的胜率需要配合使用率一起看。

---

## 官方资料包校验（2026-10-21 版）

拿到一份第三方整理的 **Pokémon Champions M-C 双打资料包**（适用期 2026-09-09 ~ 2026-12-02），
含官方 mod 源码、JSON 数据库和 262 条参赛名单。已用它逐项校验本项目：

### 已校验为正确

| 项 | 结果 |
|---|---|
| 18×18 属性克制表 | **324 组倍率全部一致，0 处差异** |
| 名单与数据一致性 | 官方 262 条 + 82 个 Mega 形态 = 344；chaos 数据 323 只，差额是没人用的冷门形态，无矛盾 |

### 已据此修正

**1. Champions 专属特性，之前完全漏掉的**

| 特性 | 效果 | 持有者（环境使用率） |
|---|---|---|
| `dragonize` 龙皮肤 | 一般招式→龙属性 ×1.2 | 超级大力鳄 0.26% |
| `eelevate` 鳗鳗高升 | 免疫地面 + 撒菱/毒菱/黏黏网/Arena Trap | 超级麻麻鳗鱼王 0.28% |
| `megasol` 超级日光 | **只对自己生效的伪晴天**，不参与抢天气 | 超级大竺葵 1.24% |
| `firemane` 火焰鬃毛 | 火属性攻击进攻 ×1.5 | 超级火炎狮 1.13% |
| `piercingdrill` 贯穿钻 | 接触招式穿透保护，伤害 1/4 | 超级龙头地鼠 0.20% |
| `spicyspray` 辣椒喷发 | 受击时使攻击者灼伤 | 超级狠辣椒 1.04% |
| `mimicry` 拟态 | 随场地改变自身属性 | 伽勒尔泥巴鱼 0.03% |
| `unseenfist` 无形拳 | 接触招式穿透保护 | 超级泥偶巨人 0.37% |

**2. Champions 改过威力的招式（25 个），之前用的是 Showdown 原版数值**

| 招式 | 原威力 | Champions |
|---|---:|---:|
| 流星突击 Meteor Assault | 150 | **170** |
| 铁头 Psyshield Bash | 70 | **90** |
| 热带踢 Trop Kick | 70 | **85** |
| 星碎 Astral Barrage | 120 | **110** |
| 钻啄 Drill Run 系 hyperdrill | 100 | **120** |
| （其余 20 个见 `data/rules/moves_override.json`） | | |

`src/threat.py` 的 `load_moves()` 现在会自动套用这份覆盖表，
所以环境火力权重用的是 Champions 数值而不是朱紫数值。

### 辣椒喷发的真相

之前只知道它存在。资料包给了准确定义：

> **受到攻击伤害时使攻击者灼伤**（不要求接触）

**这是状态效果，不是伤害修正。** 但灼伤会让攻击方物理攻击减半，
所以算伤害时必须连带调整对方输出——你那个半成品机器人「无视辣椒喷发」，
错在漏掉了这条链式影响，不是漏了一条伤害公式。

### 还没做的

- `data/residual_events.json` 和 `residual_order_index.json` 里有**回合末事件注册顺序**，
  这是做伤害计算器/模拟器时的关键，目前没用上
- 官方 mod 里 `unseenfist`、`naturalcure`、`regenerator`、`emergencyexit` 等有改动，
  与属性对位无关，暂未纳入
- 资料包声明自己「不是可执行模拟器」，未覆盖的事件标为 U 级边缘

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
- [x] 队伍弱点分析（属性矩阵 + 理论危险分）
- [x] **环境加权实战风险分**（`src/threat.py`）
- [x] **特性规则层**（`src/abilities.py` + `data/rules/abilities.json`，覆盖 22 条防御类）
- [x] **场地天气分布**（`src/fields.py`）
- [ ] 伤害计算器（对接 Showdown damage-calc 规则）
- [ ] 规则数据化（json 配置，不硬编码特性）
- [ ] QQ 机器人接入

---

## 参考

- Smogon 统计目录：<https://www.smogon.com/stats/>
- 伤害计算权威实现：<https://github.com/smogon/damage-calc>
- GitHub 镜像（下载 release / 仓库）：`https://gh-proxy.com/https://github.com/...`