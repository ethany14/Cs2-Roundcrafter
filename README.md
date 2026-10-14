# CS2 Agent 工作区

项目根目录：`C:\Users\zhiyu\Documents\Cs2-agent`

## 3D 决策实验室

运行 `./start.ps1`，打开 http://127.0.0.1:8788 。已有 6 个 Dust2 真实片段，可同步比较实际操作与候选路线，切换玩家视角、时间和其他玩家的响应分支。默认候选由本地规则生成，不产生模型费用。点击“让 Agent 推演方案”才使用本项目 `.env` 配置的服务，每次最多 5 次调用；通过原 Eregion AgentLoop 读取证据、职业参考、提交校验后的方案。

重建数据：`./.venv/Scripts/python.exe -m cs2_agent.studio`。前端 Three.js 已随项目本地提供。旧复盘入口仍在 `outputs/cs2-coach-prototype/start.ps1`。

本轮报告：`outputs/studio/3D决策实验室-验证报告.md`。当前是条件性动画推演，不是完整游戏模拟器，也没有验证胜率或最优动作。敌方未知位置不会使用实际 demo 隐藏坐标补齐。

## 本地 GPU 时序实验 v0.2

已在本机 Ryzen 9 9955HX3D / RTX 5070 Ti Laptop（约 12 GB 显存）实际训练。PyTorch 2.7.1+cu128，模型 1,409 个参数；3 个固定随机种子分别训练后平均预测。每个样本仅使用本回合当前及之前的 4 个快照，最多约 60 秒历史，早期不足部分重复最早已知状态。

对照模型使用完全相同的 GRU 结构，但将当前状态重复 4 次；这样可检查收益来自历史信息还是模型结构。训练轮数只在原训练数据内部选择：前两场拟合、第三场验证，然后用选定轮数在三场训练比赛重新训练。三场旧测试比赛已经被上一轮观察，因此本轮标为研发 benchmark，不能宣称是新的独立验证。协议在训练前写入 `data/situation/temporal-v1/protocol.json`，没有根据 benchmark 调参。

实际 Brier（越低越好）：原静态逻辑回归 0.1554；同规模当前状态 GRU 0.1407；历史 GRU 0.1552。历史模型在三场 benchmark 上都不如当前状态模型，本轮未证明时间序列的价值，不启用玩家决策建议。不能从这几场比赛推断所有时序模型都无效。

训练与评估耗时约 19.2 秒，PyTorch 峰值已分配张量显存约 74 MB（不含驱动/CUDA 上下文等总显存开销），0 次付费模型调用。程序限制 4 个 CPU 线程和最多约半数 GPU 显存分配。已保存两种模型的 6 份权重、逐随机种子及逐场指标、预测结果和初步局势标注表。

```powershell
# 环境安装；当前本机已完成，无需重复安装
./.venv/Scripts/python.exe -m pip install -r requirements-training.txt
# 新输出目录保留历史实验，防止覆盖结果
./.venv/Scripts/python.exe -m cs2_agent.temporal data/situation/dataset.json data/situation/temporal-new --device cuda
```

Agent 新增 `inspect_temporal_experiment` 与 `inspect_temporal_case`：读取真实结果，并在 CPU 上加载本地权重查询单个样本（不返回最终胜负）。当前指向已验收的 temporal-v1，不自动换成后续运行目录。

下一步优先增加空间与信息状态、用更细的时间步长重建行动，并标注少量决策题；不要仅靠增大模型或使用更多 GPU 时间。初步 CSV 不含最终胜负与模型预测，仍需人工限定玩家视角并填写判断，不能直接作为训练标签。

## 局势学习实验 v0.1（CPU，无 API 费用）

已实现 demo → 局势快照 → 回合胜负标签 → 小模型训练 → 按整场隔离的测试。语言模型不需要重新训练；原 AgentLoop 可以调用 `inspect_situation_experiment` 和 `inspect_situation_case` 查看本地实验。单局势工具不返回最终胜负标签。

当前从用户 Downloads/csdemo 的 9 个压缩包中选择 6 场 Dust2，原文件保留；本项目只解出所需地图。4–6 月的 3 场训练，9–10 月的 3 场测试，划分在拟合之前固定。共 129 回合、561 个有效快照。`data/situation/manifest.json` 记录比赛来源和分组，`dataset.json` 为匿名结构化数据，`pilot/evaluation.json` 为实际评估，`pilot/model.json` 为可读取的模型权重。

