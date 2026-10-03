# Steam 本地数据工具

一个 Python 3.11+ / WSL 的只读命令行 demo：导出愿望单、本人游戏库与家庭候选，或查询单款游戏。输出业务 JSON 和结构化 JSONL 日志，不启动服务，不需要域名、Docker 或数据库。

## 安装与配置

使用 Conda 管理 Python 和项目依赖，在本项目目录运行（本次验证 Python 3.12.14 / Conda 26.1.1）：

```bash
conda env create --prefix ./.conda --file environment.yml
conda activate ./.conda
# 需要运行离线测试时：
python -m pip install -r requirements-dev.txt
```

先安装 WSL/Linux 版 Miniconda 或 Miniforge。`environment.yml` 固定 Python 3.12，运行依赖版本保留在 `requirements.txt`。环境位于项目 `.conda`；更新环境可执行 `conda env update --prefix ./.conda --file environment.yml`。入口直接执行 Conda 环境中的 Python，不必每次激活，也不自动安装或升级。

`./start` 和 `./stop` 按以下顺序选择环境：`STEAM_CONDA_PREFIX` 显式指定的路径 → 项目 `.conda` → 已激活环境的 `CONDA_PREFIX`。使用其他 Conda 环境时，可以设置 `export STEAM_CONDA_PREFIX=/绝对路径/到/环境`；启动前检查 Conda 元数据、Python 版本及依赖。

仅当 `.env` 尚不存在时，从 `.env.example` 复制一份，在本地编辑并限制访问权限。**不要提交 `.env`，也不要把 Key、token、Cookie 贴到聊天或测试报告中。**

```bash
# 不覆盖已有配置
if [ ! -e .env ]; then cp .env.example .env; chmod 600 .env; fi
```

| 配置 | 用途 |
|---|---|
| `STEAM_ID` | 本人公开个人账号的数字 SteamID64；保存为字符串 |
| `STEAM_API_KEY` | 本人普通 Web API Key；配置后可查询可见的库、时长、成就和统计 |
| `STEAM_FAMILY_ACCESS_TOKEN` | 本人本地提供的有效会话 access token；仅家庭只读接口使用 |
| `STEAM_LANGUAGE` / `STEAM_STORE_COUNTRY` | 默认 `schinese` / `CN`；查询上下文，不代表识别出的账户地区 |
| `OUTPUT_DIR` | 默认 `Outputs`；相对项目根目录解析 |
| `LOG_LEVEL` | 默认 `INFO`；DEBUG 同样脱敏 |

环境变量优先于 `.env`，再使用默认值。`.env` 由 Python 读取，不执行 shell 内容。Key/token 不接受 CLI 参数。无需凭据即可搜索商店和读取单款公开详情；未配置 SteamID 时账号部分为 `not_requested`，拥有关系仍为 `null`。

## 运行

```bash
./start                         # 交互菜单，选择任务后继续菜单
./start wishlist                # 必须配置 STEAM_ID；不强制 Key
./start library                 # 本人库需要 Key；无家庭 token 时保留自有库并报告缺口
./start game "巫师3"
./start game --appid 292030
./start game "https://store.steampowered.com/app/292030/"
./start doctor                  # stdout 输出诊断 JSON，日志走 stderr
./start --help
./stop
```

从其他目录使用 start/stop 的绝对路径也可运行。无参数且 stdin 非交互时显示用法并退出。名称仅在返回候选中有唯一精确匹配时自动选择；模糊或同名结果写出 `needs_selection` JSON。使用候选 AppID 再执行即可，非交互命令不会等待输入。`sub` / `bundle` URL 明确不支持。

单游戏查询只抓目标游戏的详情，为拥有关系读取相关清单，不为全库补详情和成就。个人成就/统计的逐游戏补齐在 `library` 执行。未实现可选 `all`、全应用目录和跨运行缓存。

## 输出与状态

每次实际任务分配独立 `run_id`，在输出目录产生：

```text
20261002T160000000000Z_library_012345abcdef.json
20261002T160000000000Z_library_012345abcdef.runtime.jsonl
```

