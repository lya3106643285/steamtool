# Steam 本地数据工具：Codex 开发任务书

**版本：1.0.0**  
**整理日期：2026-10-02**  
**目标环境：WSL / Python**  
**交付形态：`start`、`stop` 两个运行入口；业务 JSON；结构化 runtime debug 日志**  
**文档状态：用户已确认总体功能与架构；本文补齐可实施的职责、数据契约与验收规则。**

> 给 Codex：请根据本文实现一个可运行的小型 demo，而不是再设计一套平台。优先遵守目录和职责边界；接口可用性必须通过真实响应验证，不能把 mock 测试通过写成 Steam 实测通过。不要要求用户把 API Key、Cookie 或 token 粘贴到聊天、提交记录或测试报告中。

## 0. 执行约定与优先级

### 0.1 本文解决什么

用户已经提出并确认三个业务功能、API 注册层、根目录 `.env`、时间戳输出、受控并发、独立错误处理器，以及由 `scripts` 管理的日志和 runtime debug 监督层。本文将这些内容整理为开发任务书，不表示代码已经实现或本人账号已经联调成功。

本文件可以独立交给 Codex。此前的调研报告和接口清单是补充证据，不是启动开发的必需附件。相关事实来源见第 16 节。

### 0.2 要区分三类约束

| 类别 | 含义 | Codex 应如何处理 |
|---|---|---|
| **已确认要求** | 业务范围、目录、职责、输出形式、日志与错误处理架构 | 不得擅自删减或改成另一套架构 |
| **实现补充** | 函数契约、错误码、默认参数、测试组织、退出码等 | 可在不改变职责的前提下细化；有实质改动必须记录 |
| **待实测假设** | 登录态接口、家庭库完整性、新参数、隐私及响应差异 | 以官方资料和授权实测为准；不伪造成功或静默补零 |

**优先顺序：用户后续明确指令 > 本文已确认架构 > 本文实现补充 > 旧调研建议。**接口事实则以适用的当前官方资料和授权实测为准；发现冲突，应记录差异并调整适配器，而不是为了符合文档而歪曲数据。

旧报告中的 `src/providers/workflows` 目录、仓库外凭据文件、按运行建多层输出目录，以及此前的自定义 `client.py` 方案，均不再作为本期架构基线。当前基线是 `Ports/`、`scripts/`、`Outputs/`、根目录 `.env`、`error_handler.py` 和 `Ports/request_executor.py`。

### 0.3 开发时的基本要求

- 先检查当前仓库、已有文件和适用的仓库说明；不要覆盖用户已有代码、凭据、输出或未提交改动。
- 在目标项目内工作，不擅自新建远端仓库、推送、发布或修改其它项目。
- 采用小步实现与测试。无 Key 或家庭 token 时继续完成公开接口、mock、错误处理和日志测试，不将缺少凭据当成全部开发的阻塞。
- 所有生产功能保持只读。不得自动申请 Key、重复触发手机确认、绕过风控、修改隐私或调用购买、交易、家庭成员管理等写入接口。
- 交付时逐项说明：已实现、已离线测试、已真实联调、未验证、偏离本文的调整。

## 1. 项目目标与范围

### 1.1 三个业务功能

| 功能 | 输入 | 必须输出的内容 |
|---|---|---|
| 愿望单导出 | 本人 SteamID 与配置 | 当前可取得的愿望单条目、游戏情况、商店 URL、相关 AppID—名称映射 |
| 游戏库导出 | 本人 SteamID；可选本人家庭会话 token | 自有库、家庭候选及共享资格；本人累计时长、近两周时长、个人成就和可取得的游戏统计 |
| 单游戏查询 | 游戏名称；同时支持精确 AppID 和商店 app URL | 名称解析结果、商店详情、本人是否持有、其他家庭成员是否持有、本人是否可共享 |

三个业务功能都输出结构化 JSON。导出“商店页面”指页面 URL 和接口提供的结构化字段，不是下载整张网页或图片。

**“本人时长与成就”始终属于配置中的目标 SteamID。家人提供许可证，不代表使用家人的时长和成就。**

### 1.2 首版必须提供的支撑能力

Python、WSL、`start` / `stop`、显式工具注册表、独立 API 文件、根目录 `.env`、统一持久化、运行日志、错误码、有限重试、限速与并发控制、优雅停止、运行内去重，以及不依赖真实凭据的自动化测试。

### 1.3 明确不做

不做 Web UI、HTTP 服务、数据库服务、Docker 编排、MCP、LLM/Agent、自动浏览器登录、凭据抓取器、Steam 客户端逆向登录、账号写操作、销量推算、历史价格库、推荐系统、图表，以及全 Steam 游戏详情抓取。

不为了小型 demo 引入事件总线、动态插件发现、复杂依赖注入框架或独立监督守护进程。不把第三方网站当作默认数据来源；第三方开源项目只用于接口行为参考。

`all`、全应用名称目录更新和跨运行缓存属于可选增强，不得阻塞三个业务功能。每份业务 JSON 自带本次相关的 ID 映射，不要求先下载整个 Steam 目录。

## 2. 目录与模块职责

### 2.1 基线目录

目录大小写固定为下列形式；不要同时创建 `Script`、`Scripts`、`scripts` 等不同副本。

```text
steam-tool/
├── start                              # Bash 薄入口
├── stop                               # 仅停止本工具的薄入口
├── main.py                            # CLI、装配、运行生命周期
├── config.py                          # .env 与环境变量读取、格式校验
├── error_handler.py                   # 统一错误码、分类、恢复决策
├── .env                               # 用户本地文件，不提交、不覆盖
├── .env.example                       # 无真实凭据的配置模板
├── .gitignore
├── requirements.txt
├── requirements-dev.txt              # 测试依赖，可按实际简化
├── README.md                          # 安装、配置、运行、限制
│
├── Ports/
│   ├── __init__.py
│   ├── registry.py                    # 显式登记、查找与调用
│   ├── request_executor.py            # HTTP 执行及恢复决定的落实
│   ├── get_player_summaries.py
│   ├── resolve_vanity_url.py
│   ├── get_wishlist.py
│   ├── get_wishlist_item_count.py
│   ├── get_owned_games.py
│   ├── get_recently_played_games.py
│   ├── get_family_group_for_user.py
│   ├── get_shared_library_apps.py
│   ├── get_schema_for_game.py
│   ├── get_player_achievements.py
│   ├── get_user_stats_for_game.py
│   ├── get_app_details.py
│   ├── search_games.py
│   └── get_app_list.py                # 可选：完整名称目录
│
├── scripts/
│   ├── __init__.py
│   ├── wishlist.py                    # 愿望单业务
│   ├── library.py                     # 游戏库与本人游玩数据业务
│   ├── game.py                        # 名称解析及单游戏业务
│   ├── persistence.py                 # 业务结果落盘
│   └── runtime_debug.py               # 日志配置、事件记录、进度监督
│
├── Outputs/                           # 运行产物，不提交
├── .runtime/                          # 锁和实例信息，不提交
└── tests/                             # 测试与脱敏/合成 fixtures
```

`__init__.py` 不计入职责文件数量。`scripts` 保持三个业务文件、一个持久化文件、一个 runtime debug 文件，共五个职责文件。辅助函数可放在相应业务文件中；不为每个函数继续拆层。

`.runtime/`、`tests/` 和依赖文件属于实现补充，不是新增业务层。可选接口文件没有实现时，不要放入伪成功占位工具。

### 2.2 职责矩阵

| 模块 | 负责 | 不负责 |
|---|---|---|
| `main.py` | 配置装配、实例锁、CLI、初始化日志、业务调度、停止与收尾 | 拼接具体 Steam API 参数、解释家庭拥有关系 |
| `config.py` | 统一读取配置、默认值、格式校验 | 发 HTTP 请求、输出完整凭据 |
| `Ports/registry.py` | 工具登记、凭据前置检查、调用定位、运行内请求复用 | 业务字段合并、自动申请 API Key |
| 各 API 文件 | 接口参数转换、请求定义、响应解析、已知业务错误识别 | 自行创建 HTTP 客户端、睡眠重试、保存业务文件 |
| `request_executor.py` | 复用 HTTP 连接、发送请求、执行超时/限速/并发限制，落实错误处理器决定 | 决定拥有关系、独立维护第二套恢复策略 |
| `error_handler.py` | 统一错误语言、分类、恢复决定和预算判断 | 发请求、sleep、写业务 JSON、操纵事件循环 |
| 三个业务脚本 | 编排多个工具、合并与规范化、生成业务结果 | 绕过 registry 直接请求网络、重复实现限流重试 |
| `persistence.py` | 命名、JSON 序列化、原子写入、输出路径 | 再查接口、决定错误恢复、记录每次 HTTP 响应 |
| `runtime_debug.py` | 日志配置、脱敏、关联 ID、进度与耗时、运行摘要 | 自动修复业务、重试请求、代替外部进程监控 |

