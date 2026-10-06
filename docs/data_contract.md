# Steam Tool 正式数据契约

## 1. 状态与版本

本文件是 `games`、`library`、`wishlist` 的正式输出规范，合并 Base Contract 与 Feature Contract。当前 `schema_version` 为 **2.0.0**，唯一代码常量为 `schema/version.py::SCHEMA_VERSION`。

Python 实现在 `schema/base.py`、`schema/feature.py`，使用 dataclass，并通过 `to_dict()` 序列化为保留字段顺序、保留 `null` 的 JSON 对象。模型不将 `false`、`0`、`-1` 或字符串数字互相强制转换。

与历史 1.1.0 相比，2.0.0 改变 Result 外壳、数据块元信息层级、部分字段名称和 Record 组成，属于破坏性格式升级。旧结果不被自动改写成新版本。CLI 软件版本与数据契约版本独立。

## 2. 范围

基础层定义可复用的数据块；Feature 层组合这些数据块，并定义 Summary、Coverage、Record 与 Run 状态。所有 Record 以整数 AppID 为主标识；名称不是稳定主键。

本规范不保存整块 API 原始响应，也不推断尚未确认的数据来源或 App 关系图。

## 3. 共用语义

- `null` 表示未知、未取得或无法确认，不能转成确定的 `false`、`0` 或 `-1`。
- SteamID64 在 `subject_steamid` 和字典 key 中均保持字符串。`included_apps` 的 AppID key 同样保持字符串。
- 输出的运行、采集时间采用带显式 `+08:00` 的 ISO 8601 格式，即北京时间。例如 `2026-10-07T10:20:35+08:00`。这沿用本项目已确认的输出时区，覆盖输入资料中的 UTC 示例；时间点本身不改变。
- 成就解锁、最后游玩和愿望单添加时间是整数 Unix timestamp，保留原值，不增加八小时。
- 每块 `meta` 描述本次声明范围内取得的数据。未知字段合法，但不能将缺失的必要证据宣称为完整。
- 定价保留上游的最小货币单位；格式化字符串和汇率换算不属于本规范。

## 4. Base Data Contract

### 4.1 Meta

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `state` | `ok / partial / unavailable / not_applicable / not_requested` | 数据块最终状态 |
| `source` | string / string[] / object / null | 实际单来源或多来源信息 |
| `fetched_at` | string / array / object / null | 上游成功取得时间；多来源可分别记录 |
| `error_id` | string / null | 引用根级规范化 Error |

`ok` 表示当前查询范围取得成功；`partial` 表示存在有效数据但完整性不足；`unavailable` 表示本次无法取得；`not_applicable` 表示对象客观上无此能力或不适用；`not_requested` 表示本次没有请求。

`not_requested` 不等于 `unavailable`。网络执行器的 `failed`、`data_unavailable` 等运行结果不直接进入 `Meta.state`，未取得的基础块适配为 `unavailable`，具体原因保留在 Error 中。

`source` 可以是工具名称字符串、名称数组或来源映射。`fetched_at` 可以是单个 ISO 时间、时间数组或按来源组织的映射。映射与数组的内部组织未被输入契约进一步冻结，Python 模型不施加额外的结构限制。顶层存在运行起止时间不能替代每块的采集时间。

### 4.2 GameIdentity

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 来源和状态 |
| `appid` | integer | Steam App 的稳定主标识 |
| `name` | string / null | 当前取得的名称 |
| `app_type` | string / null | App 类型，不使用封闭枚举 |

`game`、`dlc`、`demo`、`software` 等类型均可保留。没有可靠类型映射时使用 `null`，不解释未知的数字类型。名称缺失不能导致一个已知 AppID 被删除。

### 4.3 Market

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 来源和状态 |
| `region` | string | 当前 Steam 国家/地区代码，例如 CN、US |
| `released` | boolean / null | 已正式发售 / 尚未发售 / 未知 |
| `availability` | boolean / null | 当前地区可购买或获取 / 不可获取 / 未知 |

