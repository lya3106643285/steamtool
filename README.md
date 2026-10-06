# steamtool

一个 Python 3.11+ / WSL 的只读命令行工具包：导出愿望单、本人游戏库与家庭候选，或按名称批量查询游戏。输出业务 JSON 和结构化 JSONL 日志，不启动服务，不需要域名、Docker 或数据库。

## 已实现功能与对应命令

当前版本为 **1.1.0**。主命令是 `steamtool`，`teamtool` 和 `Steamtool` 是相同功能的别名；下面的示例都可以替换为这两个名字。

三个核心功能 `games / library / wishlist` 的正式数据契约为 **2.0.0**，与 CLI 软件版本独立。字段和语义以 [docs/data_contract.md](docs/data_contract.md) 为准，模型定义在 `schema/base.py` 和 `schema/feature.py`。`game` 作为旧单游戏兼容入口、`doctor` 作为诊断入口继续使用 1.1.0 格式；历史输出保留。

| 已实现功能 | 对应命令 | 使用条件与结果 |
| --- | --- | --- |
| 交互菜单 | `steamtool` | 在交互终端选择愿望单、游戏库、游戏查询或诊断；输入 `0` 退出 |
| 愿望单导出 | `steamtool wishlist` | 需要 `STEAM_ID`；读取可访问的愿望单、优先级、添加时间，补充商店详情及可取得的持有关系 |
| 本人库与游玩记录 | `steamtool library` | 本人库需要 `STEAM_ID` 和 `STEAM_API_KEY`；合并本人库、近期记录和借玩补充，导出时长 |
| 家庭共享候选与资格 | `steamtool library` | 额外需要 `STEAM_FAMILY_ACCESS_TOKEN`；区分本人持有、家人持有与本人可共享，家庭能力为实验性 |
| 成就汇总与可选明细 | `steamtool library --achievements` | 默认读取成就总数证据；显式参数开启本人完整明细。现有来源无法独立确认默认解锁汇总时保留 null；新契约不含 Stats |
| 按名称批量查询 | `steamtool games '"Hades","Noita"'` | 保留 ASCII 双引号；无参数时多行收集，空行结束；查询完整 GameRecord，可加 --achievements |
| 按游戏名称搜索、查询 | `steamtool game "Portal 2"` | 查询公开商店；存在歧义时导出候选，随后指定 AppID |
| 按 AppID 查询 | `steamtool game --appid 620` | 查询公开详情、价格、平台、发行信息与 DLC ID；配置账号后补充相关持有、时长和愿望单关系 |
| 按商店链接查询 | `steamtool game "https://store.steampowered.com/app/620/"` | 接受官方 `/app/` 链接；不支持 `/sub/`、`/bundle/` |
| 配置与网络诊断 | `steamtool doctor` | 检查配置、输出目录和公开接口；凭据齐全时增加本人资料及家庭组探测 |
| 定位配置文件 | `steamtool config path` | 仅显示当前 `.env` 路径，不显示凭据 |
| 创建空白配置 | `steamtool config init` | 创建权限为 `600` 的配置模板，已有配置时拒绝覆盖 |
| 导入已有配置 | `steamtool config import /路径/到/.env` | 私密复制已有 `.env`，保留源文件，不覆盖目标 |
| 停止运行任务 | `steamtool stop` 或当前终端 `Ctrl+C` | 尽力保存已完成部分；`stop` 针对使用同一配置目录的实例 |
| 查看帮助和版本 | `steamtool --help` / `steamtool --version` | 无需凭据，也不会发起 Steam 请求 |

每次查询或导出都会生成业务 JSON 和运行日志，支持并发、限速、有限重试、脱敏和取消后的部分结果保存。家庭能力仍为实验性；下方历史联调记录基于此前输出格式，新的 2.0.0 契约本轮使用离线合成数据验收。当前没有独立的 `family`、`achievements`、`all` 子命令，也没有自动登录或获取 token 的功能。