### 2.3 调用关系

```text
start → main.py
          ├─ config.py
          ├─ scripts/runtime_debug.py：配置全局日志与本轮监督
          ├─ 创建 request_executor 与 registry，登记工具一次
          └─ scripts/{wishlist,library,game}.py
                    └─ registry.call(tool_name, ...)
                              └─ 对应 API 工具
                                    └─ request_executor.execute(...)
                                              ├─ 执行 HTTP
                                              └─ error_handler：分类并返回恢复决定
                    └─ 生成业务结果
          └─ scripts/persistence.py：保存业务 JSON
          └─ 关闭连接、刷新日志、释放实例锁
```

日志由 `scripts/runtime_debug.py` 配置，各模块通过标准 logger 或注入的轻量事件接口产生日志。`Ports` 不得反向导入 `scripts` 中的业务实现；错误处理器也不得导入执行器。共享的小型数据结构可就近放在已有模块，避免循环导入，不额外建一套基础设施包。

### 2.4 技术栈起点（实现补充）

以 Python 3.11 及以上作为首版支持范围，在项目 `.venv` 中安装依赖；不得修改系统 Python 或其他项目环境。运行依赖以 `httpx`、`python-dotenv` 为主，其余优先使用标准库；测试可使用 `pytest` 和所需的异步测试支持。Codex 应记录自己实际验证的 Python 与依赖版本，不将“最新版本”写成未经核对的保证。

`.env` 由 Python 配置逻辑解析，不作为可执行 shell 脚本 `source`。HTTPX 只是执行器内部使用的网络库；允许使用它的 `AsyncClient`，但不能因此重新引入一个承担全部策略的项目级 `client.py`。

## 3. 工具注册与 API 适配契约

### 3.1 “注册”的含义

这里是**程序内工具注册**，不是向 Steam 申请 Key。启动时显式登记一次，运行时查找并调用多次；不得每查一款游戏重新注册。

注册器采用显式映射表，不扫描目录自动导入，不执行用户传入的任意函数名或 URL。

每个工具至少声明：

| 元信息 | 用途 |
|---|---|
| `name` | 稳定唯一的工具名，如 `get_schema_for_game` |
| `callable` | 对应异步实现 |
| `auth_kind` | `none`、`user_key` 或 `session_token` |
| `rate_scope` | 请求执行器使用的限速/冷却范围 |
| `read_only` | 本项目只允许已审核的只读工具 |
| `capability_status` | 区分已实现、实验性、禁用；不能与已实测混为一项 |

未知工具名、重复注册、无效参数都要产生明确错误。注册器不得把“已登记”当成“账号有权调用”。

### 3.2 业务调用的概念契约

以下为接口约定，不是要求照抄的完整实现：

```python
result = await registry.call(
    "get_schema_for_game",
    params={"appid": appid, "language": language},
    context=task_context,
)
```

注册器统一使用项目内部参数名，如 `language`。具体适配器负责将它转换成该接口实际要求的 `l`、`language` 或 `input_json` 字段；这些细节不泄漏给业务脚本。

每个工具返回规范化结果，至少包含：`state`、`data`、`error`、`source`、`fetched_at`、`attempts`、`from_run_cache`。可以使用类型明确的 dataclass 或等价结构；不允许有的工具返回字典、有的返回 JSON 字符串、有的直接返回裸 HTTP 响应。

`data`、`error` 的字段必须一致可预测。正常的“不适用”与失败分开表达。未知程序异常不能一律变成成功的空结果。

工具返回的 `state` 采用 `ok`、`unavailable`、`not_applicable`；成功的空清单仍是 `ok`，不能只凭数组长度判失败。业务数据块和 coverage 可进一步使用 `partial`、`not_requested`。未知的布尔事实用 `null` 表达，不另外发明字符串 `"unknown"` 代替布尔字段。外层运行 `status` 使用第 10.2 节的独立状态集合。

### 3.3 执行器与响应解码的衔接

执行器应能在唯一的重试循环里覆盖两种错误：网络/HTTP 错误，以及 HTTP 200 内的已知上游失败。

可采用 `execute(request_spec, decode, context)`：适配器提供纯解码函数；执行器请求成功后调用它；解码函数发现已知接口错误时给出规范化失败，由同一错误处理器决策。解码函数本身不得重试或联网。

这避免“HTTP 重试在执行器里、业务错误重试又在适配器里”的重复机制。任意 `KeyError`、`TypeError` 不得直接假定为服务端临时故障；应识别为契约错误或内部错误，并留下脱敏诊断。

### 3.4 新接口的接入方式

新增一个 API 文件，声明请求和解码逻辑，显式登记工具，并补适配器测试。只有新接口改变某个业务能力时，才修改对应业务脚本。

新增接口不应要求改写日志、限流、重试、JSON 持久化或其他已有 API 工具。不得为可扩展性而预先封装全部 Steam 接口。

## 4. 接口基线与实测边界

### 4.1 权限边界

本期仅采用匿名入口、普通个人 Web API Key，以及用户明确提供的本人会话 token。不同凭据不得混用。Valve 文档区分普通用户 Key 与发行商权限，并支持通过 `x-webapi-key` 请求头传入 Key。[R01]

普通 Web API 请求使用 `api.steampowered.com`，不要直接复制发行商域名示例。`store.steampowered.com` 的商店 JSON 入口按单独适配器处理。[D01]

API 表是开发候选，不是“本人的账号已经调用成功”的清单。家庭及愿望单协议参考沿用此前调研；必须在实现时复核。本任务书没有执行账号登录、Key 注册或真实库导出。

### 4.2 三个功能需要的主要端点

除标记商店域名者，路径均位于公共 Web API 域名。

| 工具名 | 端点 | 凭据与用途 | 证据/注意 |
|---|---|---|---|
| `get_player_summaries` | `/ISteamUser/GetPlayerSummaries/v2/` | 个人 Key；目标用户基础资料 | 按需身份诊断；资料可读不等于库可读 [D01] |
| `resolve_vanity_url` | `/ISteamUser/ResolveVanityURL/v1/` | 个人 Key；自定义主页转 SteamID | 已有数字 ID 时不调用 [D01] |
| `get_owned_games` | `/IPlayerService/GetOwnedGames/v1/` | 个人 Key；本人库与时长 | 可见性约束；家庭扩展参数另行验证 [R02][T01] |
| `get_recently_played_games` | `/IPlayerService/GetRecentlyPlayedGames/v1/` | 个人 Key；近期游玩 | `count=0` 或未设置表示接口全部返回项 [R02] |
| `get_schema_for_game` | `/ISteamUserStats/GetSchemaForGame/v2/` | 个人 Key；游戏成就和统计定义 | 每次指定一个 AppID [R03] |
| `get_player_achievements` | `/ISteamUserStats/GetPlayerAchievements/v1/` | 个人 Key；目标玩家成就 | 必须使用本人 SteamID [R03] |
| `get_user_stats_for_game` | `/ISteamUserStats/GetUserStatsForGame/v2/` | 个人 Key；游戏自定义玩家统计 | 不假定各游戏字段相同 [R03] |
| `get_wishlist` | `/IWishlistService/GetWishlist/v1/` | 可见时的公开读取 | `appid`、`priority`、`date_added`；公开读取及失败结构需测 [T02][D01] |
| `get_wishlist_item_count` | `/IWishlistService/GetWishlistItemCount/v1/` | 可见时的公开读取 | 数量补检，不单独证明内容完整 [T02][D01] |
| `get_family_group_for_user` | `/IFamilyGroupsService/GetFamilyGroupForUser/v1/` | 本人会话 token | 家庭身份和权限需验证 [T03][T04] |
| `get_shared_library_apps` | `/IFamilyGroupsService/GetSharedLibraryApps/v1/` | 本人会话 token | 拥有者、共享排除原因与截断需验证 [T03][T04] |
| `get_app_details` | 商店 `/api/appdetails/` | 匿名；游戏详情、地区价格 | 内部 JSON 接口，单 AppID 为保守起点 [T05][D01] |
| `search_games` | 商店 `/api/storesearch/` | 匿名；名称候选 | 不能直接把第一项当正确答案 [T05] |
| `get_app_list` | `/IStoreService/GetAppList/v1/` | 个人 Key；可选完整名称目录 | 必须分页，不在每次 start 时全量取 [R04] |

