# Steam Tool 基础数据契约

**文档状态：Draft / 当前讨论冻结版**  
**用途：定义 Steam Tool 各业务功能可复用的基础数据结构。**  
**边界：本文件只定义数据结构与字段语义，不定义具体 Feature 的调用组合、CLI 交互流程、重试策略或 API 调度逻辑。**

---

## 1. 设计原则

当前基础数据层不再以 `GameRecord` 作为最底层结构。

基础层由以下部分组成：

```text
Meta
GameIdentity
Market
Ownership
Wishlist
Playtime
Achievements
Price
Bundles
```

其中：

- `Meta` 是所有可查询数据模块共用的底层元信息结构。
- `GameIdentity` 描述 Steam App 的基本身份。
- `Market` 描述当前查询地区下的发行与可用状态。
- 其余模块描述具体业务事实。
- `GameRecord`、`LibraryRecord`、`WishlistRecord` 等属于后续 Feature 层输出，由具体功能按需组合这些基础模块，不在本文中定义。

基础层原则：

1. 不为了“以后可能有用”提前保留没有当前业务价值的字段。
2. 可计算字段原则上不重复持久化。
3. `null` 表示未知、未取得或无法确认，不能与确定的 `false`、`0`、`-1` 混用。
4. 稳定 ID 作为主标识，名称仅作为附属信息。
5. API 原始对象不整块写入业务 JSON，只保留明确进入本契约的字段。

---

# 2. Meta

所有可查询模块统一包含：

```text
Meta
├── state
├── source
├── fetched_at
└── error_id
```

推荐 JSON 形式：

```json
{
  "meta": {
    "state": "ok",
    "source": "get_app_details",
    "fetched_at": "2026-10-07T01:20:35Z",
    "error_id": null
  }
}
```

## 2.1 `state`

描述当前数据块的最终数据状态。

当前允许的语义：

```text
ok
partial
unavailable
not_applicable
not_requested
```

含义：

- `ok`：本数据块按当前查询范围成功取得。
- `partial`：取得了部分有效数据，但完整性不足。
- `unavailable`：本次无法取得数据。
- `not_applicable`：该对象客观上不存在这一数据能力或该字段不适用。
- `not_requested`：本次 Feature 没有请求这一数据块。

`not_requested` 与 `unavailable` 必须区分：

```text
not_requested = 没有查
unavailable   = 查了，但没拿到
```

## 2.2 `source`

记录该数据块实际使用的数据来源。

单来源时可以表示为：

```json
"source": "get_app_details"
```

多来源数据块允许记录多个来源，例如：

```json
"source": [
  "get_owned_games",
  "get_shared_library_apps"
]
```

具体序列化形式可在实现阶段统一，但不得丢失来源信息。

## 2.3 `fetched_at`

记录该数据实际从上游成功取得的时间。

时间统一采用 UTC ISO 8601 格式，例如：

```text
2026-10-07T01:20:35Z
```

多来源数据块允许分别记录各来源取得时间。

`fetched_at` 保留在基础契约中，不因顶层存在 `started_at` / `finished_at` 而删除。

## 2.4 `error_id`

```text
string | null
```

指向本次运行错误系统中的规范化错误对象。

无错误时：

```json
"error_id": null
```

---

# 3. GameIdentity

`GameIdentity` 描述 Steam App 的基础身份。

```text
GameIdentity
├── meta: Meta
├── appid
├── name
└── app_type
```

结构：

```json
{
  "identity": {
    "meta": {
      "state": "ok",
      "source": "get_app_details",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "appid": 292030,
    "name": "The Witcher 3: Wild Hunt",
    "app_type": "game"
  }
}
```

字段：

### `appid`

```text
integer
```

Steam AppID，是 App 的稳定主标识。

### `name`

```text
string | null
```

当前取得的 App 名称。

名称不是稳定主键。

### `app_type`

```text
string | null
```

Steam App 类型，例如可能出现：

```text
game
dlc
demo
software
```

本契约暂不建立封闭枚举，避免未来 Steam 返回新的类型时破坏兼容性。

---

# 4. Market

`Market` 描述当前查询地区下的发行与可获取状态。

```text
Market
├── meta: Meta
├── region
├── released
└── availability
```

示例：

```json
{
  "market": {
    "meta": {
      "state": "ok",
      "source": "get_app_details",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "region": "CN",
    "released": true,
    "availability": true
  }
}
```

## 4.1 `region`

```text
string
```

当前市场查询对应的 Steam 国家/地区代码，例如：

```text
CN
US
JP
DE
```

## 4.2 `released`

```text
boolean | null
```

- `true`：已正式发售。
- `false`：尚未正式发售。
- `null`：无法确认。

## 4.3 `availability`

