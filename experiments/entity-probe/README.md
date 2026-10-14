# 网络实体实验

仅解析本地 demo，不连接模型服务、不修改游戏。需要项目 `work/dotnet` 中的便携 .NET 9 SDK，以及 `work/demofile-net` 源码。

解析器固定提交：`fd59701a998cf30a46adc4942e063d90de73c07a`，MIT，许可证见 `docs/third-party/demofile-net-LICENSE.txt`。构建需要完整 Git 历史，源码依赖 Git 版本号生成。

```powershell
$env:DOTNET_CLI_HOME = "$PWD/work/dotnet-home"
$env:NUGET_PACKAGES = "$PWD/work/nuget"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
./work/dotnet/dotnet.exe build experiments/entity-probe -c Release
./work/dotnet/dotnet.exe experiments/entity-probe/bin/Release/net9.0/EntityProbe.dll data/demos/mouz-vs-spirit-m1-dust2.dem outputs/casebook/mouz-vs-spirit-m1-dust2-entities.jsonl
./.venv/Scripts/python.exe -m cs2_agent.smoke_voxels data/demos/mouz-vs-spirit-m1-dust2.dem outputs/casebook/mouz-vs-spirit-m1-dust2-entities.jsonl
./.venv/Scripts/python.exe -m cs2_agent.perception
./.venv/Scripts/python.exe -m cs2_agent.review --match 2398755 --offline
```

原始 JSONL 保存网络数组和实体序列号，较大；SQLite 只保存有效前缀并压缩。体素格式参照 demolens v2.5.0 的 `internal/parser/smokevoxel.go`，MIT。原仓库下载时返回 404，使用公开 Go 模块代理已发布版本：`https://proxy.golang.org/github.com/f-gillmann/demolens/v2/@v/v2.5.0.zip`。原始源码保留在 `work/demolens`，许可证见 `docs/third-party/demolens-LICENSE.txt`。

按 demo tick 选择已发生的数据，服务器烟雾起始 tick 不能直接代替 demo tick。解码依据是累计 chunk、种子、Morton 掩码；12 单位体素尺度及内部填充源于社区推断，尚无本项目的画面对照校准。不能把网格相交等同于玩家实际看不见，也不能在相位切换时直接认定烟雾透明。

动态门保存实体序列号、关闭/打开中/打开/关闭中状态、位置和角度，以及删除事件。`door_timeline.at_tick` 只读取查询时刻以前的状态；删除不等于确定被打碎。`posed_mesh` 支持完整门模型的 yaw 旋转，破损门板尚未重建。