`IPlayerService`、`IStoreService` 的官方说明要求按 Service 接口使用 `input_json`。统一序列化业务字段，认证材料单独处理；适配器测试需要核对最终编码，不能只检查函数参数。[R02][R04]

其他接口按照它们各自的当前契约编码，不假定“所有 Steam 端点的参数形式完全一致”。如实际验证需要替代编码，应写适配器测试和说明，而不是在业务脚本里临时拼 URL。

### 4.3 家庭接口必须保留的未知项

`include_family_licenses=true` 的跟踪描述是补充“本人通过家庭共享玩过、但未自有持有”的游戏，并带 `family_shared` 标记。它不等于完整的当前家庭共享库。[T01]

家庭列表请求可从 `include_own=true`、`include_excluded=true` 开始验证；先读取真实家庭组信息，不把参考代码中 `family_groupid=0` 的经验行为作为长期保证。返回项中的 `owner_steamids`、`exclude_reason`、`max_apps` 限制及相关字段语义需要核对。[T03][T04]

第一版只要求接收用户本地提供的有效会话 token 并实现读取适配器，不要求自动获取 token。登录辅助和 Cookie 补检不属于默认实现范围。身份不匹配或无法确认 token 对应本人时，不把家庭结果绑定到另一个 SteamID；保留未验证状态。

`rt_playtime` 等家庭字段的统计主体和单位没有确认前，仅可作为有来源说明的受控原始字段保留，不填入“本人累计分钟”。未知排除枚举保留原始值，不能默认解释为允许共享。[T03][D01]

## 5. 三个业务工作流

### 5.1 `scripts/wishlist.py`

```text
解析目标 SteamID
  → 查询愿望单列表与可用的数量信息
  → 保留所有可识别 AppID，去重但不丢来源
  → 按需并发补齐商店详情
  → 关联本轮可取得的个人/家庭拥有信息
  → 生成 wishlist 业务结果与本次 ID 映射
```

保留添加时间、优先级及返回的原始语义。列表和数量不一致时，记录可能的不完整；可做一次有记录的业务一致性复核，但不得形成无上限补查循环，也不得另套网络重试器。

详情失败、下架或地区不可读，不得删除愿望单条目。Key/token 缺失时，愿望单公开查询仍可执行；拥有关系设为未知。只有明确成功取得空清单且不存在权限/协议歧义时，才把愿望单认定为空。

### 5.2 `scripts/library.py`

```text
本人库：GetOwnedGames（不含家庭借用）
本人借玩补充：GetOwnedGames（含已玩家庭借用，能力需验证）
近期记录：GetRecentlyPlayedGames
家庭资格：GetFamilyGroupForUser → GetSharedLibraryApps
  → 合并、去重，保留各集合的语义
  → 按 AppID 补齐商店详情、schema、本人玩家成就、可用统计
  → 生成 library 业务结果与本次 ID 映射
```

前面相互独立的清单可以并发请求；家庭组与家庭列表仍按依赖执行。逐游戏查询不应在 AppID 尚未确定前启动。

本人库基础请求显式设置 `include_appinfo=true`、`include_played_free_games=true`。家庭借用参数用两种模式对照；`skip_unvetted_apps` 等补全参数属于待验证适配细节，不因未知参数被忽略就宣称已完整。保留实际发送参数的安全摘要和观察到的返回范围。[R02][T01]

本人库内明确零时长游戏要保留。曾经借玩但目前已不可共享的游戏，仍可保留其本人游玩记录，不能因此标成当前有共享资格。

家庭无 token 时返回已取得的自有库与本人数据，并标记家庭覆盖不足；有 token 但清单未知时不能输出“完整家庭库”。家庭候选清单已取得但某个游戏指标缺失时，保留候选及缺失原因。

### 5.3 `scripts/game.py`

```text
游戏名 / 精确 AppID / 官方商店 app URL
  → 校验输入与实体类型
  → 直接解析 ID，或本轮名称/别名索引 + 商店搜索
  → 确定唯一目标；否则返回候选
  → 查询商店详情
  → 关联本轮个人库、家庭库与愿望单信息
  → 生成 game 业务结果与本次 ID 映射
```

不使用大模型猜 AppID。名称规范化只服务于查找，不覆盖原始名称；可用 Unicode 规范化、大小写归一和空白整理。模糊匹配只产生候选，不自动裁定。

交互模式可让用户选择候选；非交互命令遇到歧义时，输出 `needs_selection` 的 JSON 和候选 AppID，不挂起等待 stdin。商店 `sub`/`bundle` URL 不得当成 app URL；首版清晰拒绝不支持的实体即可。

单游戏查询只为确定拥有情况取得清单，不应为了一个 AppID 顺便给整个库逐项抓详情和成就。

### 5.4 共同的数据语义

**拥有关系使用独立字段，不用单个 `owned`：**

- `owned_by_self`：当前已知的本人持有情况；不承诺是全部历史许可证账本。
- `owned_by_other_family_members`：当前家庭中其他成员是否持有。
- `available_via_family`：本人当前是否具备家庭共享资格；不等于实时空闲副本。
- `owner_steamids`：来源实际提供的拥有者；未知时为 `null`。
- `shared_exclusion_reason`：已知排除原因或原始枚举；未知时为 `null`。

`true` 需要肯定证据；`false` 需要足以支持否定的、范围明确的完整数据；`null` 表示没有足够证据。HTTP 200 或字段缺失不能单独证明否定结论。

个人成就按 `(subject_steamid, appid, apiname)` 关联，展示名不作主键。只有游戏成就定义和玩家状态都足够完整时，才计算完整完成率。未知解锁状态为 `null`；无成就与成就读取失败分开。统计缺失不自动推断为未玩过。[R03]

个人时长字段统一记录单位；已确认是分钟的字段可进入 `total_minutes`、`last_2weeks_minutes`。平台细分不盲目相加替代总时长；缺失两周字段不默认补零，除非已验证该响应契约的默认语义。[D01]

SteamID64 使用十进制字符串；AppID 使用整数，作为 JSON 对象键时使用其字符串形式。商店币种、原始金额、格式化价格分别保留，缺价不等于免费。地区参数是本次查询上下文，不证明账户可在该地区购买。[D01]

## 6. 错误处理器与请求执行器

### 6.1 三种责任必须分开

**请求执行器负责做；错误处理器决定错误发生后怎么做；runtime debug 记录发生了什么。**

超时设置由执行器配置并交给 HTTP 库生效；超时后的处理由错误处理器决定。主动限速是请求前的调度机制，不是异常；收到 429 后的冷却策略才进入错误决策。HTTPX 区分连接、读取、写入和连接池超时，日志应保留对应类型。[R06]

错误处理器以函数或轻量对象实现，尽可能保持决策可测试。不访问网络、不直接写文件、不执行 sleep。网络故障、响应错误、配置错误、输出错误都使用同一套错误对象，但不是所有错误都进入重试。

### 6.2 错误对象与处理决定分开

错误对象最低字段：

```json
{
  "error_id": "err_demo_01",
  "code": "NETWORK_TIMEOUT",
  "source": "transport",
  "scope": "request",
  "api": "get_schema_for_game",
  "appid": 1000000001,
  "subject_steamid": null,
  "exception_type": "ReadTimeout",
  "http_status": null,
  "upstream_code": null,
  "message": "等待上游响应数据超时"
}
```

上例为合成结构示例，不是真实请求记录。错误对象不得携带原始 Request/Response、凭据对象或未经脱敏的 URL。

恢复决定最低字段：`action`、`wait_seconds`、`cooldown_scope`、`reason`。动作可为 `retry`、`cooldown_then_retry`、`skip`、`abort_feature`、`abort_run`。是否允许重试要结合只读属性、当前 attempt、剩余预算及错误证据，而不是错误码上永远固定一个布尔值。

用户取消单独走停止流程，不伪装成网络故障，不自动重试。

### 6.3 首版错误码

以下是本项目自定义代码，不是 Steam 官方错误码；实现时保持稳定的字符串枚举。

