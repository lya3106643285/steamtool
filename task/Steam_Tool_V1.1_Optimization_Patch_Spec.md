# Steam Tool V1.1 工程优化补丁任务书

**文档类型：Codex 开发任务书 / Patch Spec**  
**版本：V1.1**  
**目标：在不扩展业务功能、不重构 Family 链路的前提下，修正 library 工作流的状态语义、请求规划、错误归类与运行统计，并降低无意义 enrichment 请求。**  
**基线样本：`20261003T172350723743Z_library_38b353ad68ed.json`**

---

## 0. 给 Codex 的执行约束

本次是对 V1.0 demo 的**工程校正补丁**，不是第二次架构重写。

必须遵守：

1. **不要新增业务功能。**
   - 不新增 GUI、Web 服务、数据库、Agent、MCP、推荐系统或销量分析。
   - 不增加新的 Steam 写入能力。
2. **不要重构已经跑通的 Family 鉴权与读取链路。**
   - `get_family_group_for_user`
   - `get_shared_library_apps`
   - `STEAM_FAMILY_ACCESS_TOKEN`
   目前已有真实数据证明链路可用，本轮只允许补测试、日志和状态统计，不要顺手改写认证方式。
3. **不要改变现有 `start` / `stop` 入口语义。**
4. **不要把缺失能力、上游无数据和真正程序失败混成同一种 failed。**
5. **不要根据 App 名称猜能力并永久跳过请求。**
   - `Dedicated Server`、`SDK`、`Demo` 等名称只能用于诊断，不作为唯一 capability 证据。
6. **并发仍然保留。**
   - 优化目标不是改回串行，而是减少无意义请求，并让有依赖关系的请求按依赖调度。
7. **所有认证信息继续禁止进入业务 JSON、runtime debug、异常文本和测试快照。**
8. 修改前先检查当前仓库、现有测试和未提交改动；不得覆盖用户已有实现。
9. 交付时明确区分：
   - 已实现；
   - 离线测试通过；
   - 使用真实 Steam 数据验证；
   - 尚未验证。

---

# 1. 当前真实运行基线

当前 `library` 工作流已经完成一次真实导出。该次运行的关键指标：

```text
feature: library
status: partial

wall_duration_ms: 840601.953
约等于: 14 分钟

http_attempts: 1668
logical_requests: 1668
retries: 0
rate_limits: 0
cache_hits: 0

tasks.total: 419
tasks.success: 25
tasks.failed: 394
tasks.skipped: 0
tasks.cancelled: 0

collections:   3465.45 ms
enrichment: 837042.03 ms
library:      840528.99 ms
```

这说明当前瓶颈几乎全部位于 enrichment 阶段。

但 `394 failed` **不能解释为系统发生了 394 次真正故障**。

当前 errors 中已经观察到大量如下情况：

```text
No explicit achievement schema available
Store does not provide this app in the query context
GetPlayerAchievements -> HTTP 400
GetUserStatsForGame -> HTTP 400
```

这些情况中相当一部分属于：

- 该 App 本身没有对应能力；
- Steam 当前查询上下文不提供数据；
- API 对该 App 不适用；
- 某个可选 enrichment 数据不存在；

而不是：

- Python 崩溃；
- 网络断开；
- token 失效；
- Steam 5xx；
- 重试耗尽；
- 响应结构损坏。

因此本轮第一优先级是**修正语义，再谈性能**。

---

# 2. 已确认不能回归的能力

本轮不得破坏以下已经实际跑通的数据链。

## 2.1 Family 数据

当前真实导出已经成功取得：

```text
family_group.state = ok
family.state = ok
family.count = 419
```

并且能够表达：

```text
owned_by_self
owned_by_other_family_members
available_via_family
owner_steamids
shared_exclusion_reason
```

已有实际样本能够区分：

```text
owned_by_self = false
owned_by_other_family_members = true
available_via_family = true
```

这意味着 Family token 与家庭库链路已经具备真实可用性。

**本轮不改变这条链路。**

## 2.2 个人游戏行为数据

当前真实导出已经成功取得过：

- `playtime.total_minutes`
- `last_2weeks_minutes`（接口有返回时）
- `last_played_at`
- 平台时长
- achievement schema
- player achievements
- unlock time
- game-defined stats
- store details

例如真实样本中存在：

