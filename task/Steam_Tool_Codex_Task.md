# Steam Tool 数据契约与运行逻辑实现任务书

## 1. 任务目标

基于当前已经冻结的三份设计文档，实现 Steam Tool 当前阶段的数据契约代码和已经明确的运行逻辑，并将两份 Draft 数据契约整理为一份正式的数据契约文档。

本次任务的核心目标有三个：

1. 在本地 `schema/` 目录完成基础数据契约与 Feature 数据契约的 Python 实现。
2. 按运行逻辑说明实现当前已经明确的 Games 输入处理与 Achievements 明细查询控制逻辑。
3. 将两份 Draft 数据契约整理、合并为正式文档：`docs/data_contract.md`。

本任务以现有设计文档为需求来源，不重新设计数据契约。

---

## 2. 输入文档索引

实现前必须完整阅读以下三份文档。

### 2.1 运行逻辑

```text
@Steam_Tool_Runtime_Logic_Notes.md
```

用途：

- Games 查询输入规则
- Games 输入解析
- 输入错误定位与纠错
- `COLLECTING_INPUT / CORRECTING_ITEM` 状态区别
- CLI 输入错误与业务错误的边界
- Achievements 明细按参数开启的执行逻辑

如果仓库内该文件存在具体路径，以仓库现有文件为准，不要为了匹配任务书额外复制一份。

### 2.2 Feature 数据契约

```text
docs/Steam_Tool_Feature_Data_Contract_Draft.md
```

用途：

- `GamesResult`
- `LibraryResult`
- `WishlistResult`
- 三种 Record 的字段组合
- Run
- Summary
- Coverage
- Record status
- Library 排行榜
- Wishlist 价格排序
- Feature 级 errors

### 2.3 Base 数据契约

```text
docs/Steam_Tool_Base_Data_Contract_Draft.md
```

用途：

- `Meta`
- `GameIdentity`
- `Market`
- `Ownership`
- `Wishlist`
- `Playtime`
- `Achievements`
- `Achievement`
- `Price`
- `Bundles`
- `Bundle`

上述两份 Draft 是本次实现的数据结构依据。

---

## 3. 实现原则

### 3.1 先检查现有仓库

修改代码之前先检查：

```text
项目目录结构
现有 schema/model 定义
pyproject.toml / requirements
现有 CLI
现有 Feature Runner
现有 Resolver
现有错误系统
现有 API client / ports
现有测试
```

尽量复用当前项目已有架构。

不要仅为了本任务重新建立第二套：

```text
Error System
Runtime
Client
Feature Runner
CLI Framework
```

### 3.2 文档是契约来源，不自行重设计

对于文档已经冻结的内容：

```text
字段名称
字段层级
null 语义
-1 / 0 / false 等特殊语义
Record 组成
Result 组成
Summary 组成
Coverage 组成
```

必须按照文档实现。

不要因为实现方便而擅自：

```text
改字段名
删除字段
合并字段
增加冗余字段
修改 null 语义
改变 Record 组合
```

### 3.3 不虚构尚未定义的 API → Data Block 映射

当前文档尚未正式定义完整的：

```text
API → Base Data Block
```

映射。

因此：

- 已有 Repository / Port / Client 能提供的数据，按照现有实现接入。
- 不要为了填满契约而擅自寻找新的 Steam API。
- 不要新增网页爬虫作为 fallback。
- 不要自行定义未经文档确认的新数据源。
- 不要把 API mapping 设计扩展成本次任务的主体。

如果现有代码不足以确定某项 API 来源，应保留清晰的 TODO 或现有降级路径，而不是凭猜测实现。

---

## 4. `schema/base.py`

创建或完善：

```text
schema/base.py
```

该文件实现：

```text
Meta

GameIdentity
Market
Ownership
Wishlist

Playtime
PlaytimePlatform

Achievement
Achievements

Price

Bundle
Bundles
```