`released=true` 与 `availability=false` 可以表达已发售但本地区不可获取。`released=false` 与 `availability=true` 是需复核来源的异常组合。取得商店详情不等于确认可购买，不能因此填入 `availability=true`。

### 4.4 Ownership

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 可记录本人库和家庭库多个来源 |
| `owned_by_self` | boolean / null | 本人是否确认拥有 |
| `owned_by_other_family_members` | boolean / null | 其他家庭成员是否确认拥有 |
| `available_via_family` | boolean / null | 本人是否确认具备家庭共享资格 |
| `owners` | object / null | SteamID64 字符串到昵称信息的映射 |

三个布尔值独立，不是互斥类别。同一个 App 可以由本人和其他家庭成员共同持有。完整、范围明确的证据才能支持 `false`；未知保留 `null`。共享资格不表示某一瞬间许可证是否空闲。借玩记录不能证明本人拥有。

`owners` 的每个 value 仅包含 `persona_name: string | null`。SteamID 已知而昵称未知时保留该 key，并使用 `persona_name=null`；昵称可变化，不能作为主标识。已确认没有拥有者可用 `{}` 表达，未取得名单使用 `null`。

### 4.5 Wishlist

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 来源和状态 |
| `present` | boolean / null | 确认在愿望单 / 不在 / 无法确认 |
| `priority` | integer / null | 上游优先级；0 是有效值 |
| `date_added` | integer / null | 加入愿望单的 Unix timestamp |

不在愿望单或无法取得的优先级、添加时间均为 `null`。没有充分的完整清单证据不能把缺少条目解释为 `present=false`。

### 4.6 Playtime

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 本人游玩数据的来源和状态 |
| `total` | integer / null | 累计游玩时间 |
| `last_2weeks` | integer / null | 最近两周游玩时间 |
| `last_played_at` | integer / null | 最后游玩的 Unix timestamp |
| `unit` | string | 当前为 minutes |
| `platform` | PlaytimePlatform | 固定四个平台字段 |

`total`、`last_2weeks` 是非负整数或 `null`。`total=0` 表示确认没有游玩时间；`total=null` 表示无法确认。缺少两周时间不能补零。平台时间不得相加替代累计时间。

#### PlaytimePlatform

| 字段 | 类型 |
| --- | --- |
| `windows` | integer / null |
| `mac` | integer / null |
| `linux` | integer / null |
| `deck` | integer / null |

平台字段固定保留，且都使用 `Playtime.unit`：

- 大于 0：已知在该平台上的游玩时间。
- 0：该平台支持/发行范围内，确认本人没有在该平台游玩。
- -1：已确认游戏不支持或未发行于该平台。
- `null`：无法确认平台信息。

没有平台游玩记录不能自动填 -1。平台 sentinel 不适用于累计或两周总时长。

### 4.7 Achievements

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 汇总或明细的来源和状态 |
| `total` | integer / null | 成就总数；-1 表示确认无成就系统 |
| `unlocked` | integer / null | 本人解锁数；无成就系统时同为 -1 |
| `completion_ratio` | number / null | 有可靠数据且 total>0 时为 unlocked/total |
| `items` | Achievement[] / null | 本次取得的逐项成就明细 |

`items=null` 只表示当前结果没有逐项明细，不能证明无成就系统，也不单独使 Record 变为 `partial`。汇总可以完整而 `items=null`；无法确认汇总时保留 `null`，不能补零。

确认无成就系统时必须同时使用：`total=-1`、`unlocked=-1`、`completion_ratio=null`、`items=null`、`meta.state=not_applicable`。只有正面的无能力证据才能支持此表达；玩家记录不可用不能推翻明确存在成就定义的证据。

#### Achievement

| 字段 | 类型 |
| --- | --- |
| `apiname` | string |
| `display_name` | string / null |
| `description` | string / null |
| `unlocked` | boolean / null |
| `unlock_time` | integer / null |

以 `apiname` 关联定义与玩家记录。解锁时间保留 Unix timestamp，未知解锁状态不变成 `false`。