| 错误码 | 典型含义 | 默认策略 |
|---|---|---|
| `CONFIG_INVALID` | SteamID、地区、数值配置等格式无效 | 终止相关命令，给出配置项名，不输出秘密值 |
| `TOOL_NOT_FOUND` | 工具未登记 | 视为调用/配置问题，不重试 |
| `AUTH_REQUIRED` | 当前工具缺少必要凭据 | 不发请求；相关来源降级 |
| `ACCESS_DENIED` | 明确拒绝访问，但具体原因未必可判定 | 不循环重试，不从 403 猜测具体隐私设置 |
| `AUTH_EXPIRED` | 有明确证据表明会话已失效 | 暂停相关认证来源，提示本地更新凭据 |
| `NETWORK_TIMEOUT` | 连接、读取、写入、连接池等超时 | 按类型与预算有限重试 |
| `NETWORK_ERROR` | 连接中断等传输失败 | 只对适合重试的情况重试；证书验证失败不关闭 TLS |
| `RATE_LIMITED` | 429 或已确认的上游限流信号 | 相关 scope 共享冷却后再判断是否重试 |
| `UPSTREAM_UNAVAILABLE` | 可识别的临时服务失败，如部分 5xx | 有限重试；不笼统重试所有非 200 状态 |
| `RESPONSE_INVALID` | 无法解析、协议形状不符合预期 | 保存安全诊断，默认不盲重试 |
| `DATA_UNAVAILABLE` | 上游明确不提供目标数据 | 项目结果保留缺失，不补零 |
| `REQUEST_DEADLINE_EXCEEDED` | 本次逻辑请求用尽重试总预算 | 停止该请求，保留最后原因 |
| `OUTPUT_WRITE_FAILED` | 业务 JSON 无法落盘 | stderr 与日志尽力报告，不能声称导出成功 |
| `LOG_WRITE_FAILED` | runtime 日志写入失败 | 停止新请求，尽力保存已完成业务结果，stderr 报告 |
| `INTERNAL_ERROR` | 未预期的程序错误 | 脱敏堆栈，终止受影响功能或运行，不伪装正常空数据 |

名称歧义、明确不在家庭、明确没有成就等优先作为业务状态，不都定义成程序错误。未知上游枚举和状态保留原值及来源，不随意归因为账号问题。

### 6.4 唯一重试入口

```text
参数与认证检查
  → 等待调度允许发送
  → 发起一次 HTTP 请求
  → 检查 HTTP + 解码已知业务结果
  → 成功则返回
  → 失败交 error_handler 分类与决策
       ├─ skip/abort：返回规范化失败或终止信号
       └─ retry/cooldown：执行器落实等待，再进入下一次 attempt
```

重试循环只存在于执行器。不得同时启用 HTTP 库底层自动重试、适配器重试和业务脚本重试。`max_attempts=3` 的含义固定为首次请求加最多两次重试。

429 的 `Retry-After` 不保证存在；存在时可能是秒数或 HTTP 日期，必须按语义解析。[R07][R08]

没有有效服务端等待提示时，使用有上限的指数退避与抖动。服务端要求的有效等待不能被本地 backoff 上限缩短；等待超过本次剩余预算时，应放弃本请求并保留相应 scope 的冷却，不提前再打服务器。

收到限流后保守地暂停对应域名的新请求，而不仅暂停出错的那个协程。这是本项目的起始策略，不代表已确定 Valve 的真实限流范围。必要时可基于证据细化 scope，但不通过换 IP、换 Key 或加并发绕过限制。

## 7. 并发、限速与运行内去重

### 7.1 Schema 查询的处理方式

`GetSchemaForGame` 按单个 AppID 查询游戏定义。不同 AppID 之间没有本项目的业务依赖，因此客户端可对它们并发发起独立请求；这不等于服务端提供多 AppID 批量接口，也不等于承诺任何固定并发额度。[R03]

采用 `asyncio` 与复用的 `httpx.AsyncClient`。不要在循环中为每款游戏新建客户端；HTTPX 的异步接口和连接复用用于承担这个传输工作。[R05]

### 7.2 控制必须发生在真实请求层

同时处理四款游戏不等于只有四个网络请求。每款游戏可能同时请求 schema、玩家成就和详情，所以全局 semaphore 必须约束实际 HTTP 发送及响应读取阶段。

并发上限与请求速率分别实现。等待限速、重试退避和共享冷却时不长期占住 HTTP 在途名额；真正发送前重新核对 scope 冷却，避免其他任务在 429 后继续放行。获取多个限制时使用一致顺序，避免死锁。

可以使用有界任务队列或受限异步任务组。几十到几百个目标不要求引入分布式任务系统。必须能够在停止时取消排队和等待中的工作。

### 7.3 建议起始参数

以下数字是可调整的工程起点，不是 Steam 官方阈值，也不是已测试的最高吞吐。

| 参数 | 起始值 | 定义 |
|---|---:|---|
| 全局最大 HTTP 并发 | 4 | 所有业务、所有来源共享 |
| 公共 Web API 域名发送速率 | 2 请求/秒 | 本人 Key 与家庭 API 共用域名基础限制 |
| 商店域名发送速率 | 0.5 请求/秒 | 即起始间隔约 2 秒 |
| 家庭接口附加发送速率 | 0.5 请求/秒 | 同时服从公共 Web API 域名限制 |
| 连接超时 | 10 秒 | 每次尝试 |
| 读取超时 | 20 秒 | 每次尝试；不等于整个工作流耗时 |
| 写入/连接池超时 | 各 10 秒 | 每次尝试 |
| 最大尝试次数 | 3 | 包含首次请求 |
| 逻辑请求总预算 | 60 秒 | 从首次真正发送开始，包含后续尝试、重试排队和退避 |
| 本地退避基数/上限 | 1 秒 / 30 秒 | 不能截短有效 Retry-After |
| 停止收尾宽限 | 5 秒 | 可配置；超过后取消在途任务并收尾 |
| 控制台进度间隔 | 5 秒 | 只反映当前进度，不保证完成时间 |

大量业务任务在首次发送前排队的时间，不应全部被算入 60 秒逻辑请求预算，导致队尾任务在从未发出请求前就批量失败；该排队时间单独记录。时间间隔和预算使用单调时钟，墙上时间只用于可读时间戳。

### 7.4 运行内去重必须处理“同时请求”

成功结果按语义键复用：

| 数据 | 缓存/请求合并键至少包含 |
|---|---|
| 成就定义 | 工具名、AppID、语言 |
| 商店详情 | 工具名、AppID、语言、商店地区 |
| 玩家成就/统计 | 工具名、目标 SteamID、AppID、语言（适用时） |
| 本人库/近期记录 | 工具名、SteamID、影响范围的请求参数 |
| 家庭清单 | 工具名、已核对的本人/家庭身份、范围参数、语言 |

两个协程同时请求相同键时，应共享一个在途任务，而不只是请求结束后才缓存。缓存键不能包含原始 Key 或 token，也不能跨不同账号或不同参数错误复用。

结果保留真实 `fetched_at`，缓存命中不会改成新的联网采集时间。临时失败不缓存成永远成功的空结果；缺凭据、失效认证等来源级问题可以在本轮记忆，防止给每个 AppID 重复发无意义请求。

首版仅做运行内复用，不做跨运行持久缓存和自动恢复。可选全目录读取也不得导致对全 Steam 游戏抓取详情。

## 8. 日志与 runtime debug 监督

### 8.1 日志归 scripts 管理，事件由所有层产生

`runtime_debug.py` 负责初始化 logger、输出格式、脱敏和运行统计；其余模块只产生事件，不各自添加文件 handler，也不各自选择日志路径。重复调用初始化不得造成一条事件输出多次。

首版使用 Python 标准 logging 即可。可用标准日志的 `extra` 字段承载结构化上下文，不引入监控平台或外部日志服务。监督层是进程内的，不承诺在进程崩溃、断电或事件循环完全失去响应后自救。

### 8.2 两种日志出口

**控制台：** 默认 INFO，显示功能、进度、失败数量、等待原因和最终文件路径；不要刷整份 HTTP 响应。  
**JSONL：** 逐行追加结构化事件，包含请求尝试、重试、冷却及阶段变化。正常停止后每一行都应能独立解析。

业务结果是 `.json`，日志是 `.runtime.jsonl`。后者不是一个 JSON 数组；读取器必须按行读取。两者用相同 `run_id` 关联。

### 8.3 关联标识与字段