业务 JSON 使用 `schema_version=1.0.0`，包含 `meta`、`status`、`data.items/resolution/summary`、`id_map`、`name_index`、`coverage` 和最终仍影响结果的 `errors`。日志逐行独立解析，记录阶段、任务、请求、重试、冷却、缓存命中、进度和运行摘要。历史重试失败只留日志；恢复成功不追加到业务错误清单。

| 状态 | 退出码 | 含义 |
|---|---:|---|
| `ok` | 0 | 声明范围完成；公开模式不声称账号数据可用 |
| `partial` | 2 | 保留主要结果，仍有来源缺失或完整性不足 |
| `needs_selection` | 2 | 名称需要通过候选 AppID 确定 |
| `failed` | 1 | 关键清单失败、配置/程序错误、输出或日志失败 |
| `cancelled` | 130 | 用户停止，尽力保存已取得数据 |

核心语义：

- 本人持有、家人持有、本人可共享是三个独立三值字段。`null` 表示未知；完整、范围明确的证据才能支持 `false`。
- 借玩记录不会变成本人持有；所有个人时长、成就和统计都属于配置中的本人 SteamID。
- 时长统一分钟，缺失两周时长不补零；平台时长不相加替代总时长。家庭原始 `rt_playtime` 因主体/单位未实测而不导出。
- 成就依照 `apiname` 关联；定义和玩家集合完整且对应才计算完成率。无成就、未请求、读取失败分别表达。
- 愿望单缺详情、下架或地区不可读仍保留 AppID。只有显式清单加数量一致才认定该响应范围完整。上游省略 `items` 时保守标记不可用，不猜空清单。
- 价格缺失不等于免费。保留接口提供的币种、原始金额和格式化价格。
- `id_map` 覆盖导出记录、名称候选及详情返回的 DLC AppID；反向名称索引始终是数组。

输出先写同目录临时文件并 fsync，再原子发布且拒绝覆盖旧运行。如果发布后日志失败，只允许原子更正相同 run_id 的本轮文件为失败状态。输出目录不可写、磁盘满或强杀时不能保证产生 JSON。合成示例见 [task/examples](task/examples)。

## 家庭能力与真实验证边界

家庭接口标记为 `experimental`。当前实现会核对 token 中的目标用户和有效期声明，再要求 Steam 接受认证请求；有家庭时还要求返回成员包含本人。**本地读取 JWT 声明不等于本地验证签名**；不透明或无法确认主体的 token 会拒绝绑定，不尝试自动登录、申请 token 或手机确认。

先取得真实家庭组 ID，再查询 `include_own=true`、`include_excluded=true`、`include_non_games=true` 的候选；不依赖 family_groupid=0。最多请求 10000 个条目，达到上限标记可能截断；由于没有实测的完整性保证，家庭候选完整性始终为 false。`include_family_licenses` 只是已借玩补充，不能替代完整家庭清单。

原始协议中的 `exclude_reason=0` 解释为无排除，已知排除值解释为不可共享；未定义值保留原值并保持资格未知。资格不代表当前有空闲副本。

已真实验证匿名商店详情和搜索、本人资料、本人库与近期记录清单、家庭组与共享候选清单。**私人愿望单、逐游戏成就/统计、家庭四类样本及完整性仍未完成真实验收**；自动测试使用合成响应。`include_family_licenses` 补充清单在本次实测中未能确认完整性，家庭候选也保留 `complete=false`，不宣称完整家庭库。

## 请求控制与停止

| 参数 | 默认 |
|---|---:|
| `STEAM_MAX_CONCURRENCY` | 4 个真实 HTTP 在途请求 |
| `STEAM_WEBAPI_RPS` | 2 请求/秒 |
| `STEAM_STORE_RPS` | 0.5 请求/秒 |
| `STEAM_FAMILY_RPS` | 0.5 请求/秒，额外服从 Web API 域名限制 |
| 连接/读取/写入/连接池超时 | 10 / 20 / 10 / 10 秒 |
| `STEAM_MAX_ATTEMPTS` | 3，包含首次请求 |
| `STEAM_REQUEST_DEADLINE_SECONDS` | 60 秒，从首次真正发送开始 |
| 本地退避基数/上限 | 1 / 30 秒 |
| `STEAM_STOP_GRACE_SECONDS` | 5 秒 |
| `STEAM_PROGRESS_INTERVAL_SECONDS` | 5 秒 |

