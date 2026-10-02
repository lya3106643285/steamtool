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