```text
boolean | null
```

表示当前 `region` 下是否能够正常购买或获取。

- `true`：当前地区可以正常取得。
- `false`：当前地区不可正常取得。
- `null`：无法确认。

典型组合：

| released | availability | 含义 |
|---|---|---|
| `true` | `true` | 已发售，当前地区可正常购买/获取 |
| `false` | `false` | 当前地区存在发行预期，但尚未发售 |
| `true` | `false` | 已发售，但当前地区不可购买/获取 |
| `null` | 任意 | 无法确定发行状态 |
| 任意 | `null` | 无法确定当前地区可用状态 |

`released = false && availability = true` 视为异常组合，应由实现层重新核验数据来源。

---

# 5. Ownership

```text
Ownership
├── meta: Meta
├── owned_by_self
├── owned_by_other_family_members
├── available_via_family
└── owners
```

示例：

```json
{
  "ownership": {
    "meta": {
      "state": "ok",
      "source": [
        "get_owned_games",
        "get_shared_library_apps"
      ],
      "fetched_at": {
        "owned": "2026-10-07T01:20:35Z",
        "family": "2026-10-07T01:20:37Z"
      },
      "error_id": null
    },
    "owned_by_self": true,
    "owned_by_other_family_members": true,
    "available_via_family": true,
    "owners": {
      "76561199834898167": {
        "persona_name": "Player A"
      },
      "76561199482341171": {
        "persona_name": "Player B"
      }
    }
  }
}
```

## 5.1 `owned_by_self`

```text
boolean | null
```

- `true`：已确认本人拥有。
- `false`：已确认本人不拥有。
- `null`：没有足够数据判断。

## 5.2 `owned_by_other_family_members`

```text
boolean | null
```

- `true`：已确认当前家庭中的其他成员至少有一人拥有。
- `false`：在当前已确认的完整家庭范围内，没有其他成员拥有。
- `null`：家庭信息不足，无法判断。

## 5.3 `available_via_family`

```text
boolean | null
```

表示本人当前是否具备通过 Steam Family 获得该 App 的共享资格。

该字段描述家庭共享资格，不描述某一时刻许可证是否正在被其他成员占用。

## 5.4 `owners`

```text
object | null
```

以 SteamID64 字符串作为 key，同时保存可取得的昵称信息。

```json
{
  "76561199834898167": {
    "persona_name": "Player A"
  }
}
```

规则：

- SteamID64 必须按字符串保存。
- SteamID 是稳定身份标识。
- `persona_name` 只是附属展示信息，可变化。
- 如果能确认 SteamID 但无法取得昵称：

```json
{
  "76561199834898167": {
    "persona_name": null
  }
}
```

---

# 6. Wishlist

```text
Wishlist
├── meta: Meta
├── present
├── priority
└── date_added
```

示例：

```json
{
  "wishlist": {
    "meta": {
      "state": "ok",
      "source": "get_wishlist",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "present": true,
    "priority": 0,
    "date_added": 1791330000
  }
}
```

## 6.1 `present`

```text
boolean | null
```

- `true`：已确认在愿望单中。
- `false`：已确认不在愿望单中。
- `null`：无法确认。

## 6.2 `priority`

```text
integer | null
```

Steam 返回的愿望单优先级。

不在愿望单或无法取得时为 `null`。

## 6.3 `date_added`

```text
integer | null
```

加入愿望单的 Unix timestamp。

基础数据层保留原始时间戳，不负责格式化成人类可读日期。

---

# 7. Playtime

```text
Playtime
├── meta: Meta
├── total
├── last_2weeks
├── last_played_at
├── unit
└── platform
    ├── windows
    ├── mac
    ├── linux
    └── deck
```

示例：

```json
{
  "playtime": {
    "meta": {
      "state": "ok",
      "source": "get_owned_games",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "total": 12345,
    "last_2weeks": 320,
    "last_played_at": 1791330000,
    "unit": "minutes",
    "platform": {
      "windows": 12000,
      "mac": 0,
      "linux": 0,
      "deck": -1
    }
  }
}
```

## 7.1 `total`

```text
integer | null
```

累计游玩时间。

实际单位由 `unit` 指定。

## 7.2 `last_2weeks`

```text
integer | null
```

最近两周游玩时间。

`0` 与 `null` 必须区分：

```text
0    = 已确认最近两周游玩 0
null = 没有足够数据判断
```

## 7.3 `last_played_at`

```text
integer | null
```

最后一次游玩的 Unix timestamp。

## 7.4 `unit`

```text
string
```

当前使用：

```text
minutes
```

`total`、`last_2weeks` 与 `platform` 的数值均使用该单位。

## 7.5 `platform`

固定保留：

```text
windows
mac
linux
deck
```

