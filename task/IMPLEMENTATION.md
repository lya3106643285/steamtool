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