具体字段、字段语义和 null / sentinel 规则全部以：

```text
docs/Steam_Tool_Base_Data_Contract_Draft.md
```

为准。

### 4.1 模型实现方式

首先检查项目当前是否已经使用：

```text
Pydantic
dataclass
TypedDict
其他 schema/model framework
```

优先保持现有技术栈一致。

如果已经使用 Pydantic，则继续使用现有 Pydantic 版本和风格。

不要仅为了本任务新增大型依赖。

### 4.2 必须保留的关键语义

实现时特别注意以下区别：

```text
null
false
0
-1
```

不能混用。

例如：

```text
Playtime.total = 0
```

表示确认没有游玩时间。

```text
Playtime.total = null
```

表示无法确认。

Achievements 中：

```text
total = -1
unlocked = -1
```

表示已经确认该 App 不存在成就系统。

而：

```text
items = null
```

只表示当前结果没有逐项成就明细。

这两个语义必须严格区分。

### 4.3 Meta

`Meta` 必须支持契约定义的状态：

```text
ok
partial
unavailable
not_applicable
not_requested
```

不得把：

```text
not_requested
```

和：

```text
unavailable
```

合并。

`source` 和 `fetched_at` 需要兼容单来源与多来源结构。

如果 Draft 对某种边界情况没有冻结具体 Python 类型，不要比文档施加更强的无依据约束。

### 4.4 Price 与 Bundle Price

普通 `Price` 是完整基础数据块：

```text
Price
└── meta
```

但是：

```text
Bundle.price
```

只复用 Price 的业务字段：

```text
type
currency
initial
final
```

不能再次嵌套一个独立 `Meta`。

建议通过共享的内部 price value model / helper 消除代码重复，但最终序列化结构必须符合契约。

---

## 5. `schema/feature.py`

创建或完善：

```text
schema/feature.py
```

实现 Feature 层的数据结构。

至少包括：

```text
Run

GameRecord
LibraryRecord
WishlistRecord

GamesSummary
LibrarySummary
WishlistSummary

PlaytimeRankingItem
WishlistPriceRankingItem

LibraryCoverage
WishlistCoverage

GamesResult
LibraryResult
WishlistResult
```

以及实现 Result 所必需的已有 Error 类型引用或适配。

---

## 6. Record 组成

严格按照 Feature Contract 实现。

### 6.1 GameRecord

```text
status
identity
market
ownership
wishlist
playtime
achievements
price
bundles
```

这是当前完整的单游戏标准记录。

不得为了减少请求而从 schema 中删除默认字段。

### 6.2 LibraryRecord

```text
status
identity
ownership
playtime
achievements
```

不得加入：

```text
market
wishlist
price
bundles
```

当前版本也不要新增：

```text
parent_app
dlcs
bundle_relationship
```

### 6.3 WishlistRecord

```text
status
identity
market
ownership
wishlist
price
bundles
```

不得加入：

```text
playtime
achievements
```

---

## 7. Result 结构

字段顺序按照契约保持：

```text
schema_version
run
summary
coverage   # 只有需要的 Feature
errors
items
```

其中：

```text
GamesResult
```

不包含 Coverage。

```text
LibraryResult
WishlistResult
```

包含 Coverage。

如果所使用的模型框架可以稳定控制序列化顺序，应保持上述顺序。

---

## 8. schema_version

检查项目是否已经存在统一的：

```text
SCHEMA_VERSION
```

如果已经存在，复用它。

如果不存在：

- 建立唯一的 schema version 常量。
- 不要在多个文件散落 magic string。
- 具体正式版本表示方式应在最终 `docs/data_contract.md` 中同步说明。

不要让代码版本和文档版本脱节。

---

## 9. Feature 派生逻辑

除 schema 定义外，实现当前契约已经明确规定的纯业务派生逻辑。

这类逻辑应尽可能实现为：

