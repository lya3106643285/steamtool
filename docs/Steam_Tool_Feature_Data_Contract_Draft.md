# Steam Tool 功能数据契约（Feature Contract）

**文档状态：Draft / 当前讨论冻结版**  
**用途：定义 Steam Tool 三个核心功能 `games`、`library`、`wishlist` 的输出结构、Record 组合方式、Summary 与 Coverage 语义。**  
**依赖：本文件建立在《Steam Tool 基础数据契约》之上，不重复定义基础数据块内部字段。**

---

# 1. 总体分层

Steam Tool 当前数据契约分为两层：

```text
Base Data Contract
├── Meta
├── GameIdentity
├── Market
├── Ownership
├── Wishlist
├── Playtime
├── Achievements
├── Price
└── Bundles

Feature Contract
├── GamesResult
├── LibraryResult
└── WishlistResult
```

基础层负责定义：

> 单一数据块“能表达什么”。

功能层负责定义：

> 某个业务功能“组合哪些基础块、如何组织结果、如何汇总”。

---

# 2. 统一 Result 外壳

三个 Feature 原则上统一采用：

```text
FeatureResult
├── schema_version
├── run
├── summary
├── coverage        # 按 Feature 需要决定是否存在
├── errors
└── items
```

字段顺序固定：

```text
schema_version
→ run
→ summary
→ coverage（如适用）
→ errors
→ items
```

先放本次 Result 的描述、摘要、完整性和错误信息，最后再放数据主体 `items`。

---

# 3. `schema_version`

```text
string
```

表示本项目输出契约版本。

Feature Contract 与 Base Data Contract 共同受该版本管理。

发生破坏性结构变化时必须升级版本。

---

# 4. `run`

统一表示一次 Feature 执行。

```text
run
├── run_id
├── feature
├── started_at
├── finished_at
├── subject_steamid
└── status
```

示例：

```json
{
  "run": {
    "run_id": "abc123",
    "feature": "games",
    "started_at": "2026-10-07T02:10:00Z",
    "finished_at": "2026-10-07T02:10:08Z",
    "subject_steamid": "76561199834898167",
    "status": "ok"
  }
}
```

## 4.1 `feature`

当前允许：

```text
games
library
wishlist
```

## 4.2 `status`

运行级状态：

```text
ok
partial
failed
cancelled
```

语义：

- `ok`：本 Feature 按当前契约完成。
- `partial`：存在有效结果，但部分 item 或必要数据块未完整取得。
- `failed`：没有形成可用业务结果，或核心流程失败。
- `cancelled`：用户主动终止本次运行。

---

# 5. `errors`

根级统一错误集合：

```text
errors: Error[]
```

数据块通过：

```text
meta.error_id
```

引用根级错误对象。

例如：

```json
{
  "errors": [
    {
      "error_id": "err_xxx",
      "code": "NETWORK_TIMEOUT",
      "source": "get_player_achievements",
      "appid": 292030,
      "message": "..."
    }
  ]
}
```

原则：

1. 同一个错误对象不在多个 Record 中重复完整保存。
2. 数据块只保存 `error_id`。
3. Shell 输入语法错误不进入这里。
4. 用户在交互阶段主动放弃的非法查询项不进入业务 JSON。

---

# 6. Games Feature Contract

`games` 是完整单游戏数据查询功能。

用户输入一个或多个游戏名称，系统解析为 AppID 后，为每个目标拼装完整 `GameRecord`。

## 6.1 GamesResult

```text
GamesResult
├── schema_version
├── run
├── summary
├── errors
└── items[]
    └── GameRecord
```

当前 `GamesResult` **不要求 `coverage`**。

原因：

> `games` 查询目标由用户显式指定，不承担“整个库存 / 整个愿望单是否抓全”的集合完整性语义。

单个数据块的完整性由各自 `Meta.state` 表达。

## 6.2 GameRecord

`GameRecord` 是当前最完整的单游戏标准记录。

所有基础数据块默认参与。

```text
GameRecord
├── status
├── identity
├── market
├── ownership
├── wishlist
├── playtime
├── achievements
├── price
└── bundles
```

也就是说正常 `games` 查询默认启用：

```text
identity
market
ownership
wishlist
playtime
achievements
price
bundles
```

不根据“可能用不到”裁剪字段。

## 6.3 GameRecord.status

```text
ok
partial
failed
```

用途：

> 对该 GameRecord 内部各数据块状态进行一次聚合，便于外层快速判断单个游戏是否完整。

语义：

- `ok`：当前契约要求的数据块均达到可接受状态。
- `partial`：已形成有效 GameRecord，但存在部分数据缺失。
- `failed`：无法形成有意义的目标游戏记录。