### 4.8 Price

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 独立价格块的来源和状态 |
| `type` | paid / free / null | 付费 / 永久免费或 F2P / 未知 |
| `currency` | string / null | 上游币种，例如 CNY、USD、JPY |
| `initial` | integer / null | 原始价格，最小货币单位 |
| `final` | integer / null | 当前价格，最小货币单位 |

永久免费产品使用 `type=free`，且 `currency`、`initial`、`final` 均为 `null`。100% 折扣的付费产品仍是 `type=paid`，其 `final=0` 是有效价格；不能根据零价格单独推断免费。

不持久化 `discount_percent`、`initial_formatted`、`final_formatted`。折扣比例与格式化价格属于派生或展示数据。

### 4.9 Bundles

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `meta` | Meta | 整个 Bundle 集合的来源和状态 |
| `items` | Bundle[] / null | 已取得的 Bundle 列表，或未取得 |

#### Bundle

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `bundle_id` | integer | 稳定 Bundle ID |
| `name` | string / null | 当前名称 |
| `price` | PriceValue | 仅复用 Price 的四个业务字段 |
| `included_apps` | object | AppID 字符串到名称或 null 的映射 |

未知 App 名称必须保留其 AppID key，例如 `{"123456": null}`。

#### PriceValue

字段按顺序为 `type`、`currency`、`initial`、`final`，类型与语义同 Price；不含 `meta`，来源继承外层 `Bundles.meta`。

## 5. Feature Contract

### 5.1 Result 外壳与字段顺序

| Result | 固定顶层字段，按序 |
| --- | --- |
| GamesResult | schema_version, run, summary, errors, items |
| LibraryResult | schema_version, run, summary, coverage, errors, items |
| WishlistResult | schema_version, run, summary, coverage, errors, items |

GamesResult 没有 `coverage` 字段。LibraryResult 和 WishlistResult 必须有相应 Coverage。`items` 分别是 GameRecord[]、LibraryRecord[]、WishlistRecord[]，总是数组，不是 `null`。

新外壳不包含历史格式的顶层 `meta`、`status`、`data`、`id_map` 或 `name_index`。状态位于 `run.status` 和各 Record 的 `status`。

### 5.2 Run

| 字段 | 类型 |
| --- | --- |
| `run_id` | string |
| `feature` | games / library / wishlist |
| `started_at` | string，ISO 8601 |
| `finished_at` | string / null，ISO 8601 |
| `subject_steamid` | string / null |
| `status` | ok / partial / failed / cancelled |

Run 与 Result 的功能类型必须一致。`ok` 表示在当前契约范围完成；`partial` 表示有有效结果，但必要数据、记录或集合完整性有缺失；`failed` 表示无可用业务结果或核心流程失败；`cancelled` 表示用户主动终止并保留已取得的部分。

Record 状态统一为 `ok / partial / failed`。身份不可取得、无法形成有意义的目标记录时为 `failed`；有效身份存在但必要块未取得、未请求或不完整时为 `partial`；要求的各块均为 `ok` 或 `not_applicable` 时为 `ok`。

`not_applicable` 本身不是错误；可选明细 `items=null` 本身不是不完整。Run 聚合优先保留 `cancelled`，随后是核心流程失败；全部 Record 失败则 Run 失败，有部分有效记录则表达必要数据缺口。已确认的空集合可为 `ok`，来源不可用不能假装成成功空集合。

### 5.3 Error 引用

`errors` 是现有 `steamtool.error_handler.Failure.info` 的规范化错误数组，不建立第二套错误类型或恢复系统。保留其既有字段：`error_id`、`code`、`source`、`scope`、`api`、`appid`、`subject_steamid`、`exception_type`、`http_status`、`upstream_code`、`message`。

`error_id` 是唯一字符串。多个块可引用同一个根级错误；块内不复制完整 Error。非空 `meta.error_id` 必须在根级 `errors` 中存在。已恢复的瞬时失败不进入最终业务错误集合。

输入阶段被修正或放弃的非法项不属于业务查询，不进入 `errors`。已进入查询阶段后的解析、API、认证、权限和数据错误才进入根级集合。无法解析为明确 AppID 的业务目标只保留规范化错误，不制造占位 AppID 或不合法 Record。