## 快速上手

已安装并配置好 PATH 后，新开终端即可在任意目录运行：

```bash
steamtool --version
steamtool --help
steamtool config path              # 找到安装版正在使用的配置
steamtool doctor                   # 先检查配置及接口可用性
steamtool games '"Hades","Noita"' # 按名称批量查询
steamtool wishlist                # 导出愿望单
steamtool library                 # 导出游戏库与可取得的补充信息
```

尚未安装时，按下一节完成安装。尚未配置时，先初始化空白配置或导入已有 `.env`；已有配置无需重新初始化。安装版默认读取 `~/.steamtool/.env`，在项目目录修改原始 `.env` 不会同步改变已导入的副本，应编辑 `steamtool config path` 显示的文件。

普通查询命令完成后，终端会打印本次业务 JSON 的完整路径。默认结果在 `~/.steamtool/Outputs`；可以用文件编辑器打开对应 `.json`，并通过同名 `.runtime.jsonl` 查看运行记录。`doctor` 会额外将诊断 JSON 打印到终端。使用自定义 `STEAMTOOL_HOME` 或 `OUTPUT_DIR` 时，以实际打印的路径为准。

输出时间统一为北京时间 UTC+8，与主机时区设置无关。JSON 的运行、采集时间和 JSONL 日志时间使用带 `+08:00` 的 ISO 格式；文件名直接标注“北京时间”，例如 `20261005T000948386572_北京时间_library_efe38f26f590.json`。新契约时间位于 `run` 和各块的 `meta.fetched_at`；旧格式保留 `meta.output_timezone=北京时间`。Steam 返回的成就解锁、最后游玩等 Unix 时间戳保留原值。

本机已将安装版和源码版的本地 `.env` 配置为以下绝对输出路径；JSON 和 JSONL 都会写入该目录，调用命令时无需切换工作目录：

```dotenv
OUTPUT_DIR=/home/lya3106643285/projects/steam-tools/Outputs
```

这是本地配置覆盖，程序通用默认值不变；安装版的凭据与实例状态仍在 `~/.steamtool`。旧输出保留原位置，修改路径不搬动或覆盖历史结果。

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

本项目已移除旧 `.venv`，并在 `.vscode/settings.json` 关闭 VS Code 终端自动激活、将默认 Python 解释器指向 Conda 命名环境 `steamtool`。打开新终端不会再自动执行旧 `.venv/bin/activate`；已激活的终端可执行 `deactivate` 或重新打开终端，再按需执行 `conda activate steamtool`。

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

| 配置                                         | 用途                                                          |
| -------------------------------------------- | ------------------------------------------------------------- |
| `STEAM_ID`                                 | 本人公开个人账号的数字 SteamID64；保存为字符串                |
| `STEAM_API_KEY`                            | 本人普通 Web API Key；配置后可查询可见的库、时长、成就和统计  |
| `STEAM_FAMILY_ACCESS_TOKEN`                | 本人本地提供的有效会话 access token；仅家庭只读接口使用       |
| `STEAM_LANGUAGE` / `STEAM_STORE_COUNTRY` | 默认`schinese` / `CN`；查询上下文，不代表识别出的账户地区 |
| `OUTPUT_DIR`                               | 默认`Outputs`；相对配置目录解析                           |
| `STEAM_RANKING_LIMIT`                       | Library 排行榜默认 Top-N，默认 10，允许 0                  |
| `LOG_LEVEL`                                | 默认`INFO`；DEBUG 同样脱敏                                  |

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

核心功能支持批量 quoted name：

```bash
steamtool games '"Hades","Hello, World","Noita"'
steamtool games --achievements '"Hades"'
steamtool games
```