具体聚合规则由实现阶段定义，但不得与各数据块 `Meta.state` 冲突。

## 6.4 Achievements 特殊规则

`Achievements` 数据块本身始终存在。

默认查询：

```text
total
unlocked
completion_ratio
```

默认：

```text
items = null
```

逐项成就明细的获取由 Feature / CLI 执行逻辑中的显式参数控制。

例如未来可能存在：

```text
games --achievements
```

但：

> 参数名称、CLI 语法和调度方式不属于本数据契约。

数据契约只规定：

```text
items = null
```

或：

```text
items = Achievement[]
```

均为合法结构。

## 6.5 GamesResult.summary

Games 的 Summary 保持克制，只做运行结果计数。

```text
summary
├── game_count
├── ok_count
├── partial_count
└── failed_count
```

示例：

```json
{
  "summary": {
    "game_count": 5,
    "ok_count": 3,
    "partial_count": 1,
    "failed_count": 1
  }
}
```

不在 Games Summary 中加入：

```text
总价格
总时长
平均成就率
```

这些属于后续分析层。

---

# 7. Library Feature Contract

`library` 用于导出本人库存、家庭共享相关库存信息，以及本人对应的游玩和成就数据。

当前 v1 坚持扁平库存，不建立 App 与 DLC、Bundle、父子 App 之间的关系图。

关系图属于未来版本考虑范围。

## 7.1 LibraryResult

```text
LibraryResult
├── schema_version
├── run
├── summary
├── coverage
├── errors
└── items[]
    └── LibraryRecord
```

## 7.2 LibraryRecord

```text
LibraryRecord
├── status
├── identity
├── ownership
├── playtime
└── achievements
```

相对完整 `GameRecord`，明确删除：

```text
market
wishlist
price
bundles
```

Library v1 也不新增：

```text
dlcs
parent_app
bundle_relationship
```

如果现有上游数据天然返回 DLC 为独立 App，则其作为独立 `LibraryRecord` 出现，并由：

```text
identity.app_type
```

标识类型。

当前契约不负责表达：

> 该 DLC 属于哪个本体。

## 7.3 LibraryRecord.status

与 `GameRecord.status` 相同：

```text
ok
partial
failed
```

用于快速表示单个库存记录的最终状态。

---

# 8. LibraryResult.summary

Library 是统计型功能，因此 Summary 比 Games 更丰富。

当前结构：

```text
summary
├── total_count
├── self_owned_count
├── family_owned_count
├── family_available_count
│
├── played_count
├── unplayed_count
├── playtime_unknown_count
├── played_ratio
├── unplayed_ratio
│
├── total_playtime
├── playtime_unit
│
├── ranking_limit
├── top_total_playtime[]
└── top_last_2weeks_playtime[]
```

## 8.1 `total_count`

```text
integer
```

本次 Library 结果中的 `LibraryRecord` 总数。

## 8.2 Ownership 汇总

### `self_owned_count`

本人确认拥有的 App 数量。

### `family_owned_count`

当前家庭其他成员确认拥有的 App 数量。

注意：

> 同一个 App 可以同时计入 `self_owned_count` 和 `family_owned_count`。

两者不是互斥分类。

### `family_available_count`

本人当前确认可通过家庭共享取得的 App 数量。

## 8.3 Played / Unplayed

定义：

```text
played:
playtime.total > 0
```

```text
unplayed:
playtime.total = 0
```

```text
unknown:
playtime.total = null
```

因此：

```text
played_count
unplayed_count
playtime_unknown_count
```

必须分别统计。

不能把未知时长自动归入“没玩过”。

## 8.4 Played Ratio

比例只针对已知 Playtime 的 App：

```text
known_playtime_count
= played_count + unplayed_count
```

```text
played_ratio
= played_count / known_playtime_count
```

```text
unplayed_ratio
= unplayed_count / known_playtime_count
```

若分母为 0，则比例为：

```text
null
```

## 8.5 Total Playtime

```text
total_playtime
```

只累加：

```text
playtime.total != null
```

的记录。

同时保存：

```text
playtime_unit
```

当前通常为：

```text
minutes
```

不得在存在未知 Playtime 时，把已知部分总和描述成“绝对完整的账户总时长”。

完整性由 `coverage.playtime` 配套说明。

---

# 9. Library Playtime Ranking

Summary 增加两个简单排行榜：

```text
top_total_playtime
top_last_2weeks_playtime
```

## 9.1 `ranking_limit`

```text
integer
```

表示本次排行榜最多保留多少项。

Feature / CLI 实现可决定默认：

```text
5
```

或：

```text
10
```

具体默认值不由基础数据契约固定。

## 9.2 `top_total_playtime`