完整变量名见 `.env.example`。这些值是保守工程默认值，不是 Valve 公布的限额。首次发送前的排队不消耗逻辑请求预算；后续排队、重试和退避计入预算。429 对对应域名实施共享冷却，兼容秒数和日期 Retry-After；服务端等待不被本地上限缩短。等待过长会结束本次请求但保留冷却。认证、证书及结构错误不盲目重试，TLS 始终校验，不自动跟随重定向。

Python 在整个会话持有 `.runtime/instance.lock` 的文件锁。`stop` 检查锁、PID、启动标识、boot ID、UID、绝对项目路径及命令行，使用 Linux pidfd 避免 PID 重用竞态；Conda Python 未提供 pidfd 包装时调用系统 libc 的同名接口。不支持 pidfd 或身份无法确认时拒绝发送信号。不会按进程名批量终止 Python。

SIGINT/SIGTERM 或 `stop` 会停止新派发、唤醒限速与重试等待，在宽限内收集结果后取消剩余任务，保存部分 JSON、关闭连接并释放锁。重复 stop 无害，默认不强杀。stop 最多等待 15 秒确认收尾；若自行设置超过此值的宽限，stop 可能先报告未确认，但不会强杀。

## 错误码与诊断

错误对象包含 code、来源、scope、API/AppID/目标主体、错误 ID、HTTP/上游状态和安全消息。不会把 403 推测成某种具体隐私设置，也不把失败转成空清单。

| 错误码 | 含义与处理 |
|---|---|
| `CONFIG_INVALID` / `TOOL_NOT_FOUND` | 配置、参数或调用问题；修正后重试命令 |
| `AUTH_REQUIRED` / `AUTH_EXPIRED` | 本地缺凭据或明确过期；更新本地配置 |
| `ACCESS_DENIED` | 上游拒绝或身份不符；不自动重试 |
| `NETWORK_TIMEOUT` / `NETWORK_ERROR` | 有限重试；证书错误不关闭 TLS |
| `RATE_LIMITED` / `UPSTREAM_UNAVAILABLE` | 共享冷却或有限退避 |
| `REQUEST_DEADLINE_EXCEEDED` | 逻辑请求预算耗尽，不提前违反冷却 |
| `RESPONSE_INVALID` / `DATA_UNAVAILABLE` | 结构或数据缺失，保留未知状态 |
| `OUTPUT_WRITE_FAILED` / `LOG_WRITE_FAILED` | 保存/监督失败；停止派发并尽力保留部分结果 |
| `INTERNAL_ERROR` | 未预期程序问题；记录脱敏栈位置并终止 |

`doctor` 检查配置是否存在、凭据是否配置、输出可写性、显式工具注册表，以及一个公开商店探测。有 Key/SteamID 时加用户资料探测，有 token/SteamID 时加家庭组探测，不自动遍历所有工具。配置齐全仅表示可尝试，不保证账号权限或完整性。

## 测试与开发

```bash
conda activate ./.conda
python -m pytest -q
python -m compileall -q main.py config.py error_handler.py Ports scripts
python -m pip check
bash -n start stop
```

默认测试不联网，不读取真实 `.env`，不需要真实凭据。HTTP 使用 httpx MockTransport；生命周期测试在临时项目启动实际子进程，通过仅测试使用的 sitecustomize 注入模拟 HTTP。测试不会向任意非测试进程发送信号。

`Ports/` 每个 API 一个文件，`registry.py` 显式登记，只允许审核过的只读工具。`request_executor.py` 执行请求和恢复决定；根目录 `error_handler.py` 只分类和决策。`scripts/` 仅三个业务模块、持久化和 runtime 五个职责文件。增加 API 时实现适配器、登记工具并补契约测试，不新增另一套 HTTP/重试/日志机制。

详细命令、阶段提交及待联调项见 [实现记录](task/IMPLEMENTATION.md)，逐项测试映射见 [验收矩阵](task/ACCEPTANCE.md)。