```powershell
# 将清单内职业 demo 转成数据集（需要现有 Node demo 解析依赖）
./.venv/Scripts/python.exe -m cs2_agent.situation build data/situation/manifest.json data/situation/dataset.json
# 目前只有 3 场训练，显式使用小样本诊断模式，不通过数据量门槛
./.venv/Scripts/python.exe -m cs2_agent.situation train data/situation/dataset.json data/situation/pilot --small-sample
# 完全独立的合成数据代码自检，不能当作职业比赛效果
./.venv/Scripts/python.exe -m cs2_agent.situation selftest data/situation/selftest
```

算法为固定参数的正则化逻辑回归，使用双方存活人数、存活队员血量/护甲/装备总值、回合时间、已下包状态和下包经过时间。比较训练集常数胜率与仅人数模型。固定时刻采样，排除热身、未结束/含糊回合、结束后的状态和一方已全部死亡的状态；每回合总权重相等，不让长回合占更多权重。支持新旧 demo 回合结束事件格式。最终胜负只当标签，队名、选手、最终比分和未来事件不进入特征。

评估包含 Brier、log loss、逐比赛指标、时间阶段、校准分箱和按比赛重采样的差值区间。仅 3 场测试时区间不可靠，不用它宣称泛化。预设最低 5 场训练/3 场测试只是研究门槛，不是产品验收；当前训练不足，`sample_gate_passed=false`。增加数据时另留新的测试比赛，禁止反复看同一测试集来调参。

第一轮测试比赛平均 Brier：常数 0.2494，仅人数 0.2198，完整状态 0.1554（越低越好）。这是有限的胜负相关性信号，尚未证明模型读懂战术，更不能把胜率下降归咎于玩家的某次动作。当前使用观战全局状态，敌方准确血量和装备不一定是玩家当时知道的信息；不能直接用于玩家决策评分。也没有空间控制、视线、烟雾、语音、队伍计划、动作序列或反事实分析。所有模型均标记 `ready_for_player_advice=false`。

训练/评估仅本地 CPU，首轮约 0.2 秒（不含解压和解析），0 次 LLM 调用，无 GPU 租赁。之后若让 Agent 用语言模型解释结果，才按已配置服务产生推理费用。六个解压文件约 2.5 GB。

