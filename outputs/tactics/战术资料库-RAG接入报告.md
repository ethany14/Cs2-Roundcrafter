# CS2.APP 战术资料库接入报告

日期：2026-10-13。来源：https://www.cs2.app/tactics-directory

## 本轮完成

- 目录当前页面的 20 个战术条目已经建立本地来源卡和 SQLite 索引，覆盖 7 张地图。不是全站抓取。
- 保留页面标题、地图、攻守、经济、战术类型、介绍、YouTube 链接、抓取时间和页面 SHA-256。
- 本地应用：[战术资料库](http://127.0.0.1:8790/)。停止后运行 `start-tactics.ps1`。
- Agent 注册 `retrieve_tactic_cards` 工具。网页使用结构化筛选和带中文同义词的 BM25 风格词法排序；没有调用嵌入服务，也没有训练模型。
- 支持地图、攻守、购买类型、存活人数和能配合的人数。人数／道具要求若已标注则可排除不符合项；实际来源卡仍缺这些字段，未知不会当成已满足。
- 复用当前项目模型配置。界面先展示将发送的内容与目的地主机，再由用户点击调用，每次最多一次。模型输出限制为已有条目 ID，拒绝未知引用、重复 ID、额外执行步骤或胜率字段。

## 尚未完成的部分

**20 个是已核验页面元数据的学习卡，不是 20 个已经完整核验的可执行战术。当前正式推荐数量为 0。** 视频步骤、精确道具需求、同步信号、失败分支和当前地图投掷有效性仍待核验。本轮没有给这些缺口填写模型猜测。

抽查了 9z Nuke 视频的 YouTube 页面，标题与原链接对应，界面显示字幕不可用；未完成全片动作或道具核验，也没有把无字幕理解为内容无法人工分析。部分网页介绍指向 2024 年比赛，适用性需复核。

当前网页是资料检索原型，不是完整回合战术推荐器：未接入上传 demo 的自动经济解析、逐人购买方案、对手开局习惯或地图路线校验。购买类型需要手动选择；未知条件不会被模型自动补全。已有 demo、经济和 Agent 基础保留。

## 验证

- 18 项测试通过，覆盖地图／攻守／经济过滤、中文夹击检索、缺失条件、道具不足、非法输入、来源 ID 校验、模拟外部调用以及原 Agent 核心回归。
- Dust2 / T / rifle / A 区夹击的首位结果为 A Split - FaZe。Cache 无资料时返回空结果，不跨地图补凑。
- 浏览器实际检查本地结果、来源链接、待核验说明和发送预览；未点击付费模型调用按钮。
- 外部模型接口以模拟响应和模拟 HTTP 传输验证；本轮没有实际推理调用，尚不能保证当前提供商的在线兼容性。
- HTTP 传输适配器在无工具场景不再发送空 tools 与 tool_choice，相关测试通过。

## 资料清单

| 条目 | 地图 | 攻守 | 经济 | 类型 |
|---|---|---|---|---|
| [T Pistol - Astralis](https://www.cs2.app/tactics-directory/t-pistol---astralis) | de_ancient | T | pistol | execute |
| [A Fake - 9z](https://www.cs2.app/tactics-directory/a-fake---9z) | de_nuke | T | rifle | fake |
| [Delayed A Execute - SAW](https://www.cs2.app/tactics-directory/delayed-a-execute---saw) | de_nuke | T | rifle | execute |
| [T Pistol - Complexity](https://www.cs2.app/tactics-directory/t-pistol---complexity) | de_vertigo | T | pistol | execute |
| [T Pistol - G2](https://www.cs2.app/tactics-directory/t-pistol---g2) | de_dust2 | T | pistol | execute |
| [B Fake to A - MOUZ](https://www.cs2.app/tactics-directory/b-fake-to-a---mouz) | de_mirage | T | rifle | fake |
| [Aggressive Setup - NaVi](https://www.cs2.app/tactics-directory/aggressive-setup---navi) | de_inferno | CT | rifle | setup |
| [CT Pistol - NaVi](https://www.cs2.app/tactics-directory/ct-pistol---navi) | de_inferno | CT | pistol | setup |
| [A Rush - NaVi](https://www.cs2.app/tactics-directory/a-rush---navi) | de_ancient | T | rifle | rush |
| [CT Setup - Falcons](https://www.cs2.app/tactics-directory/ct-setup-falcons) | de_dust2 | CT | rifle | setup |
| [A Split - FaZe](https://www.cs2.app/tactics-directory/a-split---faze-2) | de_dust2 | T | rifle | split |
| [B Explode - Astralis](https://www.cs2.app/tactics-directory/b-explode---astralis) | de_dust2 | T | rifle | explode |
| [Eco Tactic - Liquid](https://www.cs2.app/tactics-directory/eco-tactic---liquid) | de_ancient | T | eco | explode |
| [B Pop - G2](https://www.cs2.app/tactics-directory/b-pop---g2) | de_anubis | T | rifle | explode |
| [A Execute - Sashi](https://www.cs2.app/tactics-directory/a-execute---sashi) | de_vertigo | T | rifle | execute |
| [B Execute - Heroic](https://www.cs2.app/tactics-directory/b-execute---heroic) | de_vertigo | T | rifle | execute |
| [A Pistol - FURIA](https://www.cs2.app/tactics-directory/a-pistol---furia) | de_nuke | T | pistol | execute |
| [CT Force Buy - G2](https://www.cs2.app/tactics-directory/ct-force-buy---g2) | de_inferno | CT | force | setup |
| [A Fake to B - Spirit](https://www.cs2.app/tactics-directory/a-fake-to-b---spirit) | de_nuke | T | rifle | fake |
| [A Explode - FURIA](https://www.cs2.app/tactics-directory/a-explode---furia) | de_mirage | T | rifle | explode |

## 后续核验流程

逐条观看视频并记录时间点、五人分工、最少道具和同步条件；有投掷教程的单独关联到道具卡。先核验少量最常用方案，不以目录数量充当覆盖质量。再补出生位置、枪械和回合阶段验证，当前代码尚未实现这些完整可执行性检查，因此不能仅修改 verification 标志就开放正式推荐。

核验清单见同目录 `战术卡逐条核验清单.md`。事实与推断分开记录；找不到证据就保留未知。今后的推荐仍需要独立人工评估，资料匹配度不能当成采用后的胜率。