每个平台字段语义：

```text
> 0   = 已知在该平台上的游玩时间
0     = 游戏支持/发行于该平台，但本人没有在该平台游玩
-1    = 游戏不支持或未发行于该平台
null  = 当前无法确认该平台信息
```

禁止因为“没有该平台游玩记录”就自动填 `-1`。

---

# 8. Achievements

```text
Achievements
├── meta: Meta
├── total
├── unlocked
├── completion_ratio
└── items
```

完整结构：

```json
{
  "achievements": {
    "meta": {
      "state": "ok",
      "source": [
        "get_schema_for_game",
        "get_player_achievements"
      ],
      "fetched_at": {
        "schema": "2026-10-07T01:20:35Z",
        "player": "2026-10-07T01:20:36Z"
      },
      "error_id": null
    },
    "total": 47,
    "unlocked": 12,
    "completion_ratio": 0.2553,
    "items": null
  }
}
```

## 8.1 `total`

```text
integer | null
```

游戏成就总数。

特殊语义：

```text
-1 = 已确认该游戏不存在成就系统
```

## 8.2 `unlocked`

```text
integer | null
```

当前用户已解锁成就数量。

当确认没有成就系统时：

```text
unlocked = -1
```

## 8.3 `completion_ratio`

```text
number | null
```

完整成就数据可用时：

```text
completion_ratio = unlocked / total
```

如果游戏没有成就系统，或无法可靠计算：

```text
completion_ratio = null
```

## 8.4 `items`

```text
Achievement[] | null
```

`null` 表示当前结果没有逐项成就明细。

当完整明细存在时：

```json
[
  {
    "apiname": "ACH_COMPLETE_GAME",
    "display_name": "Complete the Game",
    "description": "Finish the game.",
    "unlocked": true,
    "unlock_time": 1791330000
  }
]
```

单项结构：

```text
Achievement
├── apiname
├── display_name
├── description
├── unlocked
└── unlock_time
```

字段：

```text
apiname: string
display_name: string | null
description: string | null
unlocked: boolean | null
unlock_time: integer | null
```

### 无成就系统

推荐：

```json
{
  "meta": {
    "state": "not_applicable"
  },
  "total": -1,
  "unlocked": -1,
  "completion_ratio": null,
  "items": null
}
```

### 关于完整明细的调用

是否主动取得完整 `items` 属于 Feature / CLI 执行逻辑，不属于基础数据契约。

当前已记录的实现方向是：

- 日常查询可以只取得汇总。
- `games` / `library` 等查询功能可以通过后续定义的显式参数开启完整 Achievements 明细。
- 具体参数名称、CLI 写法与调度方式在 Feature / CLI 契约中定义。

---

# 9. Price

```text
Price
├── meta: Meta
├── type
├── currency
├── initial
└── final
```

示例：

```json
{
  "price": {
    "meta": {
      "state": "ok",
      "source": "get_app_details",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "type": "paid",
    "currency": "CNY",
    "initial": 16800,
    "final": 4200
  }
}
```

## 9.1 `type`

```text
"paid" | "free" | null
```

### 永久免费 / F2P

```json
{
  "type": "free",
  "currency": null,
  "initial": null,
  "final": null
}
```

### 付费游戏当前 100% 折扣

仍然属于：

```json
{
  "type": "paid",
  "currency": "CNY",
  "initial": 6800,
  "final": 0
}
```

因此：

```text
final = 0
```

不能单独用于判断游戏是否为免费产品。

## 9.2 `currency`

```text
string | null
```

例如：

```text
CNY
USD
JPY
```

## 9.3 `initial`

```text
integer | null
```

原始价格，按 Steam 返回的最小货币单位保存。

例如：

```text
16800 CNY → ¥168.00
```

基础层不保存格式化价格字符串。

## 9.4 `final`

```text
integer | null
```

当前价格，同样使用最小货币单位。

### 不保存 `discount_percent`

折扣率属于派生数据：

```text
(initial - final) / initial
```

因此不进入基础数据契约。

---

# 10. Bundles

```text
Bundles
├── meta: Meta
└── items: Bundle[] | null
```

示例：

```json
{
  "bundles": {
    "meta": {
      "state": "ok",
      "source": "store_bundle_source",
      "fetched_at": "2026-10-07T01:20:35Z",
      "error_id": null
    },
    "items": [
      {
        "bundle_id": 12345,
        "name": "Complete Collection",
        "price": {
          "type": "paid",
          "currency": "CNY",
          "initial": 26800,
          "final": 6700
        },
        "included_apps": {
          "292030": "The Witcher 3: Wild Hunt",
          "378648": "Blood and Wine",
          "378649": "Hearts of Stone"
        }
      }
    ]
  }
}
```