视频并非只用于道具教学：CS2.APP 的 [POV 目录](https://www.cs2.app/demo-directory) 可按选手位置筛选，[战术目录](https://www.cs2.app/tactics-directory) 有 Execute/Fake/Setup 等分类。来源登记与未来视频—回合—tick 对齐模板在 `experiments/situation/video-sources.json`；本轮只核验了目录元数据，没有观看、转录、下载或用视频训练。POV 可能开启观战 X-ray，解说也不等于选手真实意图，需人工确认后再作为战术标签。

下一步：增加不同队伍的同地图比赛，并做少量“当时知道什么、可选行动、选择理由”的人工标注。先评估这些局势题的回答，再决定是否训练时序/动作模型。回合胜率实验只是基础检验。

解析字段参考 [demoparser2](https://github.com/LaihoE/demoparser)。职业轨迹训练与本实验的区别可参考原研究 [Learning to Move Like Professional Counter-Strike Players](https://arxiv.org/abs/2408.13934)；本项目未复现该论文的移动模型。

## 当前开发基础：Eregion Agent 核心

真正的 Python AgentLoop 已从 Eregion 本地工作副本迁入，位于 `backend/eregion/runtime/core/engine.py`。后续开发基于这个核心。

- `backend/eregion/runtime/core/`：原始 AgentLoop、对话窗口、可中断模型请求、Host 协议，逐字保留。
- `backend/eregion/runtime/request_context.py`：上下文归档、按需读取、资源新旧状态。
- `backend/eregion/runtime/provider_usage.py`：原用量记录与预算逻辑，仅改用本项目数据库基类。
- `backend/cs2_agent/`：本工作区的 Host、模型连接、工具接口和命令行入口。
- `tests/`：核心迁移验证；`docs/core-migration.md`：范围与边界；JSON 清单记录来源及文件哈希。

已创建独立 `.venv`，仅使用根目录现有 `.env`，无需填写第二份密钥。不通过路径引用、软链接或导入访问旧工作区。

```powershell
# 免费离线验证：真实核心执行工具循环，模型响应为测试桩
./start-agent.ps1 -Smoke

# 使用 .env 的模型服务，会产生正常推理调用
./start-agent.ps1 -Task '检查当前具备哪些能力，说明还缺少什么。'

# 显式恢复同一个任务，保留上下文和剩余调用预算
./start-agent.ps1 -Resume '<任务 ID>'

# 运行迁移测试
./.venv/Scripts/python.exe -m pytest -q
```

新电脑安装：Python 3.12+，执行 `python -m venv .venv`，然后 `./.venv/Scripts/python.exe -m pip install -e '.[test]'`。

当前已接入能力检查、局势实验查询、职业案例检索和自动案例复盘工具，尚未连接旧页面。工具扩展入口是 `cs2_agent.tools.Tool`，无需重写 AgentLoop。任务和用量记录保存在根目录 `data/core-tasks/`。同一任务请勿同时启动多个进程。

## 职业案例检索与主动复盘（2026-10-13）

最新进展见 `outputs/casebook/烟雾-材质-门与梯子-进展报告.md`，此前阶段见 `outputs/casebook/地图遮挡与玩家信息-进展报告.md`。后续所有面向用户的结果报告使用 Markdown（`.md`），JSON 只作程序数据和审计。

当前默认使用本机 CS2 导出的 `data/maps/current-scene.npz`（带碰撞材质、静态门和梯子外观），对近期比赛接受当前地图基准。可用 `experiments/import-current-map.ps1` 重建。旧 OBJ 仅作文件缺失时的降级来源。烟雾已加入生命周期、更新编号与扰动候选，真正体素透明度仍待实现；材质不等于穿透伤害。爬梯根据网络 MoveType=9，静态门不等于动态门状态。不要将这些信号当成已验证的决策评分。

已补充 `geometry.py` 的静态地图射线与 `perception.py` 的玩家信息证据。`start-review.ps1 -Build -Offline` 会依次提取、补充、生成 Markdown。单独补充可运行 `python -m cs2_agent.perception`。地图保存在 `data/maps/de_dust2.obj`（独立副本），几何来源与版本限制见报告；换电脑需准备该文件，不能因缺地图而假定无遮挡。当前地图版本未验证，发现标记也是近似值，禁止自动决策评分。

资料卡保存在 `experiments/knowledge/resources.json`，目前 6 条公开网页描述可通过 `find_learning_resources` 检索。它们不同于人工核对过的教程，不提供已验证投法；不等于下文 reviewed=true 的战术知识条目。

当前是一版可运行的本地案例 RAG：结构化局势检索 + 商用模型 + 原始 Eregion AgentLoop，不使用 CS-NET 权重、不训练模型。只处理 Dust2 接敌与支援调查；用户指定比赛后自动选片段，无需写问题。每次先复盘一个候选，避免一次花费过多。

```powershell
# 从现有 manifest 中的本地 demo 建库；按 demo 和提取代码哈希缓存
./start-review.ps1 -Build -Offline
# 一键自动调查，会使用本工作区 .env 模型服务，最多 6 次调用
./start-review.ps1 -Match 2398755
# 先本地收集目标和一个参考片段，再让模型分析，减少往返
./.venv/Scripts/python.exe -m cs2_agent.review --match 2398755 --prefetch --max-calls 2
# 检索覆盖检查及 20 对人工核对队列（无模型费用）
./.venv/Scripts/python.exe -m cs2_agent.casebook evaluate
```

数据在 `data/casebook/`，报告和原始证据在 `outputs/casebook/`。首轮 6 场比赛提取 778 个死亡前 2 秒片段：3 场参考比赛 382 个，3 场测试比赛 396 个。测试中 385 个有队友存活，270 个可检索到满足条件的参考。这只是覆盖检查，不是正确率；测试比赛沿用此前实验，不能称为新的独立盲测。

检索先严格匹配地图、阵营、双方人数、是否下包，再以位置、回合时间、装备值、最近队友距离排序；不按后续结果排序。排除同比赛、同 demo；每个参考回合最多返回一个案例。阈值为初始工程规则，未经战术相关性校准。目前未使用向量模型。候选按队友距离筛选，排除残局最后一名存活者；在前十个候选中优先挑有参考者，仍保留无参考时的明确返回。

所有案例都来自死亡前，因此存在明显结果选择偏差，不代表全部职业决策。职业玩家行为不是正确答案。当前无地图遮挡/导航、玩家已知信息、声音/语音重建，不做补枪可行性和决策对错评分。距离单位为游戏单位，不是米。记录的后续击杀仅为事件关联，不叫“成功补枪”。Actor 编号在每个 demo 内匿名化；模型仅接收片段信息，不上传原始 demo。

模型完成前，ReviewHost 强制检查已读取目标、已执行检索；存在参考时必须读取至少一个参考。审计记录与输出一起保存。此门槛验证工具使用，不证明模型结论正确。离线测试桩不计作真实 AI 复盘。

首轮真实服务验证共 5 次调用：无匹配案例的调查 4 次；本地预取后，有参考案例的调查 1 次。后者报告在 `outputs/casebook/0f220883035e4db688ff8b04dcd6130e.txt`，对应 JSON 保存证据读取审计。模型指出相似位置和人数下的队友距离、对手装备差异，明确无法确定是否失误。35 项 Python 测试通过；778 条记录均验证快照早于死亡事件、包含 10 人、无原始 Steam ID 和选手姓名。尚无教练盲评结果，不宣称建议质量达标。

战术/道具文字库已提供 SQLite FTS 检索与导入，但当前 **0 条经过人工核对的资料**，不会用自动编造的教程填充。待整理有来源的视频片段后，可执行：

```powershell
./.venv/Scripts/python.exe -m cs2_agent.casebook import-knowledge --file <notes.json>
```

文件为 JSON 数组，每条含 `id, kind(utility/tactic), map(de_dust2), title, body, source(https URL，建议带时间点), reviewed(人工核对后的布尔值), version(地图/游戏版本适用范围)`。只有 reviewed=true 的条目会返回给模型。中文搜索当前使用 SQLite 默认分词，语义和中文召回仍需改进。后续优先补几十条核对过的职业/道具/战术案例，再比较无检索与有检索的建议质量；当前尚未完成这一人工质量评估。

## 历史网页原型

以下内容保留用于后续迁移，仍使用旧 JS 复盘循环，并未自动切换到 Python 核心。现有报告不代表已具备游戏局势判断能力。

- `outputs/cs2-coach-prototype/`：可运行原型、源码、测试和调研文档。
- `outputs/roundcraft-prototype.zip`：源码交付包。
- `outputs/roundcraft-preview.jpg`：实际页面截图。
- `work/`：调研工具、REA 分析证据、测试 demo 与辅助脚本。

从本目录执行 `./start.ps1` 启动，打开 http://127.0.0.1:8787 。服务已运行时无需重复启动。

后续开发以本目录为工作区。完整说明见 `outputs/cs2-coach-prototype/README.md`。

## 自动 AI 复盘

后续验证见 [穿透厚度与伤害模型报告](outputs/casebook/穿透厚度与伤害模型-验证报告.md)：已接入凸包射线厚度和条件直接命中伤害工具；667 个不穿透样本最大伤害误差 1。穿墙候选未通过验证，仍禁止用于击杀判断；烟雾消散阶段不能凭占用网格判断可见度。

最新网络实体实验见 [Nuke 动态门与烟雾体素验证报告](outputs/casebook/Nuke动态门与烟雾体素-验证报告.md)，复现步骤见 [实体实验](experiments/entity-probe/README.md)。已区分沙二静态门板与 Nuke 动态门；两场沙二加入网络烟雾体素占用证据。6 场比赛补充实测伤害，任意墙体的穿透伤害预测尚未完成。

在本目录 `.env` 中填写 `LLM_BASE_URL`、`LLM_MODEL_ID`、`LLM_API_KEY`。导入 demo 后 Agent 自动查证据并交付总结和训练重点，无需提问。

本项目独立运行，不读取或引用其他工作区。不要提交或分享 `.env`；空白模板为 `.env.example`。Agent 说明见 `outputs/cs2-coach-prototype/AGENT.md`。

## 2026-10-13 长残局更新

新增两段 35 秒残局、真实 AI 条件方案、右侧敌方参照选择、烟闪火雷分类型持续效果及职业真实路径叠加。详见 `outputs/studio/长残局与职业路径-验证报告.md`。本轮模型实际调用 5 次，原流程未正常完成，经过本地结构与人数修正后保存；不得宣称已经验证最优方案。

重建顺序：`node experiments/studio_clutches.cjs`、`node experiments/studio_events.cjs`、`.venv/Scripts/python.exe -m cs2_agent.studio`。长片段右侧仅执行首个 6 秒动作，尚未连续重决策。


## 战术资料检索原型

运行 `start-tactics.ps1`，打开 http://127.0.0.1:8790/ 。首批 20 条 CS2.APP 页面元数据已建索引，支持地图、攻守、经济分类和中文关键词查询。视频执行步骤尚未核验，当前仅输出学习参考。页面可预览发送内容并调用本项目配置的模型进行引用筛选；不会自动调用。

详见 `outputs/tactics/战术资料库-RAG接入报告.md` 和 `outputs/tactics/战术卡逐条核验清单.md`。本轮外部传输仅做模拟测试，实际提供商调用尚未验证。


### Nuke 战术与本地投掷教学

运行 `start-tactics.ps1` 后打开 http://127.0.0.1:8790/nuke 。支持本地 demo 候选轨迹、投掷方法字段、近似锚点和逐人道具/时序检查。匹配仍待覆盖效果与游戏内复投验证。详见 `outputs/tactics/Nuke战术联动与三维教学-验证报告.md`。