### 5.4 Games

#### GameRecord

固定字段顺序：`status`、`identity`、`market`、`ownership`、`wishlist`、`playtime`、`achievements`、`price`、`bundles`。八个基础块全部保留，不能为减少请求而删除字段。

#### GamesSummary

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `game_count` | integer | 已形成的 GameRecord 总数 |
| `ok_count` | integer | status=ok 的记录数 |
| `partial_count` | integer | status=partial 的记录数 |
| `failed_count` | integer | status=failed 的记录数 |

三项状态计数之和等于 `game_count`。同一明确 AppID 的重复目标合并为一个 Record。Games Summary 不增加总价格、总时长或平均成就率。

### 5.5 Library

#### LibraryRecord

固定字段顺序：`status`、`identity`、`ownership`、`playtime`、`achievements`。不包含 `market`、`wishlist`、`price`、`bundles`。

Library 保持扁平库存。上游自然返回的独立 DLC App 可作为一个 Record 保留；没有类型证据时 `app_type=null`。不建立 `parent_app`、`dlcs`、`bundle_relationship`。

#### LibrarySummary

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `total_count` | integer | LibraryRecord 总数 |
| `self_owned_count` | integer | owned_by_self=true 的数量 |
| `family_owned_count` | integer | owned_by_other_family_members=true 的数量 |
| `family_available_count` | integer | available_via_family=true 的数量 |
| `played_count` | integer | playtime.total>0 的数量 |
| `unplayed_count` | integer | playtime.total=0 的数量 |
| `playtime_unknown_count` | integer | playtime.total=null 的数量 |
| `played_ratio` | number / null | played_count / 已知时长数量 |
| `unplayed_ratio` | number / null | unplayed_count / 已知时长数量 |
| `total_playtime` | integer | 只累加已知 playtime.total |
| `playtime_unit` | string | 上述总和的单位，当前 minutes |
| `ranking_limit` | integer | 本次实际采用的 Top-N，非负整数 |
| `top_total_playtime` | PlaytimeRankingItem[] | 累计时长降序排行榜 |
| `top_last_2weeks_playtime` | PlaytimeRankingItem[] | 两周时长降序排行榜 |

Ownership 三项分别计数，不互斥。比例的分母只使用 `played_count+unplayed_count`；分母为零时两个比例为 `null`。未知时长不计入未玩，不参与累计；已知部分总和不能宣称为完整的账户总时长。不同单位不能相加。

#### PlaytimeRankingItem

固定字段：`rank`（integer）、`appid`（integer）、`name`（string / null）、`playtime`（integer）、`unit`（string）。

排名从 1 开始，最多 N 项；`null` 不进入榜单，0 是有效已知值。时长相同按 AppID 升序，以保证稳定结果。N=0 表示空榜单；默认 N 属于 Feature 配置，不属于 Base 契约。

#### LibraryCoverage

固定字段：`self_library`、`family_library`（均为 CollectionCoverage）、`playtime`、`achievements`（均为 BlockCoverage）。

- `self_library`、`family_library` 描述相关源的集合完整性和当前返回的不同 AppID 数量。
- `playtime.known_count` 只计 `total` 已知的记录，0 包含在内。
- `achievements.known_count` 计总数与解锁数均已知的记录，确认无系统的 -1 也属于已知。
- 没有成就明细不会降低一个已完整汇总的 Coverage。

### 5.6 Wishlist

#### WishlistRecord

固定字段顺序：`status`、`identity`、`market`、`ownership`、`wishlist`、`price`、`bundles`。不包含 `playtime`、`achievements`。

愿望单条目以 AppID 保留，详情缺失、下架或地区不可读不能导致静默丢失。

#### WishlistSummary

固定字段：`total_count`（integer）、`price_ranking`（WishlistPriceRankingItem[]）。

#### WishlistPriceRankingItem

固定字段：`rank`（integer）、`appid`（integer）、`name`（string / null）、`type`（paid / free / null）、`price`（integer / null）、`currency`（string / null）。