## 10.1 Bundle

```text
Bundle
├── bundle_id
├── name
├── price
└── included_apps
```

### `bundle_id`

```text
integer
```

Steam Bundle 的稳定 ID。

### `name`

```text
string | null
```

Bundle 名称。

### `price`

复用 `Price` 的业务字段：

```text
type
currency
initial
final
```

Bundle 内部的 `price` 不重复嵌套独立 `Meta`；其来源元信息继承自外层 `Bundles.meta`。

### `included_apps`

采用字典结构：

```json
{
  "292030": "The Witcher 3: Wild Hunt",
  "378648": "Blood and Wine"
}
```

规则：

- key 为 AppID 的字符串形式。
- value 为当前可取得的名称。
- 如果 AppID 已知但名称未知：

```json
{
  "123456": null
}
```

禁止因为名称缺失而删除 AppID。

---

# 11. 当前基础层完整结构

```text
Meta
├── state
├── source
├── fetched_at
└── error_id

GameIdentity
├── meta
├── appid
├── name
└── app_type

Market
├── meta
├── region
├── released
└── availability

Ownership
├── meta
├── owned_by_self
├── owned_by_other_family_members
├── available_via_family
└── owners
    └── <steamid>
        └── persona_name

Wishlist
├── meta
├── present
├── priority
└── date_added

Playtime
├── meta
├── total
├── last_2weeks
├── last_played_at
├── unit
└── platform
    ├── windows
    ├── mac
    ├── linux
    └── deck

Achievements
├── meta
├── total
├── unlocked
├── completion_ratio
└── items
    └── Achievement[]
        ├── apiname
        ├── display_name
        ├── description
        ├── unlocked
        └── unlock_time

Price
├── meta
├── type
├── currency
├── initial
└── final

Bundles
├── meta
└── items
    └── Bundle[]
        ├── bundle_id
        ├── name
        ├── price
        │   ├── type
        │   ├── currency
        │   ├── initial
        │   └── final
        └── included_apps
            └── <appid>: name | null
```

---

# 12. 已明确删除 / 不进入基础契约的字段

当前基础契约明确不包含：

```text
store_url
store 原始详情对象
stats
discount_percent
initial_formatted
final_formatted
shared_exclusion_reason
```

原因：

### `store_url`

可由 AppID 机械生成，不需要持久化。

### `store`

原始商店对象过大，当前只保留真正有业务价值的 `Market`、`Price`、`Bundles`。

### `stats`

不同游戏定义差异过大，当前三个核心功能没有明确需求。

未来如果扩展到大量用户行为、玩家统计或评阅分析，再通过新的 schema 版本加入。

### `discount_percent`

可由 `initial` 与 `final` 计算。

### formatted price

属于显示层，而不是基础事实。

### `shared_exclusion_reason`

当前没有明确业务用途，因此不进入基础数据层。

---

# 13. 不属于本数据契约的实现逻辑

以下内容已经讨论并记录，但不属于本文基础数据契约。

## 13.1 Games 查询输入

当前方向：

```text
"Game A","Game B"
"Game C"

<空行>
```

规则：

- 只接受被 ASCII 英文双引号 `"` 包围的游戏名称。
- 同一行使用 ASCII 英文逗号 `,` 分隔多个名称。
- 普通换行继续收集。
- 收集阶段空行表示结束输入并开始查询。
- 不直接接受 AppID 或 Steam URL 作为用户查询内容。

输入语法错误由 Shell 当场处理，不写入业务 JSON。

例如：

```text
"Hades",Noita,"Outer Wilds"
```

应明确指出：

```text
Noita
QUERY_NAME_NOT_QUOTED
```

并提示：

```text
请重新输入该项（直接回车表示放弃该项）：
```

纠错阶段的空行只表示放弃当前错误项，不表示结束整个程序。

## 13.2 Achievements 明细开关

完整 `Achievements.items` 是否查询属于 Feature / CLI 执行逻辑。

当前方向：

- 默认不主动抓取完整成就明细。
- `games` / `library` 后续可通过显式参数开启。
- 该参数的最终名称、位置与调用方式在 Feature Contract / CLI Contract 中确定。

---

# 14. 下一阶段

基础数据契约确认后，下一层应分别定义：

```text
Wishlist Feature Contract
Library Feature Contract
Games Feature Contract
```

Feature Contract 负责确定：

1. 每个功能由哪些基础模块组合成最终 Record。
2. 哪些数据块为核心数据。
3. 哪些数据块默认查询。
4. 哪些数据块按参数启用。
5. 哪些数据块失败会导致 Feature `partial` 或 `failed`。
6. 最终 Feature 输出 JSON 的结构与 summary / coverage 规则。

基础数据契约本身不承担这些职责。
