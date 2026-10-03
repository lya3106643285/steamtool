# steamtool

一个 Python 3.11+ / WSL 的只读命令行工具包：导出愿望单、本人游戏库与家庭候选，或查询单款游戏。输出业务 JSON 和结构化 JSONL 日志，不启动服务，不需要域名、Docker 或数据库。

## 已实现功能与对应命令

当前版本为 **1.1.0**。主命令是 `steamtool`，`teamtool` 和 `Steamtool` 是相同功能的别名；下面的示例都可以替换为这两个名字。

| 已实现功能 | 对应命令 | 使用条件与结果 |
| --- | --- | --- |
| 交互菜单 | `steamtool` | 在交互终端选择愿望单、游戏库、游戏查询或诊断；输入 `0` 退出 |
| 愿望单导出 | `steamtool wishlist` | 需要 `STEAM_ID`；读取可访问的愿望单、优先级、添加时间，补充商店详情及可取得的持有关系 |
| 本人库与游玩记录 | `steamtool library` | 本人库需要 `STEAM_ID` 和 `STEAM_API_KEY`；合并本人库、近期记录和借玩补充，导出时长 |
| 家庭共享候选与资格 | `steamtool library` | 额外需要 `STEAM_FAMILY_ACCESS_TOKEN`；区分本人持有、家人持有与本人可共享，家庭能力为实验性 |
| 逐游戏成就和统计 | `steamtool library` | 需要 `STEAM_ID` 和 `STEAM_API_KEY`；读取可取得的成就定义、本人解锁记录和统计，缺失信息保留未知 |
| 按游戏名称搜索、查询 | `steamtool game "Portal 2"` | 查询公开商店；存在歧义时导出候选，随后指定 AppID |
| 按 AppID 查询 | `steamtool game --appid 620` | 查询公开详情、价格、平台、发行信息与 DLC ID；配置账号后补充相关持有、时长和愿望单关系 |
| 按商店链接查询 | `steamtool game "https://store.steampowered.com/app/620/"` | 接受官方 `/app/` 链接；不支持 `/sub/`、`/bundle/` |
| 配置与网络诊断 | `steamtool doctor` | 检查配置、输出目录和公开接口；凭据齐全时增加本人资料及家庭组探测 |
| 定位配置文件 | `steamtool config path` | 仅显示当前 `.env` 路径，不显示凭据 |
| 创建空白配置 | `steamtool config init` | 创建权限为 `600` 的配置模板，已有配置时拒绝覆盖 |
| 导入已有配置 | `steamtool config import /路径/到/.env` | 私密复制已有 `.env`，保留源文件，不覆盖目标 |
| 停止运行任务 | `steamtool stop` 或当前终端 `Ctrl+C` | 尽力保存已完成部分；`stop` 针对使用同一配置目录的实例 |
| 查看帮助和版本 | `steamtool --help` / `steamtool --version` | 无需凭据，也不会发起 Steam 请求 |