```text
Portal 2
  playtime = ok
  achievements = ok

Left 4 Dead
  playtime = ok
  achievements = ok
  stats = ok
  store = ok

Cities: Skylines
  owned_by_self = false
  owned_by_other_family_members = true
  available_via_family = true
```

这些能力必须作为回归测试基准。

---

# 3. 本次修改目标

本轮只处理四件事：

1. **重新定义完成结果状态。**
2. **增加 enrichment capability / request planning。**
3. **建立 schema 与 achievements / stats 的依赖调度。**
4. **补足 runtime debug 的性能与状态统计。**

---

# 4. 状态体系修正

## 4.1 区分“运行态”和“完成结果态”

运行过程中仍允许：

```text
pending
running
cancelled
```

任务完成后，结果分类统一为：

```text
success
not_applicable
data_unavailable
failed
```

### `success`

请求或逻辑成功执行，并取得了足够支持当前字段的数据。

### `not_applicable`

有明确证据表明该能力对于当前 App 不适用，因此不应该继续查询下游接口。

典型情况：

```text
schema 明确表示没有 achievements
schema 明确表示没有 stats
已确认 app 类型属于当前能力白名单之外
```

`not_applicable` **不是 error**，不得计入 `failed`。

### `data_unavailable`

请求本身没有发生需要视作系统故障的问题，但上游没有提供所需数据，或者查询上下文不能提供该数据。

例如：

```text
Store does not provide this app in the query context
接口明确返回没有可用数据
当前地区没有商店详情
```

`data_unavailable` 允许记录 error/event 说明原因，但不得计入真正的系统失败。

### `failed`

只用于真正异常，例如：

```text
NETWORK_TIMEOUT 且达到最大尝试次数
连接失败且达到重试上限
HTTP 5xx 达到重试上限
响应不是预期 JSON / 结构损坏
认证失效导致本来应该工作的核心请求失败
内部程序异常
序列化或写入失败
```

**禁止仅因为“某个游戏没有 schema / stats / store data”就记为 failed。**

---

# 5. 错误码与结果状态解耦

`error_handler.py` 继续负责：

- 错误分类；
- 标准错误码；
- 是否重试；
- backoff；
- 是否终止当前请求、App 或整个 workflow。

但：

> 错误码不等于任务完成状态。

建议保留现有错误体系，并至少增加/明确以下语义：

```text
CAPABILITY_NOT_APPLICABLE
DATA_UNAVAILABLE
NETWORK_TIMEOUT
NETWORK_ERROR
RATE_LIMITED
AUTH_REQUIRED
AUTH_EXPIRED
ACCESS_DENIED
UPSTREAM_UNAVAILABLE
RESPONSE_INVALID
OUTPUT_WRITE_FAILED
INTERNAL_ERROR
```

只有真正故障才映射到：

```text
outcome = failed
```

---

# 6. Enrichment 请求规划

当前行为近似：

```text
拿到 419 个 App
    ↓
对大量 App 尝试：
    store
    schema
    achievements
    stats
```

V1.1 改成：

```text
collection
    ↓
AppID 合并 / 去重
    ↓
生成 enrichment plan
    ↓
Stage A: capability discovery
    ↓
Stage B: conditional enrichment
    ↓
merge
    ↓
persist
```

---

# 7. Capability discovery 规则

## 7.1 禁止依赖名字猜测

不能简单写：

```python
if "SDK" in name:
    skip()
```

或：

```python
if "Dedicated Server" in name:
    skip()
```

名称规则只能用于 debug 提示。

## 7.2 可以使用的证据

优先级：

```text
1. 已验证并已规范化的 upstream app_type
2. Store detail 返回的 type
3. GetSchemaForGame 返回的实际 capability
4. 已有当前运行中的成功响应
5. 缓存中的已验证 capability（未来才启用持久缓存）
```

如果 `app_type` 枚举还没有完成可靠映射，则不要因为一个未知数值直接跳过请求。

未知情况保持：

```text
capability = unknown
```

而不是猜成：

```text
capability = false
```

---

# 8. Schema 驱动的依赖调度

这是本轮最关键的性能修改。

当前不应该对所有 App 无条件并行执行：

```text
schema
achievements
stats
```

改为：

## Stage A

不同 App 之间继续并发。

单个 App 首先执行：

```text
get_schema_for_game
```

`get_app_details` 与 schema 没有业务依赖，可以与 schema 并行，但仍服从各自 rate scope。

## Stage B：Achievements

只有在 schema 提供足够证据表明该游戏存在 achievements 时：

```text
schedule get_player_achievements
```

