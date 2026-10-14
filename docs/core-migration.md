# Eregion 核心迁移记录

来源为本机 Eregion/JobHunterAgent 工作副本，读取时 HEAD 为 `23ac8382b760ebc0094252989e1d3a2bf2892606`。`core-migration.json` 记录实际源文件 SHA-256；不假定工作副本没有未提交变化。

## 保留的原实现

`backend/eregion/runtime/core/` 中的 engine、context、model、host_protocol 和初始化文件保持原字节：

- AgentLoop 观察、请求模型、校验工具、执行、保存和让出执行。
- 按用户修订号丢弃过期决策，取消后禁止执行迟到动作。
- 执行前写入操作记录；恢复时提示检查不确定动作，不自动重放。
- 保留完整工具调用与结果组的上下文窗口。
- 模型请求可中断等待，迟到结果丢弃；已发送的请求仍可能计费。

同时复制 request_context、request_options、context_experiments、model_output、model_runtime、provider_usage 和 browser/evidence 辅助函数。原上下文投影仍含求职场景分支，尚未改写为 CS2 业务逻辑；实验开关保持原默认值。

## 明确的迁移修改

1. runtime/__init__.py 改为轻量初始化，移除求职业务的批量导入。
2. provider_usage.py 只有 Base 导入改到 runtime/storage.py；此处创建本项目独立的 SQLAlchemy metadata，不加载求职数据库。
3. 新建 cs2_agent Host 和模型传输适配。Host 负责当前任务、调用预算、JSON 持久化与显式完成；决策循环仍是原 AgentLoop。
4. 原 test_loop_stale_results.py 复制后只替换工具 schema 辅助函数的导入，其取消/旧决策断言保持不变。

没有迁移原 TaskHost/TaskLoop：它们直接依赖求职仓库、职位来源、工作流和执行服务；不是纯通用模块。也没有迁移求职业务、浏览器自动填表、职业记忆数据库、旧密钥、旧会话或虚拟环境。当前不宣称完整 Eregion 产品全部能力都已迁入。

## 独立运行和验证边界

Python 依赖安装到 Cs2-agent/.venv；模型设置只读取本项目 `.env`，不读取旧项目设置。模型传输无自动 HTTP 重试。状态保存 calls/max_calls，恢复不重置预算；显式 finish_task 才算完成，普通承诺文本不算完成。

当前入口为 start-agent.ps1；一个任务只允许由用户启动的单个进程使用，尚无多进程调度服务。网页原型仍运行旧 JS 循环。此轮先迁移基础，不重新包装价值有限的旧统计报告，也不对外宣称已接入局势理解。

离线验证覆盖原核心哈希、工具回传、显式完成、分段恢复、预算延续、非法工具拦截、未知执行状态恢复、取消与旧决策丢弃、独立配置读取、模拟 HTTP 协议及用量记录。离线模型是测试桩，不是职业比赛模型；不需要 API 费用。

后续 CS2 扩展应通过 Host 和 Tool 接入：玩家可知状态重建、局势模型推理、职业案例或训练数据管线、可验证的行为评价。职业数据学习是独立研究任务，本次迁移没有训练模型。
