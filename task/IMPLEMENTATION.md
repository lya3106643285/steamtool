# 实现与验证记录

任务书基线：`Steam_Tool_Codex_Development_Spec_v1.0_2026-10-02.md`。
初始仓库无代码、无提交、无 `.env`。只在本仓库开发，不创建远端或推送。

## 阶段 1

实现配置、错误/恢复对象、显式 registry、HTTP 执行器、单次运行复用、结构化脱敏日志、原子 JSON 写入。
合成工具通过 registry → executor → runtime → JSON 闭环；该工具只在测试注册，不作为生产占位接口。
原子发布使用同目录临时文件加硬链接，保证既原子可见又拒绝覆盖旧文件；这是对任务书 replace 方案的细化。
真实 Steam 接口/账号在本阶段未验证。

验证：Python 3.12.3；httpx 0.28.1、python-dotenv 1.2.1、pytest 8.4.2。
执行 `.venv/bin/python -m pytest -q`：3 passed。包含配置优先级/非法配置、注册和并发复用闭环、递归脱敏、Unicode、禁止 NaN 与旧结果防覆盖。

## 阶段 2

实现 appdetails/storesearch、精确 AppID/官方 app URL、唯一精确名称解析、候选索引和 `needs_selection` JSON、可执行 start 直接命令。
`.venv/bin/python -m pytest -q`：11 passed。
`./start game --appid 292030`：退出 0，匿名 appdetails 返回 HTTP 200 且通过身份/结构验证，业务 JSON status=ok。时间 2026-10-02T16:12Z。
此时仅验证公开商店路径，不代表本人库、家庭或账号接口成功。认证材料不会发送到商店。

## 阶段 3

实现本人库（自有/已借玩两种参数）、近期记录、schema、本人玩家成就/统计、用户资料、vanity，以及家庭组与共享清单适配器。
`.venv/bin/python -m pytest -q`：13 passed。新增测试检查最终 HTTP 认证头/Service input_json 编码、零时长、成就失败和空定义区分、家庭缺凭据/身份不符/未知排除值。
无 `.env`，未进行私人账号 live 请求；本人 Key 和家庭 token 的验收仍待用户本地配置。
家庭 token 本地解析只用作目标身份预检；必须随后由 Steam 接受认证请求，并在有家庭时返回包含本人的成员清单。未宣称本地校验 JWT 签名。不透明/无有效身份声明的 token 保守拒绝绑定。
家庭清单完整性始终为 false（无已验证分页保证）；达到 max_apps=10000 时额外标记可能截断。不导出主体/单位不明的 rt_playtime。

### 协议复核