如果 schema 明确表示无 achievements：

```text
achievements.state = not_applicable
```

并且：

```text
DO NOT CALL get_player_achievements
```

## Stage B：Stats

只有在 schema 中存在可查询的 stats 定义或其他已验证证据表明该 App 支持 user stats 时：

```text
schedule get_user_stats_for_game
```

否则：

```text
stats.state = not_applicable
```

并且：

```text
DO NOT CALL get_user_stats_for_game
```

## Schema 本身不可用时

必须区分：

### 情况 A：明确不存在 schema

例如 adapter 已有明确证据：

```text
No explicit achievement schema available
```

可以将 schema 归入 `not_applicable` 或 `data_unavailable`，并据实际证据决定是否停止 achievements / stats 下游请求。

### 情况 B：网络失败

例如：

```text
timeout
connection error
5xx exhausted
```

此时：

```text
schema -> failed
```

但不能因为 schema 网络失败就推断：

```text
achievements = not_applicable
stats = not_applicable
```

下游应该标记为显式依赖失败，例如：

```text
data_unavailable / dependency_failed
```

**不要把“没查到”解释成“不支持”。**

---

# 9. 并发要求

本轮优化不得改成逐 App 串行。

并发仍由统一的 request executor 控制：

```text
global concurrency
rate_scope
per-source RPS
cooldown
retry execution
```

业务层只负责建立任务依赖。

推荐流水线：

```text
schema(App1) done
    → schedule achievements(App1)

schema(App2) no achievements
    → mark not_applicable

schema(App3) done
    → schedule stats(App3)
```

不要先等 419 个 schema 全部结束以后再统一进入下一阶段。

---

# 10. 请求去重

同一 run 中必须保证以下 key 只执行一次：

```text
schema:
(appid, language)

player_achievements:
(subject_steamid, appid, language)

user_stats:
(subject_steamid, appid)

store:
(appid, language, store_country)
```

如果多个业务数据源同时引用同一 AppID：

```text
self-owned
family-owned
recent
```

只能共享同一份 enrichment future/result。

V1.1 只要求：

```text
in-run dedup
```

不要求引入 SQLite 或长期缓存。

---

# 11. Runtime Debug 修改

`scripts/runtime_debug.py` 继续作为监督层。

## 11.1 Outcome 统计

旧结构：

```json
"tasks": {
  "success": 25,
  "failed": 394
}
```

改成至少：

```json
"tasks": {
  "total": 419,
  "pending": 0,
  "running": 0,
  "success": 0,
  "not_applicable": 0,
  "data_unavailable": 0,
  "failed": 0,
  "cancelled": 0
}
```

这里的 task 计数语义必须在代码中固定。

如果 `task` 指的是 App enrichment task，则：

```text
一个 App = 一个 task
```

如果要统计每个 API operation，则单独增加：

```text
operations
```

不要再把“419 个 App”和“1668 个 HTTP 请求”混在同一个统计概念里。

## 11.2 API 级请求统计

新增类似：

```json
"http_by_api": {
  "get_schema_for_game": {
    "logical_requests": 0,
    "attempts": 0,
    "success": 0,
    "not_applicable": 0,
    "data_unavailable": 0,
    "failed": 0,
    "retries": 0
  }
}
```

至少分别统计：

```text
get_schema_for_game
get_player_achievements
get_user_stats_for_game
get_app_details
```

## 11.3 Planner 统计

新增：

```json
"enrichment_plan": {
  "input_apps": 419,
  "schema_scheduled": 0,
  "store_scheduled": 0,
  "achievements_scheduled": 0,
  "stats_scheduled": 0,
  "achievements_skipped_not_applicable": 0,
  "stats_skipped_not_applicable": 0,
  "dedup_hits": 0
}
```

字段名可小幅调整，但语义必须等价。

---

# 12. Top-level workflow status 修正

## `ok`

核心 collection 数据成功取得，能够形成可信的 library 快照。

允许：

- 某些 App 没有 achievements；
- 某些 App 没有 stats；
- 某些内部/历史 App 没有商店详情；
- optional enrichment 为 `not_applicable`；
- optional enrichment 为 `data_unavailable`。

这些情况本身**不应让整个 library workflow 变成 partial**。

## `partial`

核心数据存在明确缺失，使结果存在重要不确定性，例如：

```text
owned library 成功，family library 失败
或
family library 成功，owned library 失败
或
关键身份 / ownership 数据无法确认
```