每次查询或导出都会生成业务 JSON 和运行日志，支持并发、限速、有限重试、脱敏和取消后的部分结果保存。成就、统计和家庭功能已经实现，但真实账号验收范围仍以[家庭能力与真实验证边界](#家庭能力与真实验证边界)为准。当前没有独立的 `family`、`achievements`、`all` 子命令，也没有自动登录或获取 token 的功能。

## 快速上手

已安装并配置好 PATH 后，新开终端即可在任意目录运行：

```bash
steamtool --version
steamtool --help
steamtool config path              # 找到安装版正在使用的配置
steamtool doctor                   # 先检查配置及接口可用性
steamtool game --appid 292030      # 查询指定游戏
steamtool wishlist                # 导出愿望单
steamtool library                 # 导出游戏库与可取得的补充信息
```

尚未安装时，按下一节完成安装。尚未配置时，先初始化空白配置或导入已有 `.env`；已有配置无需重新初始化。安装版默认读取 `~/.steamtool/.env`，在项目目录修改原始 `.env` 不会同步改变已导入的副本，应编辑 `steamtool config path` 显示的文件。

普通查询命令完成后，终端会打印本次业务 JSON 的完整路径。默认结果在 `~/.steamtool/Outputs`；可以用文件编辑器打开对应 `.json`，并通过同名 `.runtime.jsonl` 查看运行记录。`doctor` 会额外将诊断 JSON 打印到终端。使用自定义 `STEAMTOOL_HOME` 或 `OUTPUT_DIR` 时，以实际打印的路径为准。

## 安装与配置

steamtool 是可安装的 Python CLI 包，发行包名称为 `steamtool-cli`，命令名称为 `steamtool`。使用 Conda 管理 Python 和依赖，在本项目目录首次安装：

```bash
conda env create --file environment.yml
conda activate steamtool
steamtool --version
```

已有本项目 Conda 环境时，无需重建：

```bash
conda activate steamtool
python -m pip install .
# 需要运行离线测试时：
python -m pip install -r requirements-dev.txt
```


若终端提示符仍显示 `(.venv)`，先退出旧虚拟环境，再切换到命名环境：

```bash
deactivate
conda activate steamtool
python --version
steamtool --version
```

此后提示符会显示 `(steamtool)`。已配置用户 PATH 时，日常运行 `steamtool` 无需激活；命名环境用于安装、更新和开发。环境迁移期间正在运行的导出继续使用原环境，待任务结束后再切换当前终端；也可在原任务终端按 `Ctrl+C` 保存部分结果后切换。

`environment.yml` 将环境命名为 `steamtool`，固定 Python 3.12 并安装本地包；运行依赖固定在 `requirements.txt`。激活安装了本包的 Conda 环境后，任何目录都可调用 `steamtool`。也可直接调用环境的 `bin/steamtool`。支持 Python 3.11+，当前验证环境为 Python 3.12.14 / Conda 26.1.1。

若希望打开终端即可调用，安装后将入口加入用户 PATH（在安装本包的 Conda 环境中执行一次）：

```bash
mkdir -p "$HOME/.local/bin"
ln -s "$CONDA_PREFIX/bin/steamtool" "$HOME/.local/bin/steamtool"
ln -s "$CONDA_PREFIX/bin/teamtool" "$HOME/.local/bin/teamtool"
export PATH="$HOME/.local/bin:$PATH"
```

将最后一行加入 `~/.bashrc` 后，新开 Bash 终端可直接调用，无需每次激活 Conda。已有同名命令时先检查路径，不覆盖其他工具。入口使用安装环境的绝对 Python 路径；需保留该 Conda 环境。`teamtool` 和 `Steamtool` 是同一工具的命令别名。

默认配置为 `~/.steamtool/.env`，结果为 `~/.steamtool/Outputs`，实例状态为 `~/.steamtool/.runtime`，不写入包安装目录。可以通过绝对路径环境变量 `STEAMTOOL_HOME` 指定另一个配置目录；同一配置目录只允许运行一个任务实例。

已有项目 `.env` 时，在项目目录执行以下命令迁移（只复制、不显示内容、不覆盖目标）：

```bash
steamtool config import .env
steamtool config path
```

首次配置且没有已有 `.env` 时，运行 `steamtool config init`，再编辑 `steamtool config path` 显示的文件。新建文件权限为 `600`，目标配置已存在时初始化和导入都会拒绝覆盖。环境变量优先于 `.env`。

**不要提交 `.env`，也不要把 Key、token、Cookie 贴到聊天或测试报告中。**

| 配置 | 用途 |
|---|---|
| `STEAM_ID` | 本人公开个人账号的数字 SteamID64；保存为字符串 |
| `STEAM_API_KEY` | 本人普通 Web API Key；配置后可查询可见的库、时长、成就和统计 |
| `STEAM_FAMILY_ACCESS_TOKEN` | 本人本地提供的有效会话 access token；仅家庭只读接口使用 |
| `STEAM_LANGUAGE` / `STEAM_STORE_COUNTRY` | 默认 `schinese` / `CN`；查询上下文，不代表识别出的账户地区 |
| `OUTPUT_DIR` | 默认 `Outputs`；相对配置目录解析 |
| `LOG_LEVEL` | 默认 `INFO`；DEBUG 同样脱敏 |

环境变量优先于 `.env`，再使用默认值。`.env` 由 Python 读取，不执行 shell 内容。Key/token 不接受 CLI 参数。无需凭据即可搜索商店和读取单款公开详情；未配置 SteamID 时账号部分为 `not_requested`，拥有关系仍为 `null`。

## 使用说明

### 常用命令

```bash
steamtool                         # 交互菜单，选择任务后继续菜单
steamtool wishlist                # 必须配置 STEAM_ID；不强制 Key
steamtool library                 # 本人库需要 Key；无家庭 token 时保留自有库并报告缺口
steamtool game "巫师3"
steamtool game --appid 292030
steamtool game "https://store.steampowered.com/app/292030/"
steamtool doctor                  # stdout 输出诊断 JSON，日志走 stderr
steamtool --help
steamtool stop
```

### 游戏查询

以下四种写法都受支持：

```bash
steamtool game "Portal 2"
steamtool game 620
steamtool game --appid 620
steamtool game "https://store.steampowered.com/app/620/"
```

名称包含空格时加引号。名称查询遇到同名、模糊匹配或未选中结果时，会生成 `status=needs_selection` 的 JSON；查看 `data.resolution.candidates` 中的 AppID，再执行 `game --appid`。单款查询不执行全库逐游戏补齐，也不补齐该游戏的个人成就和统计。

### 愿望单与游戏库导出

```bash
steamtool wishlist
steamtool library
```

愿望单以 AppID 保留条目，即使详情不可读或游戏下架，也不会静默丢弃。`library` 在相关清单的基础上逐游戏补充商店详情、成就和统计；游戏数量较多时耗时会增加，可在另一个终端执行 `steamtool stop`，或在当前终端按 `Ctrl+C`。

缺少家庭 token 时仍可读取有权限的本人库，家庭相关字段会标记缺口。账号隐私、权限或接口响应缺失时，以 JSON 中的 `coverage`、各数据块状态和 `errors` 判断可用范围；`partial` 退出码为 `2`，已有结果仍可使用。

### 配置维护、诊断与停止

```bash
steamtool config path                    # 显示当前配置路径
steamtool config init                    # 仅用于尚无配置的情况
steamtool config import /路径/到/.env    # 与 init 二选一，不覆盖已有配置
steamtool doctor                         # 少量只读网络诊断
steamtool stop                           # 停止同一配置目录的任务
steamtool game --help                    # 查看单款查询参数
steamtool config --help                  # 查看配置子命令
```

更新 Key 或家庭 token 时，编辑当前配置文件后重新执行任务。需要管理另一份配置时，指定绝对路径；开始任务和停止任务需使用相同目录：

```bash
STEAMTOOL_HOME=/绝对路径/到/另一份配置 steamtool doctor
STEAMTOOL_HOME=/绝对路径/到/另一份配置 steamtool stop
```

### 安装包维护与源码兼容入口

安装和卸载由 pip 管理；`steamtool stop` 仅停止任务。更新包可重新运行 `python -m pip install .`。卸载命令为 `python -m pip uninstall steamtool-cli`，用户配置、结果和日志会保留。若创建了用户 PATH 中的软链接，可删除这些已确认属于本工具的链接。当前提供本地源码和 wheel 安装，尚未发布到 PyPI。

需要分发 wheel 时，在项目目录构建，再在目标 Conda 环境安装生成的文件：

```bash
python -m pip wheel . --no-deps --wheel-dir dist
python -m pip install dist/steamtool_cli-1.1.0-py3-none-any.whl
```

源码中的 `./start` / `./stop` 仅保留为兼容入口，默认使用项目目录的 `.env` 和输出，选择 Conda 环境的顺序为 `STEAM_CONDA_PREFIX` → 命名环境 `steamtool` → 旧项目 `.conda` → 已激活的 `CONDA_PREFIX`。安装后的 `steamtool` 使用上文用户配置目录。若想直接沿用项目配置而不复制，可设置 `export STEAMTOOL_HOME=/绝对路径/到/steam-tools` 后调用 `steamtool`。

无参数且 stdin 非交互时显示用法并退出。名称仅在返回候选中有唯一精确匹配时自动选择；模糊或同名结果写出 `needs_selection` JSON。使用候选 AppID 再执行即可，非交互命令不会等待输入。`sub` / `bundle` URL 明确不支持。

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

Python 在整个会话持有 `.runtime/instance.lock` 的文件锁。`steamtool stop` 检查锁、PID、启动标识、boot ID、UID、配置目录、应用标记及实际 CLI 命令行，使用 Linux pidfd 避免 PID 重用竞态；Conda Python 未提供 pidfd 包装时调用系统 libc 的同名接口。不支持 pidfd 或身份无法确认时拒绝发送信号。不会按进程名批量终止 Python。

SIGINT/SIGTERM 或 `steamtool stop` 会停止新派发、唤醒限速与重试等待，在宽限内收集结果后取消剩余任务，保存部分 JSON、关闭连接并释放锁。重复 stop 无害，默认不强杀。stop 最多等待 15 秒确认收尾；若自行设置超过此值的宽限，stop 可能先报告未确认，但不会强杀。

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
conda activate steamtool
python -m pytest -q
python -m compileall -q main.py steamtool
python -m pip check
bash -n start stop
```

默认测试不联网，不读取真实 `.env`，不需要真实凭据。HTTP 使用 httpx MockTransport；生命周期测试在临时项目启动实际子进程，通过仅测试使用的 sitecustomize 注入模拟 HTTP。测试不会向任意非测试进程发送信号。安装测试在临时环境离线构建并安装 wheel，从源码目录外执行 CLI；不会切换项目的 Conda 管理方式。

`steamtool/Ports/` 每个 API 一个文件，`registry.py` 显式登记，只允许审核过的只读工具。`request_executor.py` 执行请求和恢复决定；`steamtool/error_handler.py` 只分类和决策。`steamtool/scripts/` 仅三个业务模块、持久化和 runtime 五个职责文件。增加 API 时实现适配器、登记工具并补契约测试，不新增另一套 HTTP/重试/日志机制。

详细命令、阶段提交及待联调项见 [实现记录](task/IMPLEMENTATION.md)，逐项测试映射见 [验收矩阵](task/ACCEPTANCE.md)。