| 字段 | 定义 |
|---|---|
| `timestamp` | 带时区的 UTC 事件时间 |
| `level`、`event`、`module` | 严重度、稳定事件名、来源模块 |
| `run_id`、`feature` | 本轮业务运行及功能 |
| `task_id` | 逻辑子任务，如某款游戏的成就补齐 |
| `request_id` | 一次逻辑 API 请求；重试沿用同一 ID |
| `attempt` | 当前请求尝试号，从 1 开始 |
| `api`、`appid` | 工具与目标，适用时提供 |
| `duration_ms` | 本事件对应阶段耗时，说明测量范围 |
| `queue_wait_ms`、`throttle_wait_ms`、`retry_wait_ms` | 区分排队、主动限速、恢复等待 |
| `http_status`、`error_code`、`error_id` | 适用时关联 HTTP 和错误对象 |
| `message` | 简短、可读、已脱敏的说明 |

不要用全局可变“当前 AppID”给并发日志加标签；使用显式上下文或正确隔离的上下文变量。

### 8.4 首版必须记录的事件

```text
run_started / phase_started / phase_finished
collection_loaded / task_started / task_finished
request_queued / request_started / request_succeeded / request_failed
retry_scheduled / cooldown_started / run_cache_hit
progress_snapshot
stop_requested / run_cancelled
export_started / export_saved / export_failed
run_finished
```

每个任务有且只有一个终态，避免重试次数被误算为已完成游戏数。任务计数至少区分：待执行、运行中、成功、失败、跳过、取消。`total` 尚未知时使用 `null`，清单取得后再确定，不编造百分比。

运行摘要至少统计：各阶段耗时、真实 HTTP 尝试数、逻辑请求数、重试数、限流数、运行内缓存命中数、已完成/失败项目数。异步请求耗时相加可能大于墙上运行时间，展示时不得混为一项。

### 8.5 示例事件

```json
{
  "timestamp": "2026-10-02T00:00:10.000Z",
  "level": "WARNING",
  "event": "retry_scheduled",
  "module": "Ports.request_executor",
  "run_id": "demo01",
  "feature": "library",
  "task_id": "app-1000000001-schema",
  "request_id": "req-demo-01",
  "attempt": 1,
  "api": "get_schema_for_game",
  "appid": 1000000001,
  "http_status": 429,
  "error_code": "RATE_LIMITED",
  "error_id": "err-demo-rate",
  "retry_wait_ms": 10000,
  "cooldown_scope": "api.steampowered.com",
  "message": "相关域名进入冷却；本请求仍有剩余尝试预算"
}
```

示例全部为合成记录。后续请求只有在全部限制和预算都允许时才重试，不因为日志写了计划就保证一定再次发送。

### 8.6 安全与监督失败

采用安全字段白名单，默认不记录完整 URL 查询串、请求/响应头、完整响应正文或完整环境变量。递归过滤 `key`、`api_key`、`access_token`、`refresh_token`、`cookie`、`authorization` 等秘密字段，并对已知秘密值做兜底替换。

只做字段名过滤还不够：异常字符串和第三方 HTTP 日志可能包含 URL。需要控制第三方日志级别，并在最终输出 formatter 或等价出口统一脱敏；不得直接输出未处理的 `str(exception)`。

不得在 DEBUG 模式关闭脱敏。关闭会捕获局部变量或完整请求对象的调试输出。账号数据留在本地，示例与测试报告使用合成或已脱敏数据。

日志初始化失败时不启动新网络任务；运行中写日志失败时发出一次安全 stderr 提示，停止新请求，尽力保存已完成业务结果，并返回失败状态。不要通过已坏的日志 handler 递归报告自己的写入失败。

## 9. 配置与凭据

### 9.1 读取规则

`.env` 放项目根目录，由 `config.py` 显式读取一次。路径相对项目根解析，不依赖用户当前 shell 的工作目录。建议优先级为：显式非敏感 CLI 参数 > 已存在的进程环境变量 > 根目录 `.env` > 默认值。

Key/token 不接受明文 CLI 参数，避免进入 shell 历史和进程参数。可以放 `.env` 或进程环境变量；需要交互输入时只能使用本地隐藏输入且不回显。

配置载入阶段检查类型与范围；具体功能是否必须具备 Key/token 在工具调用前检查。没有 Key 的用户仍能执行适用的公开搜索/详情；没有家庭 token 不能导致自有库整个不可运行。

### 9.2 `.env.example` 建议内容

```dotenv
# 真实 .env 只在本机填写；这些字段在模板中保持为空。
STEAM_API_KEY=
STEAM_ID=
STEAM_FAMILY_ACCESS_TOKEN=

# 下列是示例查询上下文，不代表已识别用户的账户商店国家。
STEAM_LANGUAGE=schinese
STEAM_STORE_COUNTRY=CN
OUTPUT_DIR=Outputs

STEAM_MAX_CONCURRENCY=4
STEAM_WEBAPI_RPS=2
STEAM_STORE_RPS=0.5
STEAM_FAMILY_RPS=0.5

STEAM_CONNECT_TIMEOUT_SECONDS=10
STEAM_READ_TIMEOUT_SECONDS=20
STEAM_WRITE_TIMEOUT_SECONDS=10
STEAM_POOL_TIMEOUT_SECONDS=10
STEAM_REQUEST_DEADLINE_SECONDS=60
STEAM_MAX_ATTEMPTS=3
STEAM_BACKOFF_BASE_SECONDS=1
STEAM_BACKOFF_CAP_SECONDS=30

STEAM_STOP_GRACE_SECONDS=5
STEAM_PROGRESS_INTERVAL_SECONDS=5
LOG_LEVEL=INFO
```

至少校验并发为正整数、RPS 和各超时为正数、attempt 数不小于 1、SteamID 是适用范围内的十进制字符串、AppID 是有效正整数。验证失败只指出变量名和要求，不显示原始秘密内容。

`.env.example` 中的国家、语言和参数是实现默认值，不是从用户账号读取的事实。不要根据 IP 位置或界面语言擅自修改商店地区。

### 9.3 凭据使用限制

Key 仅附加到要求个人 Key 的已允许端点；会话 token 仅附加到明确需要它的端点。不能给整个 HTTP 客户端设置一个会被带到所有主机的全局认证头。[R01]

默认不自动跟随携带凭据的重定向；需要重定向时必须先验证目的主机与认证转发策略。保持 TLS 校验，不自动切换代理或绕过证书错误。记录网络配置问题时不得暴露代理认证信息。

`.env`、`Outputs/`、`.runtime/`、`.venv/`、缓存和真实 fixtures 加入 `.gitignore`。真实 `.env` 不得被 start 覆盖；推荐在 WSL 本地文件系统保管并限制权限，不把权限设置视为替代日志脱敏。

## 10. 业务 JSON 与持久化契约

### 10.1 每个业务调用一份结果，不是每个 API 一份结果

```text
Outputs/
├── 20261002T000000000000Z_library_demo01.json
├── 20261002T000000000000Z_library_demo01.runtime.jsonl
├── 20261002T010000000000Z_wishlist_demo02.json
├── 20261002T010000000000Z_wishlist_demo02.runtime.jsonl
├── 20261002T020000000000Z_game_demo03.json
└── 20261002T020000000000Z_game_demo03.runtime.jsonl
```

命名由 UTC 时间戳、功能名、随机短运行 ID 组成，避免同秒冲突。不要把任意用户输入直接拼进文件路径。重复执行不能覆盖之前结果。

无参数菜单本身不必导出空业务文件；每次实际选择一个业务功能分配新 `run_id` 并导出。`--help` 不产生业务输出。已进入执行阶段的失败或取消，在文件系统可写时也要生成具有状态的结果。

### 10.2 统一外壳

| 字段 | 必须表达的内容 |
|---|---|
| `schema_version` | 本项目导出格式版本，首版 `1.0.0`；不同于 Steam 的 GetSchemaForGame |
| `meta` | `run_id`、`feature`、开始/结束时间、目标 SteamID、语言、商店地区 |
| `status` | `ok`、`partial`、`failed`、`cancelled`、`needs_selection` |
| `data` | 功能结果；建议统一包含 `items`、`resolution`、`summary` |
| `id_map` | 所有导出 AppID 的名称解释 |
| `name_index` | 规范化名称到候选 AppID 数组的反向索引 |
| `coverage` | 来源范围、状态、取得时间、完整性证据与数量 |
| `errors` | 最终仍影响结果的规范化错误；每次尝试的历史留在 runtime 日志 |

不能仅因为一个瞬时失败后来重试成功，就把整个业务永久标为 `partial`。`partial` 表示最终仍有请求范围内的重要部分未取得。有效的“不在家庭”“无成就”“未提供可选字段”可以是正常业务结果，不能机械地把每个 `null` 都当失败。