## `failed`

无法生成有意义的 library 主体结果。

## `cancelled`

用户主动调用 stop 或正常取消。

---

# 13. Item 级状态语义

单个游戏仍保留：

```text
ownership
wishlist
playtime
achievements
stats
store
```

每个块独立表达状态。

例如：

```json
{
  "appid": 215,
  "achievements": {
    "state": "not_applicable",
    "items": []
  },
  "stats": {
    "state": "not_applicable",
    "items": []
  },
  "store": {
    "state": "data_unavailable",
    "data": null
  }
}
```

但必须基于证据分类，不能单纯根据 App 名称判断。

---

# 14. JSON Schema 版本

本轮修改会新增结果状态和值，因此建议：

```text
schema_version: 1.1.0
```

要求：

1. 不删除 V1.0 已有主要字段。
2. 原有字段能保留则保留。
3. 新增字段采用向后兼容方式。
4. `false / null / 0 / []` 的原语义不得改变。
5. 认证信息永不进入输出。

---

# 15. 回归样本

至少使用以下真实运行中已经出现的类型做测试。

## 样本 A：正常游戏 + 成就

`Portal 2`

预期：

```text
playtime = success
schema = success
achievements = success
store = success
```

## 样本 B：正常游戏 + stats

`Left 4 Dead`

预期保留：

```text
achievements
game-defined stats
store details
family ownership
```

## 样本 C：家庭拥有、本人不拥有

`Cities: Skylines`

预期继续得到：

```text
owned_by_self = false
owned_by_other_family_members = true
available_via_family = true
```

## 样本 D：非典型 App / 无 schema

例如真实运行中的：

```text
Source SDK Base 2006
Dedicated Server
```

预期：

```text
不是 failed 风暴
```

应根据真实响应进入：

```text
not_applicable
或
data_unavailable
```

并避免继续发出已经能够判断为无意义的下游请求。

## 样本 E：明确无成就

当前真实结果中已有 App 被识别为：

```text
achievements.state = not_applicable
total = 0
```

V1.1 必须保持这一语义，并确保不再把这种 App 计入 failed。

---

# 16. 性能验收

本轮不设脱离实际网络环境的绝对秒数目标。

使用**同一账号、同一配置、尽量接近的网络条件**重新运行 `library`，与基线比较：

```text
baseline HTTP logical_requests = 1668
baseline wall_duration       ≈ 840.6 s
baseline enrichment          ≈ 837.0 s
```

验收要求：

1. 对明确不支持 achievements 的 App，不再调用 `get_player_achievements`。
2. 对明确不支持 stats 的 App，不再调用 `get_user_stats_for_game`。
3. `failed` 只统计真正失败。
4. 同样的 App 集合下，无意义 HTTP 请求数量必须下降。
5. 不能以降低并发到近似串行为代价“优化错误率”。
6. Family collection 结果不得回归。

目标但非硬编码门槛：

```text
logical_requests < 1668
enrichment duration < 837 s
true failed count << 394
```

如果请求数或时间没有下降，Codex 必须在交付说明中给出原因，不允许仅写“优化完成”。

---

# 17. 单元测试要求

至少补以下测试。

## 17.1 状态映射

```text
明确无 schema
    → not_applicable / data_unavailable
    → not failed
```

```text
store 无当前上下文数据
    → data_unavailable
    → not failed
```

```text
timeout 达到最大尝试次数
    → failed
```

```text
5xx 达到最大尝试次数
    → failed
```

```text
用户 cancel
    → cancelled
```

## 17.2 依赖调度

```text
schema says no achievements
    → achievements adapter must not be invoked
```

```text
schema says no stats
    → stats adapter must not be invoked
```

```text
schema supports achievements
    → achievements adapter invoked exactly once
```

```text
same app appears from owned + family + recent
    → schema called once
    → achievements called once
    → stats called once
```

## 17.3 Family 回归

mock/fixture 至少覆盖：

```text
self-owned only
family-owned only
self + family both own
family owned but excluded
```

确保本轮改动不触碰 ownership 语义。

---

# 18. 真实联调要求

离线测试完成后，再使用用户本地凭据运行：

```bash
./start library
```

不得要求用户把：

```text
STEAM_API_KEY
STEAM_FAMILY_ACCESS_TOKEN
Cookie
```

粘贴给 Codex 或写入测试日志。

真实联调报告必须给出：

