# 验收矩阵

默认全部离线，`httpx.MockTransport` 与合成 SteamID/响应；子进程测试也注入模拟 HTTP。下面的通过状态不是私人 Steam 账号的实测。

| 任务书编号 | 测试文件与主要用例 |
|---|---|
| A01–A02 | `test_foundation.py::test_registry_executor_log_json`：已知/未知/重复登记、虚拟工具完整闭环 |
| A03 | `test_game.py::test_public_and_ambiguity`：无 Key 公开详情、账号未知 |
| A04 | `test_acceptance_edges.py::test_owned_library_without_family_token`：自有库保留、家庭未知 |
| A05 | `test_accounts.py`：最终请求的 Key header、Service input_json、token 隔离 |
| B01 | `test_workflows.py::test_explicit_empty_wishlist`：显式空列表加 count=0 |
| B02 | `test_workflows.py::test_wishlist_200_is_not_automatically_empty`；`test_acceptance_edges.py::test_protocol_application_failure_with_empty_items` |
| B03、B13 | `test_workflows.py::test_wishlist_preserves_missing_details_and_duplicates`：缺详情不丢 ID、重复来源与数量差异 |
| B04–B06、B08、B11 | `test_workflows.py::test_library_semantics`：零时长、借玩、未玩家庭候选、双方持有、缺两周/缺价格、平台不相加 |
| B07 | `test_acceptance_edges.py::test_known_and_unknown_family_exclusions`：已知禁止、明确允许、未知及枚举空缺 |
| B09 | `test_accounts.py::test_family_identity_and_list`；`test_acceptance_edges.py::test_family_truncation_and_expired_token`：身份不符、不透明/过期 token、达到 max_apps |
| B10 | `test_accounts.py::test_accounts_and_encoding`；`test_workflows.py::test_achievement_unknown_does_not_become_zero`：空定义与失败分开，未知不算零 |
| B12、D08 | `test_game.py`：名称歧义、模糊/精确输入、sub/bundle 拒绝、不等 stdin |
| C01、性能验收 | `test_executor.py::test_hundred_requests_concurrency_and_speed`：100 请求，真实在途不超上限，并发 4 比并发 1 更快 |
| C02 | `test_executor.py::test_fast_responses_still_rate_limited`：极快响应仍按发送间隔放行 |
| C03–C04 | `test_executor.py`：429 秒数/日期、无提示退避、503、超时，最大总尝试 3 |
| C05 | `test_executor.py::test_nonretry_http` 与 `test_contract_and_certificate_errors_not_retried`：401/403/302/404、结构、证书不重试 |
| C06 | `test_foundation.py` 与 `test_executor.py::test_cache_context_separation_and_recovered_error`：同时调用共享任务，语言/地区隔离 |
| C07 | `test_executor.py::test_retry_after_date_and_budget_preserves_cooldown`、`test_cooldown_is_shared_and_stop_cancels_wait`；`test_acceptance_edges.py::test_first_queue_is_outside_logical_budget` |
| C08 | 缺详情与正常条目混合的 workflow 测试；`test_acceptance_edges.py::test_unexpected_workflow_error_is_terminal_and_redacted` |
| D01 | `test_acceptance_edges.py::test_log_context_and_separate_initialization`：并发任务/AppID 关联、连续初始化无重复事件 |
| D02 | `test_executor.py::test_cache_context_separation_and_recovered_error`：恢复后的最终 error=None，attempts 保留 |
| D03 | `test_foundation.py::test_redaction_and_atomic_write`；`test_acceptance_edges.py` 的输出、代理和异常脱敏测试 |
| D04 | `test_acceptance_edges.py::test_same_time_unicode_and_redacted_outputs`；foundation 非法浮点/旧结果防覆盖 |
| D05 | `test_lifecycle.py`：初始化/发布后日志失败、fsync 失败；`test_acceptance_edges.py`：运行中日志失败停止派发、输出路径不可写 |
| D06 | `test_lifecycle.py`：运行中/冷却中 stop，保留完成条目，重复 stop；菜单多次独立 run_id |
| D07 | `test_lifecycle.py::test_stale_or_reused_pid_is_not_signaled`：锁、PID 起始标识不匹配时不发送信号 |
| D09 | workflow/game 测试覆盖记录与候选 ID 映射、名称数组；详情中的 DLC 也进入映射 |

## 功能与真实验证

| 模块 | 实现 | 离线/本地集成 | 真实 Steam |
|---|---|---|---|
| 愿望单导出 | 完成 | 合成响应通过 | 已配置账号；愿望单真实查询未执行 |
| 本人库、时长、成就与统计 | 完成 | 合成响应通过 | 本人库/近期清单及逐游戏成就/统计已实测；补充字段存在缺失 |
| 家庭组与共享候选 | 完成，实验性 | 身份、枚举、截断与降级通过 | 家庭组/候选已实测且来源 AppID 无遗漏；四类接口样本已有证据，全量仍需客户端对照 |
| 单游戏查询 | 完成 | 输入、歧义、关联通过 | 公开 appdetails、storesearch 成功；账号关系未执行 |
| 配置、注册、错误、并发/限速/复用 | 完成 | 离线契约与并发测试通过 | 公开与本人/家庭清单使用同一执行器，认证路径已实测 |
| start/stop、菜单、doctor、持久化/日志 | 完成 | 实际子进程、信号、文件失败测试通过 | Conda 下本机 doctor 的公开、本人资料、家庭组探测成功 |