关键清单全失败且没有取得目标业务数据时使用 `failed`；有主要结果但部分来源不可用时使用 `partial`。用户主动停止使用 `cancelled`，即使已经保留部分数据；不要覆盖成 `ok`。

### 10.3 单游戏记录

三个功能共用同一类 `GameRecord`，避免下游为同一个字段写三套解析：

| 数据块 | 主要字段/规则 |
|---|---|
| 标识 | `appid`、`name`、`app_type`、`store_url` |
| 拥有关系 | 第 5.4 节的独立拥有/共享字段 |
| 愿望单 | `present`、`priority`、`date_added`，不能猜测缺失值 |
| 游玩 | `subject_steamid`、`total_minutes`、`last_2weeks_minutes`、`last_played_at`、可用平台细分 |
| 成就 | `state`、`total`、`unlocked`、`completion_ratio`、逐 `apiname` 项目 |
| 玩家统计 | 原始统计键和值，保留来源；不强行命名为剧情进度 |
| 商店详情 | 简介、开发商、发行商、平台、类型、发行信息、地区价格等可用字段 |
| 来源状态 | 每个块的 `state`、`fetched_at`、来源工具、必要错误关联 |

只保留允许导出的数据字段；不要将整个原始响应无差别放入 `raw`。增加可选字段不能改变现有字段类型或空值语义。

### 10.4 结果完整性和索引

`coverage` 的 `complete=true` 只能说明已知响应契约及声明范围内取得完整结果，不等于证明 Steam 所有许可证、所有历史下架项或所有私人数据都已覆盖。没有完整性证据时使用 `false` 或 `null` 并说明原因。

每个 AppID 都必须进入 `id_map`；名称未知时保留 `canonical_name=null` 和明确状态，不能丢掉 ID。名称不能作为唯一键，因此 `name_index` 的值始终是数组。官方返回的本地化名称与用户别名分开，不把人工中文译名伪称为官方名称。

建议 `summary` 只做确定性计数和已知数据汇总。缺失指标存在时，必须同时输出已知项数量、缺失项数量，不能把“已知部分时长”命名为“完整总时长”。

### 10.5 合成示例

以下 SteamID、AppID、游戏名和时长均是合成测试数据，不是用户账号结果。示例展示“本人库部分完成、家庭凭据缺失、成就读取超时”的语义；可选商店字段作了压缩，部分补查故意用 `not_requested` 表示，并非声称所有计划查询均已执行。

```json
{
  "schema_version": "1.0.0",
  "meta": {
    "run_id": "demo01",
    "feature": "library",
    "started_at": "2026-10-02T00:00:00.000Z",
    "finished_at": "2026-10-02T00:00:40.000Z",
    "subject_steamid": "76561198000000000",
    "language": "schinese",
    "store_country": "CN"
  },
  "status": "partial",
  "data": {
    "items": [
      {
        "appid": 1000000001,
        "name": "示例游戏 A",
        "app_type": "game",
        "store_url": "https://store.steampowered.com/app/1000000001/",
        "ownership": {
          "owned_by_self": true,
          "owned_by_other_family_members": null,
          "available_via_family": null,
          "owner_steamids": null,
          "shared_exclusion_reason": null
        },
        "wishlist": {
          "present": null,
          "priority": null,
          "date_added": null
        },
        "playtime": {
          "subject_steamid": "76561198000000000",
          "total_minutes": 120,
          "last_2weeks_minutes": 30,
          "last_played_at": null,
          "platform_minutes": null
        },
        "achievements": {
          "state": "unavailable",
          "total": null,
          "unlocked": null,
          "completion_ratio": null,
          "items": [],
          "error_id": "err-achievement"
        },
        "user_stats": {
          "state": "not_requested",
          "values": null
        },
        "store": {
          "short_description": "合成样例；不是实际商店数据。",
          "price": null
        },
        "source_status": {
          "ownership_self": {
            "state": "ok",
            "source": "get_owned_games",
            "fetched_at": "2026-10-02T00:00:02.000Z"
          },
          "family": {
            "state": "unavailable",
            "source": "get_shared_library_apps",
            "fetched_at": null,
            "error_id": "err-family"
          },
          "wishlist": {
            "state": "not_requested",
            "source": "get_wishlist",
            "fetched_at": null
          },
          "playtime": {
            "state": "ok",
            "source": "get_owned_games",
            "fetched_at": "2026-10-02T00:00:02.000Z"
          },
          "store": {
            "state": "ok",
            "source": "get_app_details",
            "fetched_at": "2026-10-02T00:00:05.000Z"
          },
          "achievements": {
            "state": "unavailable",
            "source": "get_player_achievements",
            "fetched_at": null,
            "error_id": "err-achievement"
          }
        }
      }
    ],
    "resolution": null,
    "summary": {
      "items_count": 1,
      "known_self_owned_count": 1,
      "family_coverage_complete": false
    }
  },
  "id_map": {
    "1000000001": {
      "canonical_name": "示例游戏 A",
      "localized_names": {},
      "user_aliases": [],
      "name_state": "ok"
    }
  },
  "name_index": {
    "示例游戏 a": [
      1000000001
    ]
  },
  "coverage": {
    "personal_library": {
      "state": "ok",
      "complete": true,
      "scope": "get_owned_games_returned_games",
      "item_count": 1,
      "fetched_at": "2026-10-02T00:00:02.000Z"
    },
    "family_library": {
      "state": "unavailable",
      "complete": false,
      "item_count": null,
      "fetched_at": null,
      "error_id": "err-family"
    }
  },
  "errors": [
    {
      "error_id": "err-family",
      "code": "AUTH_REQUIRED",
      "source": "auth",
      "scope": "source",
      "api": "get_shared_library_apps",
      "appid": null,
      "subject_steamid": "76561198000000000",
      "exception_type": null,
      "http_status": null,
      "upstream_code": null,
      "message": "未配置本人家庭会话 token；家庭拥有情况未知"
    },
    {
      "error_id": "err-achievement",
      "code": "NETWORK_TIMEOUT",
      "source": "transport",
      "scope": "request",
      "api": "get_player_achievements",
      "appid": 1000000001,
      "subject_steamid": "76561198000000000",
      "exception_type": "ReadTimeout",
      "http_status": null,
      "upstream_code": null,
      "message": "允许的请求尝试已用尽；个人成就结果未知"
    }
  ]
}
```

`items=[]` 必须结合对应状态解释：上述成就为空数组表示该数据块不可用，并不表示游戏没有成就。外层 ID 映射还要覆盖名称候选中的 AppID，而不仅覆盖最终选中的游戏。

### 10.6 `persistence.py` 的写入规则

使用 UTF-8、可读缩进、`ensure_ascii=False`；禁止输出 `NaN`/`Infinity` 这类非标准 JSON 数值。排序保持确定性：例如业务项按 AppID 或明确的业务顺序排序，不按异步完成顺序随机漂移。

先在目标目录写临时文件，完成序列化与必要校验后再原子替换到本轮最终文件名；本轮文件名唯一，不能覆盖旧运行。成功返回最终路径，失败交错误机制处理。保存失败时不打印“导出成功”。

正常失败、用户停止时尽力保存已经完成的部分。若输出目录不可写、磁盘满、进程被强杀或机器断电，不能保证一定有业务 JSON；必须如实说明。不要在收尾中发新网络请求来“补完整”。

## 11. `start`、`stop` 与 CLI

### 11.1 必须支持的形式

```bash
./start                        # 前台菜单：愿望单 / 游戏库 / 游戏查询 / 退出
./start wishlist               # 直接执行并退出
./start library
./start game "巫师3"
./start game --appid 292030
./start game "https://store.steampowered.com/app/292030/"
./start doctor                 # 最小诊断，输出 JSON
./start --help
./stop
```

命令仅定义接口，不表示本文已经创建这些脚本。`doctor` 属于辅助诊断，由 `main.py` 组织并使用已有工具和监督能力，不为它额外新增第六个 scripts 职责文件。

`doctor` 至少检查配置是否存在、凭据是否已配置、输出可写性、工具注册情况和可用的少量只读网络探测。不能显示凭据值，不能为了诊断执行所有目录中的方法，也不能自动触发 Key 注册。没有凭据时正常报告能力不足，而不是全局崩溃。

若实现可选 `all`，仅编排愿望单与游戏库联合导出；单游戏查询仍需要显式输入。两份业务 JSON 共享本轮数据和运行 ID，并用一份 `all` runtime 日志关联；不要把三个脚本各跑一遍导致重复请求。可选命令须写入 README，不得影响必做项。