按：

```text
playtime.total
```

降序排列。

单项建议结构：

```text
rank
appid
name
playtime
unit
```

示例：

```json
{
  "rank": 1,
  "appid": 292030,
  "name": "The Witcher 3: Wild Hunt",
  "playtime": 18342,
  "unit": "minutes"
}
```

## 9.3 `top_last_2weeks_playtime`

按：

```text
playtime.last_2weeks
```

降序排列。

结构与累计时长排行一致。

## 9.4 排序规则

```text
null
```

不参与正常排序。

```text
0
```

是合法已知值。

只有当前 N 个位置不足时，0 才可能进入排行榜。

---

# 10. LibraryResult.coverage

Library 必须保留 Coverage。

Coverage 用于回答：

> 本次 Library 数据到底取得了多大范围，哪些维度完整，哪些维度存在缺失。

Coverage 不负责业务统计。

当前至少包括：

```text
coverage
├── self_library
├── family_library
├── playtime
└── achievements
```

建议结构：

```json
{
  "coverage": {
    "self_library": {
      "state": "ok",
      "complete": true,
      "count": 125
    },
    "family_library": {
      "state": "ok",
      "complete": true,
      "count": 294
    },
    "playtime": {
      "complete": false,
      "known_count": 137,
      "missing_count": 282
    },
    "achievements": {
      "complete": false,
      "known_count": 310,
      "missing_count": 109
    }
  }
}
```

`complete = true` 只表示：

> 在当前已知 API 契约和声明查询范围内完整。

不得扩张解释为：

> 已证明覆盖 Steam 账号全部历史许可证、所有下架内容或所有私人数据。

---

# 11. Library 总开销字段：暂不进入 v1

当前讨论中过一次：

```text
account_spend
total_spend
```

但尚未确认它是否来自当前 Library 数据源，以及其准确语义。

因此 v1：

```text
不进入 LibraryResult.summary
```

后续需要先确认：

1. Steam 是否存在稳定可读取的数据源。
2. 认证方式。
3. 货币单位。
4. 返回值表示账户累计消费、充值金额，还是其他口径。
5. 是否与 Library 内游戏实际购买成本存在可比性。

确认后再通过后续 schema 版本加入。

---

# 12. Wishlist Feature Contract

`wishlist` 用于导出用户当前愿望单，并提供与购买决策相关的信息。

## 12.1 WishlistResult

```text
WishlistResult
├── schema_version
├── run
├── summary
├── coverage
├── errors
└── items[]
    └── WishlistRecord
```

## 12.2 WishlistRecord

```text
WishlistRecord
├── status
├── identity
├── market
├── ownership
├── wishlist
├── price
└── bundles
```

明确不包含：

```text
playtime
achievements
```

各模块职责：

```text
identity
→ 这是什么 App

market
→ 当前查询地区是否已发行、是否可以正常取得

ownership
→ 本人 / 家庭是否已经拥有或可共享

wishlist
→ 是否在愿望单、优先级、加入时间

price
→ 当前价格信息

bundles
→ 与该 App 相关的 Bundle 信息
```

## 12.3 WishlistRecord.status

```text
ok
partial
failed
```

语义与其他 Record 一致。

---

# 13. WishlistResult.summary

Wishlist Summary 保持简单。

当前至少包括：

```text
summary
├── total_count
└── price_ranking[]
```

## 13.1 `total_count`

```text
integer
```

当前愿望单结果条目总数。

## 13.2 `price_ranking`

对愿望单中的 App 按当前价格做简单排序。

单项建议结构：

```text
rank
appid
name
type
price
currency
```

示例：

```json
{
  "rank": 1,
  "appid": 123,
  "name": "Game A",
  "type": "paid",
  "price": 1200,
  "currency": "CNY"
}
```

## 13.3 排序价格来源

付费 App：

```text
price.final
```

免费 App：

```text
0
```

但仍必须通过：

```text
price.type = "free"
```

明确其免费性质。

不能仅依靠：

```text
price.final = 0
```

判断免费。

价格未知：

```text
price.final = null
```

不作为 0 处理。

当前建议：

> 已知价格按低到高排列，未知价格放在已知价格之后。

---

# 14. WishlistResult.coverage

Wishlist 必须保留 Coverage。

当前至少需要说明：

```text
coverage
├── wishlist
├── market
├── ownership
├── price
└── bundles
```

其职责是回答：

> 当前 Wishlist 条目本身是否完整，以及每类附加数据有多少成功取得、多少缺失。

具体字段可以采用：

```text
state
complete
known_count
missing_count
```

等稳定统计。

示例：