无参数时逐行输入；收集阶段空行结束整批输入。名称内部逗号保留，名称内部双引号使用两个双引号，例如 `"Game ""Special"" Edition"`。错误按项定位并重输；纠错阶段空行只放弃当前错误项，后续项目保留。输入错误只显示在终端，不进入业务 errors。名称必须解析到唯一精确 AppID；没有匹配或存在歧义时记录业务错误，不自动选择第一个候选，不制造占位 AppID。重复明确 AppID 合并为一个记录。

`games` 不接受直接 AppID 或商店 URL。旧 `game` 兼容入口保留以下写法，输出仍为旧格式：

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
steamtool library --achievements --ranking-limit 5
```

愿望单以 AppID 保留条目，即使详情不可读或游戏下架，也不会静默丢弃。`library` 只输出 identity、ownership、playtime、achievements，不再请求商店详情或 Stats；默认不请求玩家成就完整明细。`--achievements` 开启明细，`--ranking-limit` 覆盖本次 Top-N。可在另一个终端执行 `steamtool stop`，或在当前终端按 `Ctrl+C`。

当前来源缺口：默认成就总数可来自已有 schema，但没有已验证的独立解锁汇总来源，因此 unlocked/completion_ratio 为 null、Meta 为 partial；开启明细后可从现有玩家成就接口计算汇总。Bundle 来源、地区购买/获取资格和多拥有者昵称映射尚未定义，分别保留 unavailable 或 null，不增加 API 或爬虫。平台记录为零但支持信息未确认时保留 null，只有明确支持时才表达平台零游玩，只有明确不支持时才表达 -1。这些缺口会按必要块规则反映在 Record/Run 状态中。

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

主命令无参数且 stdin 非交互时显示用法并退出；显式 `games` 可以从管道或重定向文件收集多行 quoted name。旧 `game` 的模糊或同名结果使用 `needs_selection`；新 `games` 使用根级解析错误。`sub` / `bundle` URL 明确不支持。

Games 只补已解析目标的详情和成就，批内共享本人、家庭和愿望单清单以及现有运行缓存，不为全库补详情。未实现可选 `all`、全应用目录和跨运行缓存。

## 输出与状态

每次实际任务分配独立 `run_id`，在输出目录产生：

```text
20261007T102000000000_北京时间_library_012345abcdef.json
20261007T102000000000_北京时间_library_012345abcdef.runtime.jsonl
```

三个核心功能业务 JSON 使用 `schema_version=2.0.0`，字段顺序为 `schema_version / run / summary / coverage（仅 library、wishlist） / errors / items`。各块通过 `meta.state/source/fetched_at/error_id` 表达状态和来源。没有旧顶层 data、meta、status 或名称索引。详细字段、排行榜、三值和 sentinel 规则见 [正式数据契约](docs/data_contract.md)。

正式 Meta 状态为 `ok / partial / unavailable / not_applicable / not_requested`，不混用未请求与未取得。Run 状态为 `ok / partial / failed / cancelled`，Record 状态为 `ok / partial / failed`。没有成就系统使用 total=-1、unlocked=-1、items=null；未请求明细只使 items=null，不能因此把记录判为 partial。

Run 根据本次必要数据块、业务错误和集合完整性聚合；核心流程失败为 failed，取消优先为 cancelled。家庭实验性 complete=false 继续如实保留，不宣称集合完整。已形成的记录在补充查询失败或取消时保留。

Enrichment 复用已有队列、并发与 schema 驱动的调度。明细关闭时不发送 GetPlayerAchievements；只有明细开启且 schema 有有效定义时才请求完整列表。有效空定义跳过下游并使用无能力语义，schema 不可用时跳过依赖并保留错误，不根据名称或未知数字 app_type 猜能力。运行日志中的 API outcome 与重试决策保留现有语义；日志逐行独立解析，已恢复的重试错误只留日志。

同一运行按 API 和完整查询参数共享 future/result，包括最终失败结果；重试仍由统一执行器处理。无跨运行持久缓存。运行摘要位于 JSONL 日志，tasks 固定为一个 App enrichment 一个 task；operations、http_by_api、enrichment_plan 分别表达逻辑操作、真实 HTTP 和调度。未真正发出的下游请求不会增加 HTTP 数量。

| 状态                | 退出码 | 含义                                        |
| ------------------- | -----: | ------------------------------------------- |
| `ok`              |      0 | 声明范围完成；公开模式不声称账号数据可用    |
| `partial`         |      2 | 保留主要结果，仍有来源缺失或完整性不足      |
| `needs_selection` |      2 | 名称需要通过候选 AppID 确定                 |
| `failed`          |      1 | 关键清单失败、配置/程序错误、输出或日志失败 |
| `cancelled`       |    130 | 用户停止，尽力保存已取得数据                |

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

已真实验证匿名商店详情和搜索、本人资料、本人库与近期记录、家庭组与共享候选，并完成一轮逐游戏详情/成就/统计的全流程联网导出。部分补充字段不可用；私人愿望单及与 Steam 客户端对照的家庭全量验收仍未完成。自动测试使用合成响应，真实执行结果见下节。借玩补充和家庭候选继续保留 `complete=false`。

## 2026-10-04 游戏库联网实测

在 Conda 命名环境 `steamtool` 中实际执行 `steamtool library`，完整运行约 **14 分钟**，未中途停止。导出 **419 个不重复 AppID**，退出码 **2**、`status=partial`。所有接口本轮返回的清单条目均已保存；补充字段存在不可用数据，不能将本次结果描述为全部字段齐全的完整库。

| 清单来源 | 返回条目 | 本次核对结果 |
| --- | ---: | --- |
| 本人 GetOwnedGames | 125 | `game_count=125`，去重数一致，声明的可见响应范围内 `complete=true` |
| include_family_licenses 补充 | 137 | 比本人清单多 12 个 AppID；返回 `game_count` 仍为 125，不用它证明补充清单完整 |
| 近期记录 | 10 | 数量一致，全部进入导出 |
| 家庭候选，含本人 | 419 | 全部进入导出；包含排除共享、免费及非游戏条目，不等于 419 款可借玩的游戏 |

复查四类来源并集与导出 AppID 集合完全一致，遗漏 **0**、多余 **0**。家庭接口 `max_apps=1000` 与 `10000` 返回相同的 419 个 AppID，未观察到截断；实际响应仅提供 apps/owner_steamid，没有全量计数证据，仍保留 `complete=false`，尚需 Steam 客户端清单对照。

| 补充数据块 | 本次可用情况（共 419 条） |
| --- | --- |
| 商店详情 | 277 条成功，142 条当前查询上下文不可用 |
| 本人时长 | 137 条有来源记录，282 条没有可用记录；缺失不表示未玩或零时长 |
| 成就 | 213 条完整，13 条明确不适用，1 条部分可用，192 条不可用 |
| 个人统计 | 25 条成功，394 条未取得统计列表或请求失败 |

本轮记录 920 个 DATA_UNAVAILABLE 和 1 个 ACCESS_DENIED：包括 HTTP 400/403、缺少成就定义、商店不提供详情以及未提供统计列表；不据此推断具体隐私设置。共 1668 次 HTTP 请求，无重试和 429，按默认并发 4、Web API 2 请求/秒、商店 0.5 请求/秒执行。

接口证据中包含本人持有且玩过、本人不持有但有借玩时长、其他家人持有且可共享但没有本人时长记录、其他家人持有且被排除的样本；其中“没有时长记录”不能证明从未玩过。这是接口证据核对，尚未完成人工客户端对照。

业务 JSON、JSONL 日志和额外完整性核对报告保存在本机 `~/.steamtool/Outputs`，含账号与游戏清单的数据不提交 Git。其他账号或后续运行的数量可能不同；私人愿望单仍未在本轮测试。

## 2026-10-04 V1.1 补丁真实 benchmark

使用源码入口 `./start library`、同一账号及原请求配置完成 run `29c6dae6fff1`，schema_version=1.1.0。所有 419 个 AppID 及五项 ownership 字段与 V1.0 基线完全一致。原成功的时长 137、成就 213、stats 25、Store 277 个块全部保留；成功成就条目、stats 值、总时长/平台时长/最后游玩时间也与基线一致。Family 两个接口成功，家庭候选 419 条，无重复 enrichment 请求，无已跳过请求被实际发出的情况，Key/token 没有出现在 JSON 或 JSONL 中。

| 指标 | V1.0 基线 | V1.1 |
| --- | ---: | ---: |
| App 数 | 419 | 419 |
| Logical requests | 1668 | 1157 |
| HTTP attempts | 1668 | 1157 |
| App task success | 25 | 148 |
| App task not_applicable | 无独立统计 | 0 |
| App task data_unavailable | 无独立统计 | 270 |
| App task failed | 394 | 1 |
| Wall duration | 840.60 s | 840.67 s |
| Enrichment duration | 837.04 s | 837.08 s |

旧 failed 包含可选数据缺失，新旧成功/失败数不能按同一口径直接比较。一个 App 汇总四项 operation，包含成功操作时不会仅因部分能力不适用而把整个 App 标为 not_applicable；独立 operation 中 not_applicable 为 **140**（成就 13、stats 127）。真实请求中 schema 419、Store 419、成就 214、stats 100，另有 collection 5 次；相对基线少 **511 次（30.64%）**。schema 不可用的 192 个 App 各跳过两个下游，能力保持 unknown。唯一真正失败为玩家成就 HTTP 403 ACCESS_DENIED，和基线为同一个请求，未吞掉错误。

耗时没有下降：419 次 Store 请求在原 0.5 RPS 下发送间隔约需 836 秒，仍占据关键路径。全局并发仍为 4，离线并发和流水线测试通过；本轮没有通过串行或调高速率改变测量条件。顶层仍为 partial、退出 2，原因是既有 279 条 available_via_family 为 null 的关键 ownership 不确定性；可选 enrichment 不再单独影响主状态。

Portal 2、Left 4 Dead 的成就/stats/Store 均实际成功；Cities: Skylines 继续为本人不持有、家人持有且可共享；Source SDK Base 2006 的补充为 data_unavailable，不再产生 failed 风暴；原 13 个明确无成就的 App 全部保留该语义且没有成就请求。客户端全量对照、其他账号/地区/权限、实时网络重试仍未实测；长期缓存和复杂类型映射留待后续版本。

本轮 111 项离线测试通过，包含单元、MockTransport、子进程及 wheel 测试。真实 JSON、日志和审计汇总在项目 Outputs；本轮仅更新源码与文档，没有重装命名环境中已安装的 CLI。要让安装版 `steamtool` 使用补丁，需按上文从当前源码重新构建并安装 wheel。

## 2026-10-05 安装版重装与输出路径验证

从当前源码构建 1.1.0 wheel，以 `--force-reinstall --no-deps --no-index` 重装到 Conda 命名环境 `steamtool`，保留现有依赖、凭据与历史结果。三个命令入口可用；安装版 27 个 Python 文件与源码一致。测试进程实际导入重装后的包，完整离线测试 **111 passed in 25.16s**，pip check 无依赖冲突。

仅将安装版 `~/.steamtool/.env` 和源码版项目 `.env` 的 OUTPUT_DIR 改为 `/home/lya3106643285/projects/steam-tools/Outputs`，其他配置和 0600 权限保留；业务代码及通用路径默认值未修改。

从 `/tmp` 调用安装版命令进行真实联网验证。doctor run `fc9e12d6c37e` 为 ok、退出 0，public/profile/family 三项探测均成功且输出目录可写。完整 library run `efe38f26f590` 为 schema_version=1.1.0，420 App、1160 logical/HTTP attempts、零重试/429；App success 149、data_unavailable 270、failed 1，wall 842.57 s、enrichment 839.07 s。

与上一轮相比，真实来源新增 1 个 App；原 419 个 App 无遗漏，原 ownership 字段无变化，原成功的时长 137、成就 213、stats 25、Store 277 个块全部保留。Family group/shared library 均成功；唯一玩家成就 ACCESS_DENIED 与上一轮同一请求。顶层仍为 partial、退出 2，保留 280 条 ownership 不确定性，并在可选块中保留实际权限拒绝。输出没有重复 enrichment 请求、没有跳过后仍发送的请求，也未发现 Key/token 泄漏。

业务 JSON、同名 runtime JSONL 及 reinstall-audit.json 均保存至指定项目 Outputs；文件名时间仍为 UTC。本轮仅修改本地输出配置并重装，没有搬动旧结果，也没有新增业务逻辑。

## 2026-10-05 输出时区调整

后续输出改为上述 UTC+8 格式，并更新命名环境中的安装版。项目 Outputs 与旧 `~/.steamtool/Outputs` 的 29 个历史结果文件已转换：43,817 个时间字段、28 个文件名及 16 处文件名引用同步更新。转换前完整备份至项目 Outputs 的 `.timezone-backups`；`timezone_migration_20261005T004517510410_北京时间.json` 记录当次转换的原名、新名及文件校验值。随后将现有文件名和输出时区名称直接改为“北京时间”，时间值不变；后续重命名记录见 `beijing_rename_*.json`。

转换逐项核对了时间点和业务数据：只改变时间的显示时区，原始 Unix 时间戳、耗时、游戏数据和查询结果均保留。UTC+8 跨日文件名、日志和采集时间测试通过，完整离线测试 **114 passed in 20.92s**。

重装后从 `/tmp` 联网运行 doctor，run `cc633defa7a4` 的文件名、JSON 和运行日志均为 UTC+8。public/profile 探测成功；family 返回 `AUTH_EXPIRED`，本次状态为 partial、退出 2，需要更新家庭令牌后再验证家庭接口。输出目录保持指定绝对路径。

## 请求控制与停止

| 参数                                |                                   默认 |
| ----------------------------------- | -------------------------------------: |
| `STEAM_MAX_CONCURRENCY`           |                 4 个真实 HTTP 在途请求 |
| `STEAM_WEBAPI_RPS`                |                              2 请求/秒 |
| `STEAM_STORE_RPS`                 |                            0.5 请求/秒 |
| `STEAM_FAMILY_RPS`                | 0.5 请求/秒，额外服从 Web API 域名限制 |
| 连接/读取/写入/连接池超时           |                   10 / 20 / 10 / 10 秒 |
| `STEAM_MAX_ATTEMPTS`              |                        3，包含首次请求 |
| `STEAM_REQUEST_DEADLINE_SECONDS`  |              60 秒，从首次真正发送开始 |
| 本地退避基数/上限                   |                              1 / 30 秒 |
| `STEAM_STOP_GRACE_SECONDS`        |                                   5 秒 |
| `STEAM_PROGRESS_INTERVAL_SECONDS` |                                   5 秒 |

完整变量名见 `.env.example`。这些值是保守工程默认值，不是 Valve 公布的限额。首次发送前的排队不消耗逻辑请求预算；后续排队、重试和退避计入预算。429 对对应域名实施共享冷却，兼容秒数和日期 Retry-After；服务端等待不被本地上限缩短。等待过长会结束本次请求但保留冷却。认证、证书及结构错误不盲目重试，TLS 始终校验，不自动跟随重定向。

Python 在整个会话持有 `.runtime/instance.lock` 的文件锁。`steamtool stop` 检查锁、PID、启动标识、boot ID、UID、配置目录、应用标记及实际 CLI 命令行，使用 Linux pidfd 避免 PID 重用竞态；Conda Python 未提供 pidfd 包装时调用系统 libc 的同名接口。不支持 pidfd 或身份无法确认时拒绝发送信号。不会按进程名批量终止 Python。

SIGINT/SIGTERM 或 `steamtool stop` 会停止新派发、唤醒限速与重试等待，在宽限内收集结果后取消剩余任务，保存部分 JSON、关闭连接并释放锁。重复 stop 无害，默认不强杀。stop 最多等待 15 秒确认收尾；若自行设置超过此值的宽限，stop 可能先报告未确认，但不会强杀。

## 错误码与诊断

错误对象包含 code、来源、scope、API/AppID/目标主体、错误 ID、HTTP/上游状态和安全消息。不会把 403 推测成某种具体隐私设置，也不把失败转成空清单。

| 错误码                                         | 含义与处理                                |
| ---------------------------------------------- | ----------------------------------------- |
| `CONFIG_INVALID` / `TOOL_NOT_FOUND`        | 配置、参数或调用问题；修正后重试命令      |
| `AUTH_REQUIRED` / `AUTH_EXPIRED`           | 本地缺凭据或明确过期；更新本地配置        |
| `ACCESS_DENIED`                              | 上游拒绝或身份不符；不自动重试            |
| `NETWORK_TIMEOUT` / `NETWORK_ERROR`        | 有限重试；证书错误不关闭 TLS              |
| `RATE_LIMITED` / `UPSTREAM_UNAVAILABLE`    | 共享冷却或有限退避                        |
| `REQUEST_DEADLINE_EXCEEDED`                  | 逻辑请求预算耗尽，不提前违反冷却          |
| `RESPONSE_INVALID` / `DATA_UNAVAILABLE`    | 结构或数据缺失，保留未知状态              |
| `OUTPUT_WRITE_FAILED` / `LOG_WRITE_FAILED` | 保存/监督失败；停止派发并尽力保留部分结果 |
| `INTERNAL_ERROR`                             | 未预期程序问题；记录脱敏栈位置并终止      |

`doctor` 检查配置是否存在、凭据是否配置、输出可写性、显式工具注册表，以及一个公开商店探测。有 Key/SteamID 时加用户资料探测，有 token/SteamID 时加家庭组探测，不自动遍历所有工具。配置齐全仅表示可尝试，不保证账号权限或完整性。

## 测试与开发

```bash
conda activate steamtool
python -m pytest -q
python -m compileall -q main.py steamtool schema
python -m pip check
bash -n start stop
```

默认测试不联网，不读取真实 `.env`，不需要真实凭据。HTTP 使用 httpx MockTransport；生命周期测试在临时项目启动实际子进程，通过仅测试使用的 sitecustomize 注入模拟 HTTP。测试不会向任意非测试进程发送信号。安装测试在临时环境离线构建并安装 wheel，从源码目录外执行 CLI；不会切换项目的 Conda 管理方式。

`steamtool/Ports/` 每个 API 一个文件，`registry.py` 显式登记，只允许审核过的只读工具。`request_executor.py` 执行请求和恢复决定；`steamtool/error_handler.py` 只分类和决策。`steamtool/scripts/` 仅三个业务模块、持久化和 runtime 五个职责文件。增加 API 时实现适配器、登记工具并补契约测试，不新增另一套 HTTP/重试/日志机制。

`schema/` 定义数据模型与纯派生逻辑，`steamtool/contracts.py` 将当前来源证据适配为正式输出，`steamtool/input_parser.py` 处理 quoted name 与单项纠错。实现依据是 [本轮任务书](task/Steam_Tool_Codex_Task.md) 和 docs 下三份输入文档；两份原始设计资料保留。

详细命令、阶段提交及待联调项见 [实现记录](task/IMPLEMENTATION.md)，逐项测试映射见 [验收矩阵](task/ACCEPTANCE.md)。
