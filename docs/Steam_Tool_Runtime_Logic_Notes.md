# Steam Tool 运行逻辑补充说明

**文档状态：Draft / 当前讨论冻结版**  
**用途：记录当前不属于数据契约、需要交给 CLI / Feature 执行逻辑处理的两个问题。**

---

# 1. Games 查询输入与错误纠正逻辑

这部分属于：

```text
CLI
Input Parser
Resolver
```

不属于基础数据契约，也不进入最终 Feature Result Schema。

---

## 1.1 输入格式

Games 查询只接受被 ASCII 英文双引号 `"` 包围的游戏名称。

示例：

```text
"Hades","Noita"
"The Witcher 3: Wild Hunt"
"Hello, World"

<空行>
```

规则：

1. 一个游戏名称对应一对 ASCII 英文双引号。
2. 同一行多个游戏使用 ASCII 英文逗号 `,` 分隔。
3. 普通回车表示提交当前行并继续输入下一行。
4. 正常收集阶段输入空行，表示结束整批输入并开始查询。
5. 不接受 AppID 作为用户输入。
6. 不接受 Steam 商店 URL 作为用户输入。
7. 中文引号、弯引号等不视为合法边界符。

---

## 1.2 解析方式

解析器不能直接使用：

```python
line.split(",")
```

因为游戏名称本身可能包含逗号。

例如：

```text
"Hades","Hello, World","Noita"
```

必须解析为：

```text
Hades
Hello, World
Noita
```

因此需要使用支持双引号边界的解析方式，例如 CSV-style parser 或等价实现。

如果游戏名称本身包含 ASCII 双引号，应使用明确的转义规则。建议沿用 CSV 双双引号规则：

```text
"Game ""Special"" Edition"
```

解析为：

```text
Game "Special" Edition
```

---

## 1.3 输入错误按项处理

输入错误不应导致整批输入全部失败。

例如：

```text
"Hades",Noita,"Outer Wilds"
```

第二项：

```text
Noita
```

不符合：

```text
"Game Name"
```

格式。

Shell 应立即指出：

```text
第 2 项输入错误：
Noita

错误类型：
QUERY_NAME_NOT_QUOTED

说明：
游戏名称必须使用 ASCII 英文双引号 "..." 包围。
```

然后进入当前错误项的纠错状态。

---

## 1.4 纠错提示

建议使用：

```text
请重新输入第 2 项（直接回车表示放弃该项）：
>
```

用户有两种选择：

### 重新输入

```text
> "Noita"
```

若合法：

```text
替换原错误项
→ 加入最终查询队列
→ 继续后续输入 / 查询
```

如果再次非法，则继续指出当前错误并要求重新输入。

### 直接回车

```text
>
```

表示：

```text
放弃当前错误项
```

该项不进入最终查询队列。

---

## 1.5 两种空行语义

代码必须区分两个交互状态：

```text
COLLECTING_INPUT
```

和：

```text
CORRECTING_ITEM
```

### COLLECTING_INPUT

正常收集输入时：

```text
空行
→ 结束整个输入阶段
→ 开始执行查询
```

### CORRECTING_ITEM

当前正在修正错误项时：

```text
空行
→ 仅放弃当前错误项
→ 不结束整个程序
```

实现时不能把这两种空行处理为同一个行为。

---

## 1.6 输入错误与业务错误分离

Shell 输入语法错误：

```text
QUERY_NAME_NOT_QUOTED
QUERY_INVALID_QUOTE
QUERY_UNCLOSED_QUOTE
QUERY_EMPTY_NAME
QUERY_UNEXPECTED_CHAR
QUERY_INVALID_ESCAPE
```

属于：

```text
CLI / Parser 错误
```

不进入最终业务 JSON：

```text
errors[]
```

原因：

> 被用户修正或放弃的非法输入从未进入正式业务查询阶段。

只有已经进入 Feature 执行阶段后产生的 API、网络、解析、权限或数据错误，才进入最终 Result 的 `errors[]`。

---

# 2. Achievements 明细按参数开启

这部分属于：

```text
Feature Runner
CLI 参数
查询调度逻辑
```

不属于基础数据契约。

---

## 2.1 数据契约保持不变

Achievements 基础结构始终为：

```text
Achievements
├── total
├── unlocked
├── completion_ratio
└── items
```

其中：

```text
items: Achievement[] | null
```

---

## 2.2 默认行为

正常执行：

```text
games
```

或：

```text
library
```

时，默认只获取 / 保留：

```text
total
unlocked
completion_ratio
```

并设置：

```json
"items": null
```

其语义是：

> 本次结果没有请求逐项成就明细。

它不代表：

> 该游戏没有成就系统。

---

## 2.3 完整明细模式

Games 和 Library 功能允许通过显式参数开启完整 Achievements 明细。

未来 CLI 可以采用类似：

```bash
games --achievements
```

或：

```bash
library --achievements
```

具体参数名称和 CLI 语法可以在实现阶段最终确定。

开启后：

```text
Achievements.items
```

填充完整成就列表：

```text
Achievement[]
├── apiname
├── display_name
├── description
├── unlocked
└── unlock_time
```

---

## 2.4 执行逻辑

推荐逻辑：

```text
Feature 启动
↓
执行正常基础查询
↓
取得 Achievements 汇总
↓
检查 achievements detail 参数
├── 未开启
│   └── items = null
│
└── 已开启
    ↓
    调用逐项成就相关接口
    ↓
    填充 items[]
```

---

## 2.5 无成就系统与未请求明细必须区分

### 有成就系统，但未请求 items

```json
{
  "total": 47,
  "unlocked": 12,
  "completion_ratio": 0.2553,
  "items": null
}
```

### 已确认无成就系统

```json
{
  "total": -1,
  "unlocked": -1,
  "completion_ratio": null,
  "items": null
}
```

这两个状态不能混淆。

---

## 2.6 设计目的

默认关闭完整 `items` 的原因：

1. `library` 可能包含数百个 App。
2. 完整逐项成就会显著增加 API 请求数量。
3. JSON 体积会快速膨胀。
4. 日常库存分析通常只需要总数、已解锁数量和完成率。
5. 确实需要成就细节时，再显式开启。

因此：

> Achievements 完整结构始终保留，但默认只填汇总数据；逐项明细由执行参数控制。

---

# 3. 职责边界总结

```text
问题 1：
Games 名称输入、双引号解析、错误定位、重输、放弃
→ CLI + Input Parser + Resolver
```

```text
问题 2：
Achievements.items 是否完整查询
→ Feature Runner + CLI 参数 + 查询调度
```

两者共同遵守：

```text
不修改 Base Data Contract
不改变 Feature Result Schema
```

只改变：

```text
运行过程
查询范围
最终字段是否被填充
```

---

# 4. 后续实现要求

后续交给 Codex 实现时，需要至少验证：

## Games 输入

- 支持多行持续输入。
- 支持一行多个带双引号名称。
- 支持游戏名内部逗号。
- 正确定位错误项。
- 错误项可重复重输。
- 纠错阶段空行只跳过当前项。
- 正常收集阶段空行结束整批输入。
- Shell 输入错误不污染最终业务 JSON。

## Achievements

- 默认模式不抓完整 `items`。
- 明细参数开启后正确填充 `items[]`。
- 无成就系统与 `items = null` 的“未请求”语义严格区分。
- 明细查询失败时按现有 Meta / Error 机制降级，不破坏整个 Record。