### 11.2 启动行为

`start` 使用 Bash 薄封装，将参数安全传给项目的 Python 入口。根据脚本位置定位项目，不要求用户先 `cd` 到特定路径。依赖缺失时给出安装命令；不在每次启动自动联网升级依赖。

Python 程序持有整个生命周期的单实例锁，实例信息位于 `.runtime/`，至少包含 PID、进程启动标识、项目绝对路径和运行身份。锁释放与实例信息清理要在异常退出路径上尽力执行。

首版前台运行，任务完成自动退出；菜单保持交互直至退出。没有 Web 服务器，也不因为需要 stop 就做后台守护进程。无参数启动但 stdin 不是交互终端时，显示用法并退出，不无限等待菜单输入。

### 11.3 停止行为

`stop` 只针对本项目当前实例。先确认锁和实例信息，校验 PID 对应的进程身份、启动时间和项目；不能只相信一个陈旧 PID 文件。身份无法确认时拒绝发送信号，提示检查。

不得使用 `pkill python`、`killall python` 或宽泛进程名匹配。重复 stop 无害；没有实例时清楚报告，不影响其他 Python 或本地模型进程。

优雅停止流程：

```text
收到 stop / SIGINT / SIGTERM
  → 标记取消，并记录 stop_requested
  → 停止派发新工作，唤醒/取消限速和重试等待
  → 在宽限内收集已完成结果
  → 取消剩余在途工作，正确处理 CancelledError
  → 生成 status=cancelled 的部分结果
  → 保存业务 JSON、刷新 runtime 日志
  → 关闭 HTTP 客户端、清理实例状态、释放锁
```

取消不得被宽泛异常捕获后转成可重试网络错误。不要以无限等待所有网络任务完成作为停止方案。默认不升级为无条件强杀；收尾失败要报告，不能误杀其他进程。

### 11.4 建议退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 目标业务按声明范围完成；或正常退出菜单/help |
| 2 | 部分成功，或名称需要选择；详细状态在 JSON |
| 1 | 执行失败、配置错误、输出/日志失败或内部错误 |
| 130 | 运行因用户停止而取消，尽力保留部分结果 |

这里只规定项目进程的最终状态；`stop` 命令的返回应反映其停止操作是否成功。JSON 的 `status` 作为下游判断依据，不从退出码猜测具体数据缺口。

## 12. 测试与验收标准

### 12.1 测试分成三类

**离线单元/契约测试：** 默认无外网，无 Key，无 token，使用合成 fixture 和可控 HTTP mock。  
**本地集成测试：** 测 start/stop、文件、日志、进程身份校验和取消；不误触其它进程。  
**授权真实联调：** 用户本地配置凭据后，低频验证少量样本，再做个人规模导出；默认测试命令不触发此类调用。

可使用 `pytest`，异步测试采用与运行方式一致的方案；HTTP mock 优先覆盖执行器边界。时间、sleep、随机抖动和 HTTP transport 应可替换，使重试测试不实际等待几十秒。

必须区分 fixture 数据与真实响应。真实 fixtures 提交前去掉凭据和不必要的账号信息；测试报告不包含私人库清单。

### 12.2 必测矩阵

| 编号 | 场景 | 期望 |
|---|---|---|
| A01 | 已知工具/未知工具/重复注册 | 正确路由；未知和重复明确失败 |
| A02 | 新增一个虚拟只读 API 工具 | 无需修改执行器、日志与已有 API 即可调用 |
| A03 | 没有 Key，但查询公开详情 | 可执行公开部分，账号数据标为未知 |
| A04 | 有 Key、无家庭 token | 自有库可导出；家庭为 unknown/unavailable，不是 false |
| A05 | 不同端点认证与参数编码 | 不向商店匿名入口发送个人 Key；Service 字段按契约编码 |
| B01 | 明确空愿望单 | 完整空结果；区别于私密/失败响应 |
| B02 | 愿望单 HTTP 200 但失败/异常结构 | 不导出伪成功的空愿望单 |
| B03 | 愿望单数量不一致或详情缺失 | 保留已知 AppID，标记覆盖不足，不静默删项 |
| B04 | 自有库零时长游戏 | 保留；不因时长为零过滤 |
| B05 | 本人玩过的家庭借用游戏 | 不误判本人持有，游玩数据主体仍是本人 |
| B06 | 家庭可共享但本人没玩过 | 出现在家庭候选；无证据的指标不填零 |
| B07 | 家人持有但被排除/未知枚举 | 分开表达持有与可共享；未知枚举不解释为允许 |
| B08 | 本人与家人都持有 | 两种持有字段可同时为 true |
| B09 | 家庭 token 失效、身份不匹配、列表截断 | 不声称完整家庭库；没有无上限重试 |
| B10 | 无成就、未请求、玩家成就失败 | 状态可区分；失败不算 0 解锁或 0% |
| B11 | 缺失两周字段、缺价、平台时长 | 不盲目补零，不把平台时长简单相加当总时长 |
| B12 | 同名本体/DLC、模糊名称、sub/bundle URL | 返回候选或明确不支持；不猜第一项 |
| B13 | AppID 已知但商店详情不可用 | 保留 ID 与已有名称，详情状态可解释 |
| C01 | 100 个合成目标并发查询 | 真实在途请求数不超过配置上限 |
| C02 | 请求返回极快 | 即使并发低，发送速率仍受限制 |
| C03 | 429 有秒数/日期 Retry-After | 正确等待；同 scope 新任务同步冷却 |
| C04 | 429 无 Retry-After、临时 5xx、超时 | 有限退避；总尝试数准确，没有多层重试 |
| C05 | 401/403、协议结构错误、证书错误 | 不无限重试，不关闭 TLS，不推断账户被盗/具体隐私 |
| C06 | 同一键同时由多个协程调用 | 共享在途请求；不同语言/地区/用户不得串用 |
| C07 | 预算耗尽、超长冷却、停止中的 sleep | 不提前违反冷却；等待可被取消 |
| C08 | 一款游戏预期失败、另一款成功 | 成功数据保留；未知内部错误也有明确终态 |
| D01 | 并发日志与重复初始化 | ID 对应正确，不串 AppID、不重复添加 handler |
| D02 | 临时失败重试后成功 | runtime 留下历史；最终 errors 不重复堆叠已恢复失败 |
| D03 | 秘密嵌入嵌套字段、URL、异常、代理信息 | 业务文件、runtime、控制台均不泄漏 |
| D04 | 同时间多轮输出、Unicode、非法浮点数 | 名称不冲突、UTF-8 可读、合法 JSON |
| D05 | 写入中失败、输出不可写、日志不可写 | 无伪成功；旧结果不损坏；无递归错误日志 |
| D06 | 运行中 stop、冷却中 stop、重复 stop | 保存已完成数据，正确取消且不误杀 |
| D07 | 陈旧或被复用的 PID | 身份校验失败，不对其它进程发送信号 |
| D08 | 非交互模式名称歧义 | 产生 needs_selection JSON，不等待输入 |
| D09 | 所有导出和候选 AppID | 都有 id_map 条目；反向名称索引始终为数组 |

### 12.3 少量真实样本的联调顺序

先验证公开单游戏详情，再用本人 Key 验证自有且玩过的游戏、近期时长和成就。家庭部分优先检查四类样本：本人持有、已借玩、可共享但未玩、家人有但被排除；用户家庭不存在某类样本时如实标记不可验证，不制造数据。

核对 `include_family_licenses` 的实际返回、用户成就主体、家庭共享排除含义和可能的截断。必要时由用户在 Steam 界面对照少量样本，而不是要求上传完整私人资料。

若只有 mock 通过，家庭接口仍必须标注“实现完成，真实账户未验证”。真实联调失败时记录接口、时间、脱敏参数形状、HTTP/上游状态、预期和实际差异；不要为通过测试而改成抓取另一人的数据。

### 12.4 并发性能验收

离线构造固定延迟的批量请求，对比并发 1 与并发 4 的完成耗时，测试中将速率限制设置成不成为瓶颈；验证确实存在受限并发而非名义 async、实际串行。不强求墙钟“恰好四倍”，保留调度与测试环境误差。

另设独立测试验证限速本身。真实 Steam 性能结果只报告实际规模、耗时、成功/失败/重试数，不把 mock 的加速比宣传为线上保证。

## 13. Codex 实施顺序

### 阶段 1：工程最小骨架与稳定契约

检查仓库后建立目录、配置模板、错误对象/决定、registry、请求执行器和最小 runtime。先完成一个模拟工具的 `registry → executor → 日志 → JSON` 闭环。明确输出与错误字段后再扩充接口。