```text
纯函数
builder
aggregator
serializer helper
```

而不是散落在 CLI 中。

### 9.1 Games Summary

计算：

```text
game_count
ok_count
partial_count
failed_count
```

只进行运行结果计数。

不要额外加入：

```text
总价格
总时长
平均成就率
```

### 9.2 Library Summary

实现：

```text
total_count

self_owned_count
family_owned_count
family_available_count

played_count
unplayed_count
playtime_unknown_count

played_ratio
unplayed_ratio

total_playtime
playtime_unit

ranking_limit
top_total_playtime
top_last_2weeks_playtime
```

#### Played / Unplayed

严格区分：

```text
playtime.total > 0      → played
playtime.total == 0     → unplayed
playtime.total is None  → unknown
```

`unknown` 不能算入 `unplayed`。

比例分母只使用：

```text
played_count + unplayed_count
```

分母为 0：

```text
played_ratio = null
unplayed_ratio = null
```

### 9.3 Library Playtime Ranking

实现：

```text
top_total_playtime
top_last_2weeks_playtime
```

规则：

```text
降序
null 不参与正常排序
0 是有效已知值
```

实际 Top-N：

```text
ranking_limit
```

写入 Summary。

默认 N 属于 Feature / CLI 配置，不属于 Base Contract。

如果项目已有配置机制，放入现有配置。

不要将默认值硬编码到基础 schema。

### 9.4 Wishlist Summary

实现：

```text
total_count
price_ranking
```

排序规则：

```text
已知价格：低 → 高
未知价格：排在已知价格后面
```

免费 App：

```text
price.type == "free"
```

排序价格视为 0。

但是：

```text
price.final == 0
```

不能单独用于判断免费产品，因为付费产品可能存在 100% 折扣。

---

## 10. Coverage

Coverage 是集合完整性描述，不是业务统计。

不要把 Summary 和 Coverage 混在一起。

### 10.1 Library Coverage

至少实现：

```text
self_library
family_library
playtime
achievements
```

按照契约生成：

```text
state
complete
count
known_count
missing_count
```

等对应字段。

只使用当前查询范围判断 `complete`。

不得把：

```text
complete = true
```

解释为已经证明覆盖账户全部历史 Steam License。

### 10.2 Wishlist Coverage

至少包括：

```text
wishlist
market
ownership
price
bundles
```

负责表达：

```text
愿望单主体是否完整
各附加数据块成功多少
缺失多少
```

---

## 11. Record / Run Status 聚合

实现统一的状态聚合 helper，避免三个 Feature 各写一套互相不一致的判断。

Record：

```text
ok
partial
failed
```

Run：

```text
ok
partial
failed
cancelled
```

必须遵循现有 Data Block `Meta.state`。

至少满足：

- `not_applicable` 本身不应被视为错误。
- 一个有效 Record 存在部分必要数据缺失时应为 `partial`。
- 无法形成有意义的目标 Record 时为 `failed`。
- 所有契约要求的数据达到可接受状态时为 `ok`。
- Achievements 没有逐项查询，`items = null` 本身不得导致 Record 变成 `partial`。

---

## 12. Error 引用机制

Feature 根级保留：

```text
errors[]
```

Base Data Block 使用：

```text
meta.error_id
```

引用根级规范化 Error。

禁止把同一个完整错误对象复制进每一个 Record。

如果项目已经存在规范化 Error model：

```text
直接复用 / 适配
```

不要创建第二套 Error system。

---

## 13. Games 输入运行逻辑

按照：

```text
@Steam_Tool_Runtime_Logic_Notes.md
```

实现 Games 查询输入处理。

该逻辑不得放入：

```text
schema/base.py
schema/feature.py
```

应该放入当前项目已有：

```text
CLI
Input Parser
Resolver
```

对应层。

### 13.1 输入格式

只接受：

```text
"Game Name"
```

多个名称：

```text
"Hades","Noita"
```

