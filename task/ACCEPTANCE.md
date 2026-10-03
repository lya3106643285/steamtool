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
| 本人库、时长、成就与统计 | 完成 | 合成响应通过 | 本人库/近期清单已实测；逐游戏成就/统计未执行 |
| 家庭组与共享候选 | 完成，实验性 | 身份、枚举、截断与降级通过 | 家庭组/候选清单已实测；完整性与四类样本未验收 |
| 单游戏查询 | 完成 | 输入、歧义、关联通过 | 公开 appdetails、storesearch 成功；账号关系未执行 |
| 配置、注册、错误、并发/限速/复用 | 完成 | 离线契约与并发测试通过 | 公开与本人/家庭清单使用同一执行器，认证路径已实测 |
| start/stop、菜单、doctor、持久化/日志 | 完成 | 实际子进程、信号、文件失败测试通过 | Conda 下本机 doctor 的公开、本人资料、家庭组探测成功 |

## 待授权账号联调

凭据由用户留在本地 `.env`；不贴聊天。本次 `./start doctor` 已通过；后续用小样本验证本人已有且玩过的游戏及近期/成就主体。家庭需对照本人持有、已借玩、可共享但未玩、家人有但被排除四类；缺少某类样本时记录不可验证。

核对 include_family_licenses 的实际效果、共享列表的范围/截断、不同隐私返回，以及 protobuf 省略字段的实际 JSON 编码。当前不将省略字段推断为 false/0 或空清单。完整家庭 live 验收未完成；没有用 mock 性能数据承诺线上速度。


## 2026-10-04 Conda 迁移验证

项目 `.conda` 已创建（Python 3.12.14）；本地 `.env` 的三项配置生效，输出不展示秘密值。Conda 下完整离线测试 **66 passed in 2.79s**，包括 pidfd 系统 libc 兼容路径和四项 Conda 入口选择测试。Python 编译、pip check、Bash 语法通过。

本人库、近期记录、家庭组与共享候选均返回 state=ok；家庭候选的完整性保守为 false，借玩补充响应的数量一致性也未确认，不据此声称数据全量。各类游戏、成就/统计和愿望单仍需后续真实样本对照。