交付证据：离线配置、路由、结果契约、脱敏和持久化测试通过。无真实凭据也必须能完成此阶段。

### 阶段 2：公开单游戏查询闭环

实现 appdetails、storesearch、精确 AppID 和商店 app URL 输入；补歧义处理、无凭据降级及 id_map/name_index。建立 start 的直接命令形式。

交付证据：公开路径 mock 测试、实际可达时的少量公开只读探测；网络不可达时不伪造 live 结果。

### 阶段 3：本人库与家庭高风险接口

实现本人库、近期记录、schema、玩家成就、统计适配器；尽早加入家庭身份与共享清单适配，不把家庭风险留到全部工程结束才验证。

有凭据即进行低频小样本验证；无凭据则完成 fixture、能力降级和测试，将待联调清单写出。

### 阶段 4：三个业务功能完成与并发复用

完成 library、wishlist、game 三个工作流，打通字段语义和结果输出；加入共享并发/限速、冷却、单处重试和在途请求复用。不要先建立全量应用数据库。

### 阶段 5：生命周期、诊断与验收

补齐菜单、doctor、start/stop 单实例和取消，运行完整测试矩阵。最后完善 README、示例配置和能力/限制说明。可选 all、完整名称目录仅在必做验收完成后添加。

每个阶段结束保留可运行状态，说明完成了哪些文件、执行过哪些测试和剩余风险。不要把“准备实现”“已经生成占位代码”记为功能完成。

## 14. 最终交付清单与完成定义

应交付项目代码、可执行的 `start`/`stop`、`.env.example`、明确依赖、README、自动测试、合成 JSON/日志示例，以及简短的实现与验证记录。真实 `.env` 由用户自行创建，不能作为交付物。

README 必须说明：WSL 安装与运行步骤、Key/token 的本地配置位置、公开模式能做什么、家庭接口的授权和未验证点、输出结构、错误码、并发参数和停止流程。安装步骤不得要求购买域名或部署网站。

最终报告以表格列出三个功能和支撑模块的实现/离线测试/真实联调状态。附上实际执行的命令与结果；没有执行的测试标为未执行，不以“应该通过”替代证据。

**demo 完成不要求每个游戏每个字段都非空，但要求：已取得数据正确、未知状态诚实、错误有来源、运行可追踪、停止不误杀、结构便于增加接口。**完整家庭支持的 live 验收尚未进行时，必须单独保留该限制，不能笼统宣称所有功能已实测可用。

## 15. 相对于用户口述方案的整理与补充清单

本节用于区分保留的要求和为落地增加的细节。Codex 后续再做实质调整，应继续维护这份记录。

| 项目 | 处理 | 说明 |
|---|---|---|
| Python、WSL、本地 demo | 保留 | 不升级成平台或网络服务 |
| Ports 工具化、可扩展注册层 | 保留并明确 | 程序启动登记一次，运行时查找调用；不是自动申请 Key |
| 每个 API 一个文件 | 保留 | 按接口方法拆；通用机制不复制到每个文件 |
| 根目录 `.env` | 保留 | 覆盖旧调研的仓库外凭据方案 |
| 三个业务脚本和持久化 | 保留 | 原来的四个职责文件继续存在 |
| 日志由 scripts 负责 | 按用户补充加入 | 增加 `runtime_debug.py`，合计五个职责文件 |
| 独立错误处理器与错误码 | 按用户补充加入 | 根目录 `error_handler.py` 统一分类和恢复决策 |
| 不让自定义 client 承担恢复策略 | 按已确认调整 | 使用 `request_executor.py` 落实 HTTP 和决策；不再建项目级 client.py |
| runtime debug 监督层 | 明确范围 | 进程内、事件与进度可追踪，不是外部自愈 Agent |
| 时间戳＋功能输出 | 保留并补充 | 添加短运行 ID 防冲突，业务一轮一份 JSON |
| 日志格式 | 已讨论方案的具体化 | JSONL 与业务 JSON 分开，以 run_id 关联 |
| main、config、.runtime、tests | 实现补充 | 入口装配、统一配置、单实例安全和验证；不是新增业务层 |
| 并发与网络控制 | 实现补充 | 真实请求层 semaphore、按域名限速、共享冷却、一次决策一次执行 |
| 默认参数、错误码、退出码 | 实现补充 | 可调整但需文档一致；不称为 Steam 官方规定 |
| JSON 三值语义、coverage、来源时间 | 实现补充 | 防止把失败误写成 false/0 或冒充完整结果 |
| single-flight 运行内复用 | 实现补充 | 防并发重复请求；不引入持久缓存服务 |
| 候选与实体类型处理 | 实现补充 | 不用模糊第一项猜游戏，AppID 与包/合集 ID 分开 |
| 全量名称目录、all、跨运行缓存 | 范围收敛 | 前两项可选；跨运行缓存不在首版，不阻塞当前功能 |
| 真实账号验证状态 | 明确新增验收要求 | 实现完成、mock 通过和真实数据验证分别报告 |

## 16. 资料与证据索引

### 16.1 本次整理使用的既有文件

**[D01]《Steam 本地导出工具：API 调研与开发方案》**  
文件：`Steam_API_Research_and_Development_Plan_2026-10-02.md`。  
用于业务语义、权限边界及前期接口研究。其架构、凭据位置和部分参数建议已由本文覆盖。旧报告明确未完成本人账号实测，不得把它引用成成功运行证明。

**[D02]《接口清单》**  
文件：`steam_api_inventory_2026-10-02.json`。  
记录 21 个与项目相关的候选入口，包含可选与登录辅助接口；不是要求全部实现，也不是 Steam 个人 API 总数。清单的 `live_tested=false` 应被保留为验证边界。

### 16.2 本次核对的官方/原始技术资料

以下资料在本任务书整理时核对；引用只支持相关协议和机制，不代表已执行本地或账户测试。

**[R01] Valve — Authentication using Web API Keys**：个人与发行商 Key、请求头认证。  
`https://partner.steamgames.com/doc/webapi_overview/auth`

**[R02] Valve — IPlayerService**：本人库、近期记录、Service 参数编码及可见性。  
`https://partner.steamgames.com/doc/webapi/IPlayerService`

**[R03] Valve — ISteamUserStats**：GetSchemaForGame、GetPlayerAchievements、GetUserStatsForGame。  
`https://partner.steamgames.com/doc/webapi/ISteamUserStats`

**[R04] Valve — IStoreService**：GetAppList、分页及参数编码。  
`https://partner.steamgames.com/doc/webapi/IStoreService`

**[R05] HTTPX — Async Support**：AsyncClient 与连接复用。  
`https://www.python-httpx.org/async/`

**[R06] HTTPX — Timeouts**：连接、读取、写入和连接池超时。  
`https://www.python-httpx.org/advanced/timeouts/`

**[R07] RFC 6585 §4**：429 Too Many Requests 与可选 Retry-After。  
`https://www.rfc-editor.org/rfc/rfc6585.html`

**[R08] RFC 9110 §10.2.3**：Retry-After 的秒数与日期语义。  
`https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after`

### 16.3 沿用前期调研、实现前需复核的协议/原项目资料

这些是 Valve 数据的跟踪快照或开源实现，不等于 Valve 对内部接口的稳定性承诺。本文没有重新对这些接口做真实账号调用；开发时记录具体版本或 commit 和验证结果。

**[T01] SteamTracking — IPlayerService 机器接口描述**  
`https://github.com/SteamTracking/SteamTracking/blob/master/API/IPlayerService.json`

**[T02] SteamTracking — Wishlist 协议**  
`https://github.com/SteamTracking/Protobufs/blob/master/webui/service_wishlist.proto`

**[T03] SteamTracking — FamilyGroups 协议**  
`https://github.com/SteamTracking/Protobufs/blob/master/webui/service_familygroups.proto`

**[T04] SteamDB 浏览器扩展 — 家庭数据读取实现**  
`https://github.com/SteamDatabase/BrowserExtension/blob/master/scripts/background.js`

**[T05] OpenCLI — Steam 商店搜索与详情适配器文档**  
`https://github.com/jackwener/OpenCLI/blob/main/docs/adapters/browser/steam.md`

---

**给 Codex 的最终执行要求：按上述边界实现最小可运行版本。不要只返回设计建议，不要用占位成功掩盖未实现，不要因缺少私人凭据停掉可以离线完成的工作。最后提交清晰的实现、测试、待验证与变更记录。**