- [Valve IPlayerService](https://partner.steamgames.com/doc/webapi/IPlayerService)：使用 input_json；认证单独发送。
- [Valve Web API authentication](https://partner.steamgames.com/doc/webapi_overview/auth)：个人 Key 使用 x-webapi-key。
- [Valve ISteamUserStats](https://partner.steamgames.com/doc/webapi/ISteamUserStats)：单 AppID、指定目标玩家。
- [SteamTracking FamilyGroups](https://github.com/SteamTracking/Protobufs/blob/f5b0600750b2d5634c78f654845b6d5954f700db/webui/service_familygroups.proto)：复核只读方法、身份、拥有者、max_apps 字段；内部接口仍实验性。通过 GitHub commits API 获取该文件最新提交 f5b0600750b2d5634c78f654845b6d5954f700db。
- 愿望单协议已从同仓库 webui/service_wishlist.proto 读取，后续使用 steamid、items、appid/priority/date_added 和 count；不调用任何写入方法。

这些协议资料不构成真实账号联调证据。

## 阶段 4

完成 library/wishlist/game 编排；wishlist 数量复核和重复来源保留；独立拥有关系、本人时长/成就/统计；GameRecord 与 ID/名称索引共用。单游戏只补该 AppID 的详情，不为整个库抓详情和成就。
有限工作队列复用同一个执行器；在真实 HTTP 发送层限制并发、域名速率、家庭附加速率和共享冷却。成功缓存与并发在途复用保留原采集时间。
`.venv/bin/python -m pytest -q`：34 passed，0.95s。包含 100 请求并发上限/并发 1 与 4 性能对比、快速响应限速、429 秒数和日期、超长冷却/预算、5xx/超时有限重试、401/403/重定向/证书/结构错误不重试、语言地区缓存隔离、停止等待。
业务合成测试覆盖零时长、借玩/自有/双方持有、未玩家庭候选、未知排除枚举、失败成就不补零、平台时长不相加、缺价、愿望单去重/缺详情/数量不符/明确空清单、HTTP 200 异常结构、单游戏请求范围。
SteamDB 扩展公开实现复核支持明确 exclude_reason=0 为无排除；未知非零枚举目前保留原值和 available_via_family=null，未根据未验证枚举猜测。
尚未配置私人凭据，以上均为合成测试；不宣称私人愿望单、本人库或完整家庭库已实测。

## 阶段 5

完成交互菜单、doctor、单实例 flock、进程启动标识/boot ID/UID/项目/命令行校验和 pidfd 停止。SIGINT/SIGTERM/stop 停止派发和等待，并在宽限后取消剩余任务；集合逐个完成时立即保留已取得 ID，取消不会丢掉此前集合与详情。默认不强杀。

补全日志初始化、运行中及发布后失败路径；发布后失败只可原子更正本轮相同 run_id 的文件。补全统一 HTTP/传输错误分类、HTTP 200 内上游失败、未知异常终态、DLC ID 映射和并发日志关联。

最终检查命令与结果：

| 命令 | 实际结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | **61 passed in 4.18s**；无真实凭据、默认不联网 |
| `.venv/bin/python -m compileall -q main.py config.py error_handler.py Ports scripts` | 退出 0 |
| `.venv/bin/python -m pip check` | `No broken requirements found.` |
| `bash -n start stop` | 退出 0 |
| `git diff --check` | 退出 0，无空白错误 |
| `./start doctor` | JSON status=partial；公开 appdetails 探测成功；三项账号配置均为 false，按预期报告能力不足 |
| `./start game 'Portal 2'` | 退出 0；storesearch 成功、唯一精确候选 AppID 620、详情成功、JSON status=ok |
| `./stop`（无实例） | 退出 0，报告锁已释放，无其他进程受影响 |

真实公开探测证据（UTC）：

- 2026-10-02T16:12Z：AppID 292030 appdetails HTTP 200，返回名称“巫师3：狂猎 — 重制版”。
- 2026-10-02T16:40Z：doctor 再次成功探测公开详情；配置能力不足与探测结果分别表达。
- 2026-10-02T16:40Z：搜索 Portal 2 并查询 AppID 620 详情成功。结果与运行日志保存在本地 Outputs，未提交真实网络响应文件。
- 对应北京时间日期为 2026-10-03。以上均为匿名商店请求，不是账号验收。

离线性能单独测量：MockTransport 固定每次响应延迟 5ms，100 个请求，发送速率设为不构成瓶颈。并发 1：100 成功，0.5522s，实际峰值 1；并发 4：100 成功，0.1526s，实际峰值 4。不将该约 3.62 倍样本加速比宣称为 Steam 线上保证。

新增 [验收矩阵](ACCEPTANCE.md) 覆盖任务书 A01–D09；README 包含 WSL 安装、配置、命令、错误码、输出、并发和停止流程。[合成 JSON](examples/synthetic_game.json) 与 [合成 runtime JSONL](examples/synthetic_game.runtime.jsonl) 显式标记 MockTransport 数据；未提交凭据或私人库清单。

### 最终协议细化及调整

1. 家庭排除枚举在原始 [steammessages_familygroups.steamclient.proto](https://github.com/SteamTracking/Protobufs/blob/bd86e4c6419d40f9a5de222d8b9f68fb3a1fde07/steam/steammessages_familygroups.steamclient.proto) 中复核。明确 0 代表 Included；已知 1–4、6–13、15–30 表达排除，5/14 及未来未知值保留资格未知。此项替代阶段 4 的临时保守处理，但仍不代表真实账户验证。
2. 愿望单协议固定参考 [fcbb9a107a0ff5293385f24d6c774eeb5e3d4c84](https://github.com/SteamTracking/Protobufs/blob/fcbb9a107a0ff5293385f24d6c774eeb5e3d4c84/webui/service_wishlist.proto)。省略 repeated items 的 JSON 行为仍未实测；因此省略字段保守不可用，只有显式空列表与明确零数量可证明空。
3. 未知家庭统计主体/单位的 rt_playtime 不导出，而非放入含糊 raw；已确认本人接口字段保留分钟语义。
4. 原子发布采用临时文件 + 同目录硬链接，避免 replace 覆盖旧运行；只有发布后日志故障允许核对 run_id 后更正本轮文件。
5. 家庭列表固定 max_apps=10000 且 complete=false；达到上限额外标记。宁可明确保留完整性限制，也不宣称已取得全家庭库。
6. 名称歧义统一输出候选，由用户下一次指定 AppID；菜单也使用此路径，不再引入另一套名称猜测机制。
7. 不实现可选 all、全目录、跨运行缓存；未添加额外业务层，scripts 仍为五个职责文件。

### 最终交付状态

| 功能/支撑 | 实现 | 离线/本地验证 | 真实联调 |
|---|---|---|---|
| 愿望单 | 完成 | 通过 | 未执行，缺本地 SteamID |
| 本人库/时长/成就/统计 | 完成 | 通过 | 未执行，缺个人 Key |
| 家庭候选/资格 | 完成，实验性 | 通过 | 未执行，缺本人 token；完整性仍未验收 |
| 单游戏 | 完成 | 通过 | 公开搜索/详情成功，账号关系未执行 |
| 注册、错误、并发、复用、JSON、日志 | 完成 | 通过 | 公开执行路径成功，其余以离线证据为准 |
| start/stop、菜单、doctor | 完成 | 实际子进程测试通过 | 本机命令和公开探测成功 |

私人愿望单、本人库、include_family_licenses、家庭四类样本和完整性 live 验收仍待本地凭据。未进行自动登录、Key/token 获取、写账号操作、远端创建、推送或发布。

## 2026-10-04：Conda 环境迁移与本地凭据联调

按用户后续要求，由 venv 改为 Conda。新增 `environment.yml`（Python 3.12、pip、固定运行依赖），在本项目 `.conda` 创建环境；本次实际 Python 3.12.14 / Conda 26.1.1。依赖及下载缓存加入 Git 忽略。

`start` 优先采用 STEAM_CONDA_PREFIX，其次项目 `.conda`，最后已激活的 CONDA_PREFIX；直接 exec 选定环境的 Python，保留进程身份和信号传递。旧 `.venv` 保留在本机，但入口不再选择它。缺少环境、版本或依赖时显示 Conda 安装提示。生命周期测试改用运行测试的解释器环境，不依赖开发机器的 `.venv` 路径。

该 Conda Python 构建未提供 os.pidfd_open / signal.pidfd_send_signal。增加调用系统 libc 的 pidfd_open / pidfd_send_signal 兼容路径，继续先固定进程身份再校验和发信号；无 pidfd 支持时仍拒绝发送。不改成裸 PID kill。

用户原先将 SteamID/Key 填在 Config 默认值；配置加载函数实际读取 `.env`/环境变量，因此将值迁移到未提交的 `.env` 并清空源代码默认值。保留已有 `.env` 非空值及用户随后添加的家庭 token，文件权限 0600。检查时曾意外显示未提交代码中的 Key，已告知用户建议更换；未将该 Key 或 token 提交到 Git。

验证结果：

- `.conda/bin/python -m pytest -q`：**66 passed in 2.79s**。包括 Conda 入口选择/参数安全传递、缺环境提示，以及实际子进程停止/取消和 pidfd libc 兼容测试。
- `.conda/bin/python -m compileall -q main.py config.py error_handler.py Ports scripts`、`bash -n start stop`：退出 0。
- `.conda/bin/python -m pip check`：No broken requirements found。
- `./start --help`：Conda 下退出 0。
- `./start doctor`：退出 0、status=ok；公开商店、本人资料、家庭组均 state=ok，没有最终错误。三项凭据均已配置；本地 token 主体与目标匹配，Steam 接受了实际家庭组认证请求。
- 低频读取 GetOwnedGames 两种模式、GetRecentlyPlayedGames、GetFamilyGroupForUser 和 GetSharedLibraryApps：均 state=ok，无最终错误。本人库与近期清单在声明响应范围内数量一致；借玩补充数量一致性未确认，complete=false；家庭候选继续 complete=false。未逐游戏抓取整个库的详情或成就，不将清单请求成功当作完整家庭验收。
- `.env` 已被 Git 忽略，当前源代码默认凭据为空；真实响应及日志保存在本地 Outputs，没有提交账号 ID、token 或私人库清单。

使用方式与环境路径依据 [Conda 官方环境管理文档](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)。私人愿望单、逐游戏成就/统计、家庭四类样本与完整性仍需后续验收。保留此前阶段记录作为历史证据。

本次提交仅包含迁移与验证改动；用户原有 README 排版调整及任务书向 task 的移动保留在工作区。

## 2026-10-04：可安装 CLI 包与直接终端调用

按用户要求，提供安装后的 shell 命令 `steamtool`，并保留 `teamtool` / `Steamtool` 别名。通过 pyproject.toml 的 console scripts 生成命令，由 pip 安装/卸载 `steamtool-cli`。代码统一放入 steamtool 命名空间，API 与业务职责边界不变；steamtool/scripts 仍为五个职责文件。源码 main.py、start/stop 保留为兼容入口，不承担安装/卸载职责。

配置由安装目录分离到默认 `~/.steamtool`，可用绝对路径 STEAMTOOL_HOME 覆盖；配置、Outputs 和 .runtime 跨工作目录稳定。config init 创建空模板，config import 私密复制已有配置，两者均独占创建、权限 0600、拒绝覆盖。config path 不读取或打印秘密内容。wheel 包含空白资源模板，排除真实 .env、输出和运行状态。

停止逻辑增加应用标识、安装入口和命令别名/软链接识别；继续验证锁令牌、PID 启动时间、boot ID、UID、配置目录及完整 argv，再通过 pidfd 发送信号。python -m steamtool 也可运行。无法确认身份仍拒绝发送信号。

本机安装到现有项目 Conda 环境，在 ~/.local/bin 创建三项命令软链接，将用户命令目录加入 ~/.bashrc 的 PATH。新开终端可以直接调用，不需手动激活 Conda。软链接依赖当前安装环境的绝对路径，须保留该 Conda 环境；更换安装位置时需调整链接。原始项目 .env 保留，私密复制到 ~/.steamtool/.env；以后使用 config path 定位并维护安装版配置。

验证：

- 完整离线测试 **72 passed in 5.82s**。新增 wheel 独立安装、资源/命名空间检查、三项命令入口、配置权限/不覆盖、跨目录路径稳定、安装命令软链接下单实例与停止保存部分结果测试。测试临时环境仅用于隔离安装验证，项目运行环境继续由 Conda 管理。
- 在 /tmp 直接执行 teamtool --version 与 steamtool --help，退出 0，无需激活环境。
- 全局 steamtool doctor：退出 0、status=ok，public_probe/profile_probe/family_probe 均 ok、无最终错误。结果和日志保存在用户 Outputs，未提交。
- 卸载本包后确认已安装模块消失，用户配置、结果及日志的内容哈希保持不变；重装 wheel 后三个命令入口恢复。
- Python 编译、Bash 语法、pip check 均通过。

打包方式参考 [PyPA 的 pyproject.toml 文档](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) 和 [命令行工具打包文档](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)。当前仅构建本地 wheel，未发布到 PyPI、未推送远端。已有私人愿望单、逐游戏成就/统计和家庭完整性验收边界继续保留。

本次提交保留用户已有 README 表格排版和任务书移动为未提交工作区改动。

## 2026-10-04：Conda 命名环境 steamtool

按用户要求，将环境规范改为命名环境 `steamtool`。`environment.yml` 的 name 改为 steamtool，README 改用 `conda env create --file environment.yml` 和 `conda activate steamtool`，补充退出旧 `.venv` 的使用步骤。

本机使用 Conda 离线克隆原项目 `.conda` 至 `~/miniconda3/envs/steamtool`，保留 Python 3.12.14 与现有依赖；在新环境重新安装本地 CLI wheel，使入口的绝对 Python 路径指向新环境。用户 PATH 中 steamtool/teamtool/Steamtool 的软链接已原子更新。迁移时安装版 library 实例锁仍被占用，因此保留原 `.conda` 供已有任务继续使用，没有停止任务、改动凭据或删除结果。旧任务可在原终端完成或通过 Ctrl+C 收尾后切换环境。

源码兼容入口 start 在显式 STEAM_CONDA_PREFIX 后，查询 Conda 环境注册表选择命名环境 steamtool；支持自定义 envs 目录及含空格路径，之后回退到旧项目 `.conda` 或已激活环境。仍直接 exec 选定环境的 Python，保留信号和实例身份。

验证：新命名环境中完整离线测试 **74 passed in 19.11s**；新增命名环境优先于旧项目/无关活动环境、无需激活即可选择命名环境的测试。实际激活后 Python sys.prefix 为命名环境目录，pip check 无依赖冲突；在 /tmp 直接运行 steamtool/teamtool --version、源码 start --help 及 Bash 语法检查均通过。本轮没有新增 Steam 网络请求。

环境克隆参考 [Conda 官方环境管理文档](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#cloning-an-environment)。原有 README 表格排版和任务书移动继续保留为未提交工作区改动。

## 2026-10-04：完整游戏库联网执行与清单完整性复查

在用户明确允许联网后执行已安装 steamtool library，使用已有本地三项配置，原并发/速率不变。此前取消运行的文件保留；本轮独立 run_id，运行 840.60 秒后自然结束，退出码 2、status=partial，导出 419 个不重复 AppID。实际发送 1668 次请求，无重试/429；没有因测试耗时而取消任务。

执行后通过同一 Executor 和只读接口进行小规模独立复查。本人接口 125 条，game_count=125，响应内数量一致；借玩补充 137 条，game_count=125，比本人清单多 12，因此不证明其完整性。近期 10 条、家庭候选 419 条；所有源集合并集与导出集合完全相同，缺失/额外 AppID 均为 0。

家庭 max_apps=1000/10000 两次均返回相同 419 个 AppID，未观察到截断，但实际响应只有 apps/owner_steamid，没有全量计数。按 [家庭请求/响应协议](https://raw.githubusercontent.com/SteamTracking/Protobufs/master/webui/service_familygroups.proto)，该接口未提供可供本次核对的总量/分页字段，不据此承诺 Steam 客户端全量一致。请求包含 include_own/include_excluded/include_non_games，419 是候选条目数，不是纯游戏或可共享游戏数。[Valve GetOwnedGames 文档](https://partner.steamgames.com/doc/webapi/IPlayerService#GetOwnedGames) 也限定其为可见的本人游戏响应，不将 125 与其他查询口径直接等同。

最终商店详情 277 成功/142 不可用，时长 137 有记录/282 不可用，成就 213 完整/13 不适用/1 部分/192 不可用，统计 25 成功/394 不可用。错误为 DATA_UNAVAILABLE 920 与 ACCESS_DENIED 1；HTTP 400 385、403 1，另有缺成就定义、商店详情不可提供、没有统计列表等响应内缺失。保留未知值，没有凭状态猜测隐私设置或生成不存在的数据。

真实接口证据提供四类样本：本人持有且有本人时长 79、本人不持有但有借玩时长 12、本人不持有且可共享但没有本人时长记录 83、本人不持有且被排除 7。无时长证据不等于从未玩过；人工 Steam 客户端对照仍未完成。

验证业务 JSON 中全部记录进入 id_map，个人指标主体一致，Key/token 未写入输出；结果和额外审计报告留在 ~/.steamtool/Outputs，不提交私人 ID/名称/响应。README 和验收矩阵更新真实验证范围，仅提交安全汇总及说明，不修改业务实现。原有用户 README 排版和任务书移动继续保留。

## 2026-10-04：V1.1 工程优化补丁

本轮按 `Steam_Tool_V1.1_Optimization_Patch_Spec.md` 修正状态语义、依赖调度、运行内去重和监督统计。Family 两个 adapter、token 验证方式、ownership 合并、start/stop、并发/限速配置均沿用既有实现。没有新业务能力、数据库或跨运行缓存；保留用户已有 README 修改和任务书移动。

| 修改文件 | 目的与关键行为 |
| --- | --- |
| `steamtool/error_handler.py` | 将错误码映射与重试决策分开；明确 capability/data/failed；未解释的 HTTP 400 和所有 5xx 属于真正失败，401 为认证过期 |
| `steamtool/Ports/request_executor.py` | Result 暴露 outcome；兼容成功 state=ok；只允许指定 adapter 解码 HTTP 400 的结构化应用错误；统计终态及 HTTP 状态，不将重试历史当最终失败 |
| `steamtool/Ports/get_schema_for_game.py` | 校验 achievements 与 stats 定义，暴露 capability；缺 schema 为 data_unavailable，损坏结构为 failed |
| `steamtool/Ports/get_player_achievements.py` | 明确无 stats 的结构化响应归为 capability 不适用；其余应用错误为数据不可用，损坏响应为失败 |
| `steamtool/Ports/get_user_stats_for_game.py` | 同上；响应主体不匹配归 RESPONSE_INVALID，保留所有成功统计数据 |
| `steamtool/Ports/registry.py` | 在原 single-flight 上共享全部终态结果，避免失败后再次调用重发；首个调用者取消不丢共享结果，不改注册结构 |
| `steamtool/scripts/library.py` | schema 驱动条件调度，两个下游独立并行；无证据为 unknown/data_unavailable；一个 App 一个 task；主状态按核心 collection/ownership 判定 |
| `steamtool/scripts/game.py` | 共享块与 coverage 增加 outcome；商店补充记录独立 planner/operation；not_applicable 不进入业务 errors |
| `steamtool/scripts/runtime_debug.py` | task 四种完成结果独立统计，新增 operations、http_by_api、enrichment_plan；decision 日志关联 App、操作、理由及依赖错误 |
| `steamtool/scripts/persistence.py` | schema_version 升至 1.1.0，保留 envelope、字段和原子写入机制 |
| `tests/test_v11.py` | 新增 37 项状态、依赖、并发、去重、Family、字段和取消契约测试，全部使用合成数据 |
| `tests/test_accounts.py` | 将明确上游无数据的断言改为 data_unavailable，保留认证与编码检查 |
| `tests/test_executor.py` | HTTP 不重试测试同时验证真正失败与 404 数据不可用的完成结果 |
| `tests/test_acceptance_edges.py` | 调整完成状态；更换凭据的模拟场景使用独立 Registry，保留过期与截断回归 |
| `tests/test_workflows.py` | fixture 增加 stats 能力证据；缺商店数据与不完整响应的断言按新分类验证 |
| `README.md` | 更新 schema_version、成功兼容字段、调度、主状态、运行指标及真实性能边界 |
| `task/ACCEPTANCE.md` | 分别记录单元、MockTransport、真实 Steam 验收、benchmark 和未验证范围 |
| `task/IMPLEMENTATION.md` | 逐文件记录补丁行为、实际依赖图、状态兼容、实现约束与交付范围 |

实际依赖图如下，每个 App 独立推进，仍由统一 Executor 控制发送、并发、限速、冷却和重试：

```text
collection → AppID 合并/去重 → 并发 App worker
    ├─ store → 合并商店详情
    └─ schema → 有成就定义？ → player achievements
              → 有 stats 定义？ → user stats
              → 明确空定义：not_applicable，不发下游请求
              → schema 不可用/失败：data_unavailable + DEPENDENCY_FAILED，能力 unknown
    → 合并 → App outcome → 持久化
```

schema 接口同时返回 stats 和 achievements 定义的用途由 [Valve ISteamUserStats 文档](https://partner.steamgames.com/doc/webapi/ISteamUserStats?l=english) 支持。有效 availableGameStats 缺某类列表按该完整 schema 中的空定义处理；整个 schema 缺失不推断没有能力。未经验证的数字 app_type 和游戏名称不参与跳过。

成功块保留 state=ok，新增 outcome=success；state 的 not_applicable、data_unavailable、failed 对应同名 outcome。task 按其操作结果 failed > data_unavailable > success > not_applicable 汇总，not_applicable 本身不使含成功操作的 App 失败。operations 包括已跳过的逻辑操作，HTTP 计数只包括实际请求；三者不能互相等同。数据不可用允许 errors/event 说明，capability 不适用不计业务 error。

离线验证：项目 Conda 环境完整 111 项通过；新增纯单元契约 19 项、MockTransport 契约 18 项，另保留原有 74 项。Python 编译、Shell 语法、pip check 和 diff 检查通过。真实 benchmark 的单独结果见后续验收记录。

性能边界：仍要查询 419 个 Store 条目时，在原 store_rps=0.5 下发送间隔最低约 836 秒。减少 Web API 无意义请求并不保证 wall time 同比例减少；本轮不调高速率、不改成串行，也不新增复杂类型判定以绕过这一限制。

真实验收已完成：run_id=29c6dae6fff1，schema_version=1.1.0，419 App、1157 logical/HTTP attempts、App outcome success 148/not_applicable 0/data_unavailable 270/failed 1，wall 840.671880 s、enrichment 837.084593 s。请求数下降 511（30.64%），耗时基本持平，Store 限速仍是瓶颈。独立 not_applicable operation 140，不能与 App outcome 的 0 混为同一口径。Family 及所有 AppID/ownership 字段与基线一致，原成功时长/成就/stats/Store 块没有丢失；唯一 ACCESS_DENIED 与基线同请求。顶层 partial 是保留既有 ownership 未知值的结果。完整 benchmark、实际样本、未验证项及安装版 CLI 的范围见 `task/ACCEPTANCE.md` 和 README 的 V1.1 章节。

## 2026-10-07：正式数据契约与批量 Games

依据 `Steam_Tool_Codex_Task.md` 及 docs 下三份输入设计文档实现；两份数据契约输入资料和运行逻辑说明原样保留。正式有效规范为 `docs/data_contract.md`，SCHEMA_VERSION=2.0.0。软件包版本独立，旧 game/doctor 的 1.1.0 外壳和历史结果保留。

| 文件 | 本轮职责 |
| --- | --- |
| `schema/base.py` | 12 个要求的基础模型及共享 PriceValue；Meta 五种状态；严格保留 null/false/0/-1；字符串字典 key；Bundle price 无 Meta |
| `schema/feature.py` | Run、三个 Record/Result、Summary、排行、Coverage；统一状态聚合和根级错误引用验证 |
| `schema/model.py`、`schema/version.py` | dataclass 类型校验与递归序列化；正式/旧格式版本集中管理；没有新增依赖 |
| `steamtool/contracts.py` | 把已有来源证据适配到正式外壳；仅输出各 Feature 要求的字段 |
| `steamtool/input_parser.py` | quoted CSV-style 名称解析；六类输入错误和项定位；COLLECTING_INPUT/CORRECTING_ITEM 状态机 |
| `steamtool/main.py` | games CLI 与多行收集；输入错误停留 CLI；明细/Top-N 参数；正式结果保存与取消/日志失败回写 |
| `steamtool/scripts/game.py` | 批量名称复用现有精确解析和查询；未解析目标只记录业务错误；重复明确 AppID 合并 |
| `steamtool/scripts/library.py` | 默认跳过玩家完整成就明细；Library 不请求 Store/Stats；保留集合来源与已知名称；正面 schema 不被玩家记录缺失推翻 |
| 配置模板、`config.py`、`pyproject.toml` | Top-N 默认 10，支持 0 和本次参数覆盖；wheel 包含 schema 包 |

设计输入的 UTC 时间说明与本次会话先前明确的北京时间输出要求不同；保留已经生效的 UTC+8、北京时间文件名和原始 Unix timestamp，正式规范明确此处理。

现有来源没有已验证的独立成就解锁汇总接口，默认只保留已知 total，unlocked/completion_ratio 为 null、Meta.partial；不为填汇总暗中查询完整列表。显式 --achievements 后复用已有玩家成就接口计算汇总和填入明细。确认无系统时使用成对 -1、null 明细和 not_applicable；查询失败保留 Record 和根级错误引用。

Bundle 来源、地区购买/获取资格、多拥有者昵称映射仍未定义，适配层保留 TODO、unavailable/null。平台零时间只有在支持信息已确认时才映射为 0；明确不支持才映射为 -1。没有新增 API、爬虫、缓存或运行框架。

新增 67 个参数化测试用例，完整离线验证 **181 passed in 25.40s**；包含模型语义、各功能字段组合、Summary/排行/Coverage、CSV 与重输、明细开关/无能力/查询失败、已知名称和本人拥有者、未取得清单不假装空集合、取消保存、晚期日志失败回写、文档一致性及实际安装版管道纠错。原有子进程、请求机制与 wheel 验证继续通过。Python 编译、bash 语法、pip check、git diff --check 通过；仓库没有独立 lint/type-check 配置。

已离线构建并重装当前命名 Conda 环境；从 /tmp 核对安装版 steamtool 29 个 Python 文件、schema 5 个 Python 文件与源码相同，现有命令入口可见 --achievements 与 --ranking-limit。本轮没有使用真实账号进行新契约的联网验收，历史联网结果不作为 2.0.0 的真实数据验收证据。