## 待完成的客户端对照与其他联调

凭据由用户留在本地 `.env`；不贴聊天。doctor 与完整 library 已联网执行，个人时长/成就/统计主体已核对；仍需人工核对已玩游戏的具体数值。家庭已有四类接口证据样本，应继续与客户端对照本人持有、已借玩、可共享但未玩、家人有但被排除四类；缺少本人时长不能证明从未玩过。私人愿望单未在本轮执行。

核对 include_family_licenses 的实际效果、共享列表的范围/截断、不同隐私返回，以及 protobuf 省略字段的实际 JSON 编码。当前不将省略字段推断为 false/0 或空清单。完整家庭 live 验收未完成；没有用 mock 性能数据承诺线上速度。


## 2026-10-04 Conda 迁移验证

项目 `.conda` 已创建（Python 3.12.14）；本地 `.env` 的三项配置生效，输出不展示秘密值。Conda 下完整离线测试 **66 passed in 2.79s**，包括 pidfd 系统 libc 兼容路径和四项 Conda 入口选择测试。Python 编译、pip check、Bash 语法通过。

本人库、近期记录、家庭组与共享候选均返回 state=ok；家庭候选的完整性保守为 false，借玩补充响应的数量一致性也未确认，不据此声称数据全量。各类游戏、成就/统计和愿望单仍需后续真实样本对照。

## 2026-10-04 CLI 安装及 shell 验证

`steamtool-cli` wheel 已安装至本机 Conda 环境，shell 通过用户 PATH 中的命令入口直接调用 `steamtool` / `teamtool` / `Steamtool`，不需每次激活环境。完整测试 **72 passed in 5.82s**。

新增 test_packaging.py 验证 wheel 不包含本地秘密/输出、脱离源码安装可运行、三项命令入口、config path/init/import、权限 0600 和拒绝覆盖、路径不随 cwd 改变，以及通过命令软链接运行后的单实例拦截、pidfd 停止和部分结果保存。D07 同时覆盖启动时间不符和完整 PID 信息吻合但属于其他命令的拒绝信号路径。

在 /tmp 通过已安装全局命令执行 doctor，公开详情、本人资料与家庭组探测均 ok，退出 0；仅输出安全汇总。卸载/重装本包后验证用户配置、结果与日志内容未改变，命令恢复可用。未进行 PyPI 发布或远端推送。

## 2026-10-04 命名环境 steamtool

实际创建并激活 Conda 命名环境 steamtool，Python 3.12.14，CLI 的三个用户入口均指向新环境；pip check 和 Bash 语法检查通过。命名环境中完整离线测试 **74 passed in 19.11s**，增加 start 的命名环境发现、优先级及自定义环境路径测试。

用户的 library 实例锁在迁移时仍被占用，原环境保留供运行中导出继续使用，未向任务发信号或更改账号配置。README 统一使用 conda activate steamtool 并说明退出旧 .venv 的步骤。

## 2026-10-04 完整 library 联网验收

用户明确授权联网执行 library。本轮在命名环境 steamtool 运行到底，耗时 840.60 秒，419 条记录，无重复 AppID，status=partial、退出 2；最终 419 个任务均结束，无 pending/running/cancelled。25 个任务全部补充来源成功，其余 394 个存在至少一个缺失来源，失败任务仍保留 AppID。

清单核对：本人接口 125/125，近期记录 10/10；借玩补充返回 137 条而 game_count 仍为 125，比本人集合多 12。家庭接口 419 条，max_apps=1000 与 10000 集合相同、未达上限。所有来源并集 419，与导出集合完全相同，遗漏 0、多余 0。家庭响应没有总量字段，complete=false 保留；集合一致验证只针对本次接口可见范围。

补充块：商店 ok 277/unavailable 142；时长 ok 137/unavailable 282；成就 ok 213/not_applicable 13/partial 1/unavailable 192；统计 ok 25/unavailable 394。错误共 DATA_UNAVAILABLE 920、ACCESS_DENIED 1；HTTP 400 385 次、403 1 次，其他为响应数据缺失。1668 次 HTTP 请求，无重试/429，维持原限速。

接口证据样本计数：本人持有且有时长 79；本人不持有、家人持有且有本人时长 12；本人不持有且可共享但无本人时长记录 83；本人不持有、家人持有且被排除 7。第三类不能确认从未玩过；四类尚未完成人工客户端核对。不将不可用字段推断为空、零时长或没有成就。

输出所有 AppID 均进入 id_map，时长/成就/统计主体均与配置本人一致；业务 JSON 不含配置中的 Key/token。业务 JSON、运行日志和完整性复查报告只存本地用户 Outputs，未提交私人清单。本轮未执行愿望单。