```text
run_id
schema_version
total apps
logical_requests
http attempts
success
not_applicable
data_unavailable
failed
wall_duration
enrichment_duration
```

并与基线比较。

---

# 19. 不允许做的“优化”

以下做法禁止：

1. 用游戏名称硬编码跳过。
2. 把 HTTP 400 全部改成 `not_applicable`。
3. 为降低 failed 数量吞掉真正异常。
4. 为降低请求数删除既有数据字段。
5. 重写 Family token 获取方式。
6. 引入数据库作为 V1.1 前置条件。

---

# 20. 推荐修改位置

根据当前 V1.0 架构，优先修改：

```text
error_handler.py
Ports/request_executor.py
scripts/library.py
scripts/runtime_debug.py
scripts/persistence.py
```

具体 API adapter 仅在需要暴露更明确 capability/result 语义时小幅修改。

`Ports/registry.py` 除非需要补充已有工具元数据，否则不要重构。

---

# 21. 建议实现顺序

## Phase 1：状态语义

先完成：

```text
success
not_applicable
data_unavailable
failed
```

以及 error → outcome 映射测试。

## Phase 2：dependency planner

实现：

```text
schema
    ↓
achievements?
stats?
```

保证不同 App 间仍然并发。

## Phase 3：in-run dedup

确保相同 query key 只产生一个 future/request。

## Phase 4：runtime debug

补：

```text
planner stats
API stats
outcome stats
```

## Phase 5：回归

验证：

```text
family
playtime
achievements
stats
store
```

均未回归。

## Phase 6：真实 benchmark

重新执行 `library`，输出前后对比。

---

# 22. Codex 最终交付格式

完成后请输出：

## A. 修改文件

逐个列出：

```text
file
修改目的
关键行为变化
```

## B. 状态语义变化

明确说明哪些旧 `failed` 现在会被分类为什么。

## C. 请求规划变化

给出实际依赖图或伪代码。

## D. 测试结果

分别写：

```text
unit tests
mock tests
real Steam integration tests
```

不得混写。

## E. Benchmark

至少输出表格：

| 指标 | V1.0 基线 | V1.1 |
|---|---:|---:|
| App 数 | 419 | |
| Logical requests | 1668 | |
| HTTP attempts | 1668 | |
| Success | 25 | |
| Not applicable | 无独立统计 | |
| Data unavailable | 无独立统计 | |
| Failed | 394 | |
| Wall duration | 840.6 s | |
| Enrichment duration | 837.0 s | |

注意：旧版 `success=25 / failed=394` 的语义存在分类问题，因此只用于展示基线，不能直接把新旧 success/failed 当成完全同口径指标。

## F. 未解决问题

列出仍需要后续处理的：

```text
Steam 接口不稳定行为
无法可靠推断的 capability
真实账号权限边界
性能瓶颈
```

不得为了“任务完成”隐去未验证项。

---

# 23. 本轮完成标准

V1.1 可以宣布完成，当且仅当：

1. Family 链路仍然能够取得实际家庭库。
2. Library 核心结果未回归。
3. `not_applicable / data_unavailable / failed` 已经真正分开。
4. schema 能阻止明确无意义的 achievements / stats 请求。
5. 同一 run 内重复 enrichment 请求被消除。
6. runtime debug 能解释：
   - 为什么没有发某个请求；
   - 为什么发了；
   - 为什么失败；
   - 为什么被标记为 not applicable；
   - 请求量花在哪里。
7. 使用真实数据重新跑一次 benchmark。
8. 新输出升级为 `schema_version = 1.1.0` 或提供等价的兼容版本标识。
9. 不泄漏 API Key、Family token、Cookie 或认证请求头。

---

# 24. 本轮之后暂不实施的事项

以下留到 V1.2 或更后：

```text
跨 run 持久缓存
SQLite
历史快照比较
价格历史
自动 token 获取
GUI / Web UI
更复杂的 App 类型识别
自动性能调参
多账号
家庭成员级游玩数据
```

先把 V1.1 的**数据语义和请求规划**做好，再决定是否值得继续扩展。

---

## 最终原则

本次优化的核心不是：

> “让数字看起来成功率更高”。

而是：

> **系统必须准确知道：哪些请求成功了，哪些能力本来不存在，哪些数据 Steam 没提供，以及哪些才是真正的错误。**

在这个前提下，利用 schema 和已验证 capability 减少无意义请求，同时保持 App 之间的并发执行，才是 V1.1 的正确优化方向。