付费产品以 `Price.final` 排序，免费产品明确通过 `Price.type=free` 识别，并以 0 排序。已知价格低到高，未知价格在后；同价或同为未知时按 AppID 升序。排名从 1 开始。100% 折扣的付费产品保留 `type=paid`。

排序保留本次市场查询的原始币种与金额，不做跨币种折算，也不把未知金额当零。

#### WishlistCoverage

固定字段：`wishlist`（CollectionCoverage）、`market`、`ownership`、`price`、`bundles`（均为 BlockCoverage）。

`wishlist` 表达清单主体的状态、完整性与不同 AppID 数量，其余四项表达当前条目范围内数据块的取得情况。

### 5.7 Coverage 共用结构

#### CollectionCoverage

| 字段 | 类型 |
| --- | --- |
| `state` | 与 Meta.state 相同 |
| `complete` | boolean / null |
| `count` | integer / null |

#### BlockCoverage

| 字段 | 类型 |
| --- | --- |
| `state` | 与 Meta.state 相同 |
| `complete` | boolean |
| `known_count` | integer |
| `missing_count` | integer |

已接受的 `ok / not_applicable` 块计入已知，或按上面声明的具体维度判定已知。两项计数之和等于当前 Record 数。全已知为 `ok`，部分已知为 `partial`；没有取得该维度为 `unavailable`，全部未请求可为 `not_requested`。已确认空条目范围的附加块 Coverage 为 complete=true、计数为零；主体是否完整仍由 CollectionCoverage 单独表达。

Coverage 描述集合/维度完整性，不是 Summary 业务统计。没有任何条目且主体集合未确认完整时，附加维度同样为 unavailable、complete=false，不把未取得清单当作已确认空集合。`complete=true` 只表示当前已知接口契约与声明范围内完整，不能解释为覆盖全部历史 Steam 许可证、所有下架内容或所有私人数据。上游家庭源仍有未验证的完整性限制时必须保留 complete=false；不能为输出成功而改成 true。

## 6. Null 与 Sentinel 核对

| 表达 | 含义 |
| --- | --- |
| 布尔字段 null / false | 未知 / 确认否定 |
| Playtime.total null / 0 | 未知 / 确认零游玩 |
| PlaytimePlatform null / 0 / -1 | 平台未知 / 已知零时间 / 确认不支持或未发行 |
| Achievements.total 与 unlocked 同为 -1 | 确认无成就系统 |
| Achievements.items=null | 本次无逐项明细，不是无成就系统 |
| Price.type=free | 永久免费，三个价格字段均为 null |
| Price.type=paid 且 final=0 | 付费产品当前零价格，可为 100% 折扣 |
| 集合 null / [] | 未取得集合 / 已取得空集合 |

## 7. 版本管理

Base 与 Feature 共同受 `SCHEMA_VERSION=2.0.0` 管理。未来破坏性层级、字段类型或空值语义变化必须升级版本。代码生成的 Result 不能用旧版本号伪装新结构，也不能只升级文档而不升级代码。

未冻结的 API 到基础块映射不由模型猜测实现。无法确认的事实使用 `null` 和相应状态；来源缺失不等于确定为空、免费、未玩、不拥有或不支持。

## 8. 范围外

CLI 输入交互、输入纠错、成就明细参数、请求调度、并发、限流、重试和 Runtime Debug 属于运行层，参见 [运行逻辑说明](Steam_Tool_Runtime_Logic_Notes.md)。本规范不展开其执行细节。

当前不包括 `store_url`、原始 store 对象、Stats、折扣率、格式化价格、`shared_exclusion_reason`、DLC/Parent-App/Bundle 关系图、完整 App Graph、账户总消费和购买历史。没有完整 API 映射的数据块不得通过新增爬虫或未经确认的新来源强行填满。

历史结果、诊断结果与保留的旧单游戏兼容输出不属于本规范；读取时必须先检查各自声明的 schema_version。两份输入数据契约保留为设计来源，本文件是新三功能输出的有效契约。