支持：

```text
"Hello, World"
```

所以禁止简单：

```python
line.split(",")
```

应使用 CSV-style parsing 或等价的明确 parser。

支持 CSV 双双引号转义：

```text
"Game ""Special"" Edition"
```

解析为：

```text
Game "Special" Edition
```

### 13.2 不接受的查询形式

Games 用户输入不直接接受：

```text
AppID
Steam Store URL
未加 ASCII 双引号的名称
中文引号
弯引号
```

### 13.3 Parser 错误

至少保留以下错误码：

```text
QUERY_NAME_NOT_QUOTED
QUERY_INVALID_QUOTE
QUERY_UNCLOSED_QUOTE
QUERY_EMPTY_NAME
QUERY_UNEXPECTED_CHAR
QUERY_INVALID_ESCAPE
```

这些错误属于：

```text
CLI / Parser
```

不得写入最终：

```text
FeatureResult.errors[]
```

---

## 14. 输入纠错状态机

必须明确实现两个状态：

```text
COLLECTING_INPUT
CORRECTING_ITEM
```

### COLLECTING_INPUT

```text
空行
→ 结束整批输入
→ 开始查询
```

### CORRECTING_ITEM

```text
空行
→ 放弃当前错误项
→ 返回后续流程
```

绝对不能用一个统一的：

```text
if not line:
    break
```

处理两种情况。

错误项重新输入后：

```text
合法
→ 替换原项
→ 加入查询队列
```

再次错误：

```text
继续纠错
```

空行：

```text
仅放弃该项
```

---

## 15. Resolver 边界

Parser 只负责语法。

Resolver 负责：

```text
Game Name → AppID
```

不要把 AppID 解析伪装成用户输入功能。

保持：

```text
CLI Input
→ Parser
→ Resolver
→ Feature
```

职责分离。

---

## 16. Achievements 明细查询逻辑

Games 和 Library 默认：

```text
Achievements
├── total
├── unlocked
├── completion_ratio
└── items = null
```

默认不主动请求完整：

```text
Achievement[]
```

### 16.1 显式 detail 开关

Games 与 Library 支持显式参数开启 Achievements 明细。

具体 CLI 参数名称优先检查现有实现。

如果当前不存在，可采用与设计文档一致、语义明确的形式，例如：

```text
--achievements
```

但不要把该开关加入数据契约字段。

它属于：

```text
Feature Runner / CLI / Query Scheduling
```

### 16.2 开启后

显式开启时才请求完整：

```text
Achievement[]
```

并填入：

```text
achievements.items
```

### 16.3 三种状态必须区分

#### 有成就系统，未请求明细

```text
total = 正常值
unlocked = 正常值
completion_ratio = 正常值
items = null
```

#### 已确认无成就系统

```text
total = -1
unlocked = -1
completion_ratio = null
items = null
meta.state = not_applicable
```

#### 请求明细但明细查询失败

按照现有：

```text
Meta
Error
Record status
Run status
```

机制降级。

不得因为逐项成就接口失败而无条件丢弃整个 GameRecord / LibraryRecord。

---

## 17. 正式数据契约文档

完成代码实现后，根据：

```text
docs/Steam_Tool_Base_Data_Contract_Draft.md
docs/Steam_Tool_Feature_Data_Contract_Draft.md
```

生成正式：

```text
docs/data_contract.md
```

### 17.1 文档要求

`data_contract.md` 应把 Base Contract 和 Feature Contract 合并为一个正式规范。

建议结构：

```text
1. Document Status / Version
2. Contract Scope
3. Common Semantics
4. Base Data Contract
   4.1 Meta
   4.2 GameIdentity
   4.3 Market
   4.4 Ownership
   4.5 Wishlist
   4.6 Playtime
   4.7 Achievements
   4.8 Price
   4.9 Bundles

5. Feature Contract
   5.1 Shared Result Structure
   5.2 Run
   5.3 Error Reference
   5.4 Games
   5.5 Library
   5.6 Wishlist

6. Null / Sentinel Semantics
7. Schema Versioning
8. Out of Scope
```

