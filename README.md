# CS2 Analysis Agent

[中文](#中文) · [English](#english)

---

## 中文

本地运行的 CS2 demo 分析网站：回放、多回合分析、战术板与战术室、玩家数据，以及可选的 Agent 复盘。界面支持中文 / English 切换，Agent 输出跟随界面语言。

### 功能

| 入口 | 地址 | 说明 |
|---|---|---|
| 比赛 / 回放 | `/demos` | 16 Hz 2D 回放：真实玩家名、血量与装备图标、开枪/烟/闪/火效果、比分 |
| 多回合分析 | `/demos?wbmode=multi` | 筛选回合，停留/击杀/死亡热力图，道具聚类，我的比赛与职业参考对照 |
| 战术室 | `/demos?view=room` | 保存个人战术；战术板支持多阶段、多楼层、路线与道具的动态播放 |
| 玩家主页 | `/demos?view=profile` | 绑定 Steam（OpenID），自动追踪比赛，Rating / ADR / KAST 等数据 |
| 道具实验室 | `/lab` | 道具落点与弹道检查（2D / 3D） |
| 战术助手 | `/assistant` | 战术资料检索与问答 |
| 道具图文 | `/lineups` | 瞄点图文与视频抽帧核验 |

### 安装

需要 Windows、Python ≥ 3.12、Node ≥ 22。

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[test]"
# demo 解析器（demoparser2）
npm install --prefix outputs/cs2-coach-prototype
```

### 启动

```powershell
./start-tactics.ps1
```

打开 http://127.0.0.1:8790 。服务只监听本机，写操作需要页面自动携带的本地令牌。

### 数据与隐私

- demo、解析结果、模型权重和账号数据都只保存在本地（`data/`、`outputs/`），不进入仓库；仓库中 `outputs/` 只保留 Markdown 报告。
- Steam API Key 只能在网页里填写，保存在 `data/account/secrets.json`，接口不会返回它。
- 武器图标通过 `experiments/import-icons.ps1` 从本机 CS2 安装导入；雷达图放在 `data/maps/radar/`。
- Agent 复盘需要在 `.env` 中配置模型服务（参考 `.env.example`），并且只在点击后调用，有调用次数上限；其他功能完全离线。

### 目录

```
backend/cs2_agent/   服务端、demo 解析整理、统计、Agent 主机
backend/eregion/     AgentLoop 运行时
web/                 前端页面
experiments/         数据抽取脚本（demo → 回放/补充数据）、移动模型实验
tests/               pytest
outputs/**/*.md      实验与验证报告
```

### 常用命令

```powershell
$env:PYTHONPATH='backend'
./.venv/Scripts/python.exe -m pytest -q                         # 测试
./.venv/Scripts/python.exe -m cs2_agent.demo_workbench replay   # 重建 16 Hz 回放数据
./.venv/Scripts/python.exe -m cs2_agent.demo_workbench supplement
```

---

## English

A locally hosted CS2 demo analysis site with replay, multi-round analysis, a tactic board and tactic room, and player stats, plus an optional Agent review. The UI switches between 中文 and English, and Agent answers follow the UI language.

### Features

| Entry | URL | What it does |
|---|---|---|
| Matches / Replay | `/demos` | 16 Hz 2D replay: real player names, HP and loadout icons, shot/smoke/flash/fire effects, score |
| Multi-round analysis | `/demos?wbmode=multi` | Round filters, dwell/kill/death heatmaps, grenade clusters, my matches vs. pro reference |
| Tactic room | `/demos?view=room` | Save your own tactics; the board plays back stages, floors, routes and utility |
| Player profile | `/demos?view=profile` | Steam link (OpenID), automatic match tracking, Rating / ADR / KAST |
| Utility lab | `/lab` | Grenade landing and trajectory checks (2D / 3D) |
| Tactics assistant | `/assistant` | Tactic material search and Q&A |
| Lineups | `/lineups` | Lineup screenshots and video-frame verification |

### Setup

You need Windows, Python ≥ 3.12 and Node ≥ 22.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[test]"
# demo parser (demoparser2)
npm install --prefix outputs/cs2-coach-prototype
```

### Run

```powershell
./start-tactics.ps1
```

Open http://127.0.0.1:8790. The server listens on localhost only, and every write request needs the local token, which the page sends automatically.

### Data and privacy

- Demos, parsed matches, model weights and account data stay local (`data/`, `outputs/`). They are not committed; only Markdown reports under `outputs/` are in the repo.
- You enter your Steam API key in the web UI. It is stored in `data/account/secrets.json` and is never returned by the API.
- Weapon icons are imported from your local CS2 install with `experiments/import-icons.ps1`. Radar images live in `data/maps/radar/`.
- The Agent review needs a model endpoint in `.env` (see `.env.example`). It runs only when you click it and has a call cap. Everything else is offline.

### Layout

```
backend/cs2_agent/   server, demo processing, stats, agent hosts
backend/eregion/     AgentLoop runtime
web/                 frontend
experiments/         extraction scripts (demo → replay/supplement), movement-model experiments
tests/               pytest
outputs/**/*.md      experiment and validation reports
```

### Common commands

```powershell
$env:PYTHONPATH='backend'
./.venv/Scripts/python.exe -m pytest -q                         # tests
./.venv/Scripts/python.exe -m cs2_agent.demo_workbench replay   # rebuild 16 Hz replay data
./.venv/Scripts/python.exe -m cs2_agent.demo_workbench supplement
```

Earlier experiment notes (Chinese): [docs/research-log.md](docs/research-log.md)