```json
{
  "coverage": {
    "wishlist": {
      "state": "ok",
      "complete": true,
      "count": 37
    },
    "price": {
      "complete": false,
      "known_count": 35,
      "missing_count": 2
    },
    "bundles": {
      "complete": false,
      "known_count": 30,
      "missing_count": 7
    }
  }
}
```

---

# 15. 三个 Record 的组合关系

当前冻结版本：

```text
GameRecord
├── status
├── identity
├── market
├── ownership
├── wishlist
├── playtime
├── achievements
├── price
└── bundles
```

```text
LibraryRecord
├── status
├── identity
├── ownership
├── playtime
└── achievements
```

```text
WishlistRecord
├── status
├── identity
├── market
├── ownership
├── wishlist
├── price
└── bundles
```

关系可理解为：

```text
GameRecord
├── LibraryRecord 所需字段
└── WishlistRecord 所需字段
```

但：

> Library 与 Wishlist 不只是简单字段切片，它们还拥有各自独立的集合级 Summary 与 Coverage 语义。

---

# 16. 当前明确不属于 Feature 数据契约的逻辑

以下内容已讨论，但属于运行 / CLI / Resolver 逻辑。

## 16.1 Games 名称输入规则

当前方向：

```text
"Game A","Game B"
"Game C"

<空行>
```

规则：

1. 游戏名称必须使用 ASCII 英文双引号 `"` 包围。
2. 一个游戏名称对应一对英文双引号。
3. 同一行使用 ASCII 英文逗号 `,` 分隔。
4. 普通换行继续收集。
5. 收集阶段空行结束输入并开始查询。
6. 不直接接受 AppID 或 Steam URL 作为用户查询内容。

## 16.2 输入错误重输

输入语法错误应在 Shell 立即指出：

```text
哪一项错误
原始错误项
错误类型
```

例如：

```text
"Hades",Noita,"Outer Wilds"
```

应指出：

```text
Noita
QUERY_NAME_NOT_QUOTED
```

然后提示：

```text
请重新输入该项（直接回车表示放弃该项）：
```

纠错状态下：

```text
空行
```

表示只放弃当前错误项。

这类错误不进入 Feature JSON。

## 16.3 Achievements 明细开关

`GameRecord` 与 `LibraryRecord` 都保留完整 `Achievements` 结构。

默认：

```text
achievements.items = null
```

后续可通过显式参数开启逐项成就明细。

该参数：

```text
属于 Feature / CLI 执行逻辑
```

不是数据契约字段。

## 16.4 Library 排行榜 Top-N

`ranking_limit` 存入 Summary 表示本次结果实际采用的 N。

但：

> 默认 N 是 5 还是 10，属于 Feature / CLI 默认配置，不属于结构契约。

---

# 17. 当前暂缓设计项

以下内容不进入 v1：

```text
DLC / Parent-App 关系图
Bundle 与 DLC 的关系推理
完整 Steam App 图结构
Stats
账户总消费 / 总开销
复杂购买历史
```

原则：

> 当前版本优先形成稳定、扁平、可验证的数据输出。

只有在后续业务确实需要，并确认存在稳定数据源后，再通过 schema 升级加入。

---

# 18. 当前 Feature Contract 总览

```text
GamesResult
├── schema_version
├── run
├── summary
├── errors
└── items[]
    └── GameRecord
        ├── status
        ├── identity
        ├── market
        ├── ownership
        ├── wishlist
        ├── playtime
        ├── achievements
        ├── price
        └── bundles
```

```text
LibraryResult
├── schema_version
├── run
├── summary
│   ├── inventory counts
│   ├── played / unplayed
│   ├── total playtime
│   └── Top-N playtime rankings
├── coverage
├── errors
└── items[]
    └── LibraryRecord
        ├── status
        ├── identity
        ├── ownership
        ├── playtime
        └── achievements
```

```text
WishlistResult
├── schema_version
├── run
├── summary
│   ├── total_count
│   └── price_ranking
├── coverage
├── errors
└── items[]
    └── WishlistRecord
        ├── status
        ├── identity
        ├── market
        ├── ownership
        ├── wishlist
        ├── price
        └── bundles
```

---

# 19. 下一阶段

基础数据契约和 Feature Contract 确认后，下一阶段应定义：

```text
API → Base Data Block 映射
```

即明确：

1. 每个基础数据块由哪个 / 哪些 API 提供。
2. 调用依赖关系。
3. API 返回如何转换为基础契约字段。
4. 哪些 API 是 Feature 的必要来源。
5. `Meta.state` 如何判定。
6. `coverage.complete` 如何判定。
7. 失败与降级规则。
8. 缓存与 `fetched_at` 的使用方式。
9. 并发、重试、限流仍由既有运行架构负责，不混入数据契约。