### 17.2 从 Draft 转为正式规范

整理时：

- 删除 `Draft / 当前讨论冻结版` 等草稿状态。
- 删除已经失效的“下一阶段再讨论”等过程性语言。
- 把已经冻结的“建议结构”改写成正式契约定义。
- 合并 Base / Feature 中重复说明。
- 保留所有仍然有效的边界条件。
- 确保文档字段名称和实际 Python schema 完全一致。

### 17.3 不把运行逻辑混入正式 Data Contract

以下内容不要展开写入正式 `data_contract.md`：

```text
CLI 输入交互
纠错 UI
Parser 状态机
Achievements CLI 参数语法
网络重试
限流
并发
Runtime Debug
API 调度
```

可以在 Out of Scope 中简短说明这些属于运行层，并引用：

```text
Steam_Tool_Runtime_Logic_Notes.md
```

### 17.4 Draft 文件处理

以下两个文件作为本次任务的输入资料：

```text
docs/Steam_Tool_Feature_Data_Contract_Draft.md
docs/Steam_Tool_Base_Data_Contract_Draft.md
```

默认不要删除。

新的正式有效契约为：

```text
docs/data_contract.md
```

除非仓库已有明确的文档淘汰规则，否则不要额外重命名或删除 Draft。

---

## 18. 测试要求

本任务必须补充或更新自动测试。

优先使用项目现有测试框架。

### 18.1 Base Schema 测试

至少验证：

```text
Meta.state 合法状态
null / false / 0 / -1 不被错误归并
Playtime platform sentinel
Achievement.items nullable
无成就系统表示
Bundle.price 不含 Meta
SteamID dictionary key 保持字符串
included_apps 的 AppID key 保持字符串
```

### 18.2 Feature Schema 测试

验证：

```text
GameRecord 字段组成
LibraryRecord 字段组成
WishlistRecord 字段组成

GamesResult 无 coverage
LibraryResult 有 coverage
WishlistResult 有 coverage

Result 序列化结构
```

### 18.3 Summary 测试

Library 至少覆盖：

```text
played
unplayed
unknown playtime

ratio denominator
zero denominator

total playtime

total ranking
last_2weeks ranking

null 排除
0 合法
Top-N
```

Wishlist 至少覆盖：

```text
paid price
free game
100% discounted paid game
unknown price
known-before-unknown ordering
```

### 18.4 Games Parser 测试

至少覆盖：

```text
"Hades"
"Hades","Noita"
"Hades","Hello, World","Noita"
"Game ""Special"" Edition"
```

以及：

```text
"Hades",Noita,"Outer Wilds"
```

必须能够精确定位：

```text
第 2 项
Noita
QUERY_NAME_NOT_QUOTED
```

还需测试：

```text
中文引号
弯引号
未闭合引号
空名称
非法转义
意外字符
AppID
Steam URL
```

### 18.5 输入状态测试

必须测试：

```text
COLLECTING_INPUT + 空行
→ 结束输入
```

和：

```text
CORRECTING_ITEM + 空行
→ 只跳过当前项
```

同时测试错误项：

```text
错误
→ 重输仍错误
→ 再次提示
→ 重输正确
→ 正常加入队列
```

### 18.6 Achievements Detail 测试

至少测试：

#### 默认

```text
games
library
```

不得请求完整明细，最终：

```text
items = null
```

#### 开启

```text
detail enabled
```

才执行逐项成就查询并填充：

```text
Achievement[]
```

#### 无成就系统

保持：

```text
total = -1
unlocked = -1
completion_ratio = null
items = null
```

#### 明细查询失败

确认：

```text
Error 被记录
Meta 正确降级
Record 不被无条件丢弃
```

---

## 19. 本次禁止范围

除非当前仓库已有相关实现且为了兼容必须修改，否则不要在本任务中扩展：

```text
DLC / Parent-App 图关系
完整 Steam App Graph
Stats
账户总消费
购买历史
新的 Steam API 调研
新的网页爬虫
新的缓存架构
新的 Runtime Debug 架构
新的网络重试框架
新的限流框架
GUI
Web UI
```

本任务是：

```text
落实已经冻结的数据契约
+
落实已经冻结的两项运行逻辑
```

不是重新设计 Steam Tool。

---

## 20. 推荐执行顺序

按以下顺序工作：

```text
1. 阅读三份设计文档
2. 检查仓库现状和依赖
3. 对照文档列出当前实现差异
4. 实现 schema/base.py
5. 实现 schema/feature.py
6. 实现 Feature summary / coverage / status helper
7. 实现 Games Parser / correction state
8. 实现 Achievements detail switch
9. 接入现有 Feature Runner / CLI
10. 编写和更新测试
11. 运行完整测试
12. 生成 docs/data_contract.md
13. 最后再次核对代码与正式文档的一致性
```

不要先写正式文档再根据文档猜代码。

最终：

```text
代码实现
```

和：

```text
docs/data_contract.md
```

必须互相一致。

---

## 21. 完成标准

只有同时满足以下条件才视为任务完成。

### Schema

```text
[ ] schema/base.py 已实现
[ ] schema/feature.py 已实现
[ ] Base 字段与 Draft 一致
[ ] Feature Record 组合与 Draft 一致
[ ] null / false / 0 / -1 语义未被破坏
```

### Runtime

```text
[ ] Games 多行输入可用
[ ] 一行多个 quoted name 可用
[ ] 游戏名内部逗号可用
[ ] escaped quote 可用
[ ] 可以精确定位错误 item
[ ] 错误 item 可重复重输
[ ] correction 空行只跳过当前 item
[ ] collecting 空行结束整批输入
[ ] Parser Error 不进入业务 errors[]
```

### Achievements

```text
[ ] 默认不请求完整 items
[ ] detail 开启后才查询 items
[ ] 无成就系统语义正确
[ ] detail 查询失败可以降级
```

### Feature

```text
[ ] Games Summary 正确
[ ] Library Summary 正确
[ ] Library Ranking 正确
[ ] Library Coverage 正确
[ ] Wishlist Summary 正确
[ ] Wishlist Price Ranking 正确
[ ] Wishlist Coverage 正确
[ ] Record / Run status 聚合一致
```

### Documentation

```text
[ ] docs/data_contract.md 已生成
[ ] Base + Feature 已合并
[ ] 不再标记为 Draft
[ ] 文档与实际 schema 一致
[ ] CLI / Runtime 细节没有污染 Data Contract
```

### Quality

```text
[ ] 新增 / 修改测试通过
[ ] 项目原有测试未被破坏
[ ] lint / type check（如果项目已有）通过
[ ] 没有无关的大规模重构
[ ] 没有引入未经需求确认的新数据源
```

---

## 22. 最终汇报要求

完成后不要只回复“已完成”。

给出简短实施报告：

```text
1. 修改 / 新增了哪些文件
2. base.py 实现了哪些模型
3. feature.py 实现了哪些模型与派生逻辑
4. Games 输入逻辑修改位置
5. Achievements detail 开关修改位置
6. 新增了哪些测试
7. docs/data_contract.md 是否生成
8. 执行了哪些测试 / lint / type check
9. 是否仍存在因现有仓库或文档未定义而无法完成的事项
```

如果发现设计文档之间存在真正冲突：

```text
不要自行选一个版本静默实现。
```

先以最小改动方式保留现有行为，并在最终报告中准确指出：

```text
冲突位置
两边定义
当前采用的临时处理
```

不得借机重新设计整个契约。
