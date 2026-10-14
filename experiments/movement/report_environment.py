import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/environment'
m=json.loads((OUT/'metrics.json').read_text());schema=json.loads((OUT/'feature-schema.json').read_text());counts=schema['nonzero_counts']
lines=['# 声音、已知敌情与环境证据：小模型对照报告','', '日期：2026-10-13。全部解析、训练和推理在本机完成，没有调用付费模型 API。', '',
'## 结论','',
f"已将 42 项环境字段接入小模型，并把过滤后的证据查询工具注册到 AgentLoop。开枪预测 AP 从 {m['actions']['fire']['joint_baseline']['AP']:.3f} 提升至 {m['actions']['fire']['environment_joint']['AP']:.3f}；移动 ADE 从 {m['ADE']['joint_baseline']:.3f} 增至 {m['ADE']['environment_joint']:.3f}（越小越好），闪光投掷预测退步。不能据此认定整体决策能力改善，也不能把行为预测当成最优解。",'',
'## 游戏文件与 demo 的声音证据','',
'本机游戏包导出的 `game_sounds_footsteps.vsndevts` 中，`Base.Footstep` 的距离音量曲线在 1100 游戏单位处为零，包含 `occlusion_intensity = 0.375`、`use_baked_occlusion = true` 和 `display_broadcast = true`。检查的一场 Dust2 demo 中，`player_sound` 有 17,178 次记录，其中 13,655 次是 `step=true, radius=1100`。因此直接使用实际声音事件及其 radius，比根据玩家速度猜测脚步更可靠。','',
'这仍不等于已还原“玩家一定听见”。尚未逆向确认 HUD 声音圈与混音器的完整关系，也没有复现烘焙声学、曲线切线、混音、耳机设置或背景声音掩蔽。当前输出是声音传播范围候选、八方向粗略方位和静态遮挡标记；遮挡不会简单把声音删除，候选也不会标成确认听见。原始声源坐标仅用于本地重建，不作为敌人精确坐标输出。','',
'枪声从 `weapons.vdata` 对应的普通／消音 soundevent 映射到声音曲线，同时遍历已启用的远距离子事件。共整理 902 个声音节点、61 个武器映射；不是每个节点都保证有完整曲线。缺失映射不产生敌方活动提示，也不把全局未知事件计数输入模型。源文件 SHA-256 保存在 `data/sounds/profiles.json`。','',
'## 已接入的数据和边界','',
'| 项目 | 本次实现 | 剩余限制 |','|---|---|---|',
'| 声音 | 决策前 2 秒实际事件、事件半径／资源曲线、粗方位、静态遮挡 | 每类最多 4 个事件；听者位置最多约 0.5 秒采样误差；不是实际听觉确认 |',
'| 敌人历史 | 仅自身 `approximate_spotted_by` 支持的历史位置、时间与相对位置 | 只有 2 秒历史；点亮标记不等于精确渲染可见；不借隐藏坐标更新 |',
'| 地图与掩体 | 七图静态碰撞、四方向短射线、已知位置射线材料 | 不是导航可行性；碰撞网格不等于视觉不透明网格 |',
'| 烟雾 | 已生效／未过期事件、中心视锥与遮挡筛选、圆柱范围近似；可查真实体素缓存 | 看见中心是保守代理，会漏烟雾边缘；本批体素命中为零 |',
'| 火焰 | 生效和熄灭事件、视锥与静态遮挡筛选 | 未恢复完整燃烧格，未计算火焰伤害 |',
'| 闪光 | 自身 flash duration，生效时附带 max alpha | 最大亮度并非每一帧实际渲染亮度；尚未把受闪与其他观察特征统一重建 |',
'| 材料和伤害 | 材料交点、部分 Dust2 凸体厚度、假设无甲胸部的直射伤害 | 穿墙伤害公式此前验证失败，数值缺失且有效性掩码为零 |','',
'沙二的固定门板已纳入静态遮挡，不将它们视为可开关动态门。Nuke 等地图此次只导入世界静态碰撞，尚未接上逐 tick 动态门变换；所有样本明确标记动态几何未完整重建。其他地图独立静态道具也未保证完整包含。','',
'烟火判断只是候选视线代理，当前没有实现烟雾之间的互相遮挡、闪光后的真实视觉恢复等完整感知机制。不会因此声明已知信息重建完成。','',
'## 数据覆盖','',
'77 个唯一 demo、30 个系列赛、七张地图（Ancient、Anubis、Cache、Dust2、Inferno、Mirage、Nuke）。本轮复用每个 demo 的 64 个固定样本，共 4,928 个，未把全部 537,810 个基础移动窗口重新扩成环境训练样本。按系列赛划分 19／5／6 个训练／验证／测试系列，保持原划分；测试窗口 1,024 个。','',
'| 非零证据 | 窗口数 |','|---|---:|']
for label,key in [('脚步声候选','footstep_candidates'),('枪声候选','gunshot_candidates'),('自身点亮敌人历史','last_seen_valid'),('烟雾视线候选','smoke_in_view'),('火焰视野候选','fire_in_view'),('自身闪光','self_flash_duration'),('真实烟雾体素命中','smoke_voxel_known'),('凸体厚度有效','known_target_thickness_valid'),('条件直射伤害有效','direct_damage_valid'),('穿墙伤害有效','wall_damage_valid')]:lines.append(f'| {label} | {counts[key]} |')
lines+=['','敌人历史只有 67 个窗口，这是交火学习的重要数据瓶颈。体素零命中表示本轮无法验证体素带来的收益，不表示烟雾没有遮挡。厚度只有 4 个窗口且仅局部支持，不能外推到所有掩体。','',
'## 对照实验','',
'两个模型都预测未来 0.5／1／2 秒相对移动，以及开枪和五类道具的首次出手时间段。对照组使用原有移动、武器和自身动作历史；实验组追加当前 42 维环境信息。两组均使用种子 7、17、29，100 轮训练，相同损失和优化器，以验证集移动 ADE 选检查点，报告三个种子集成结果。新增环境维度使输入层参数略有增加，尚未做等参数或逐特征消融，因此不能把收益归因于某一个环境特征。','',
'测试集已在之前的实验中查看过，这是一轮开发集性质的探索对照，不是新的独立验证。动作预测是次要指标，检查点不是按动作 AP 挑选。','',
'| 指标 | 原联合模型 | 加环境信息 |','|---|---:|---:|',f"| 移动 ADE，游戏单位，越低越好 | {m['ADE']['joint_baseline']:.3f} | {m['ADE']['environment_joint']:.3f} |",'',
'| 动作 | 测试正例 | 原 AP | 加环境 AP | 原 Brier | 加环境 Brier |','|---|---:|---:|---:|---:|---:|']
names={'fire':'开枪','smoke':'烟雾弹','flash':'闪光弹','he':'高爆手雷','incendiary':'燃烧弹','decoy':'诱饵弹'}
for name,value in m['actions'].items():
 a,b=value['joint_baseline'],value['environment_joint'];fmt=lambda x:'不支持' if x is None else f'{x:.3f}'
 lines.append(f"| {names[name]} | {a['positive']} | {fmt(a['AP'])} | {fmt(b['AP'])} | {a['Brier']:.5f} | {b['Brier']:.5f} |")
ci=m['paired_series_improvement']['ci95']
lines+=['',f"AP 越大越好，Brier 越小越好；AP 不是准确率。开枪的“重复最近动作”简单基线 AP 为 {m['actions']['fire']['repeat_recent_action']['AP']:.3f}。按六个测试系列配对重采样，移动改善的探索性 95% 区间为 [{ci[0]:.3f}, {ci[1]:.3f}] 游戏单位，跨零。手雷仅 7 个测试正例，不能据其 AP 增幅认定稳定收益；诱饵弹没有训练正例，推理明确返回不支持。",'',
'| 地图 | 原 ADE | 加环境 ADE |','|---|---:|---:|']
for name,val in m['by_map'].items():lines.append(f"| {name} | {val['joint_baseline']:.3f} | {val['environment_joint']:.3f} |")
lines+=['',f"本轮六次本地训练及评估耗时约 {m['seconds']:.1f} 秒，PyTorch 峰值已分配显存约 {m['peak_mb']:.1f} MiB（不含驱动和其他进程），环境构建约 {schema['seconds']:.1f} 秒；这些时间不包含之前的地图导出和 demo 解析。",'',
'## 接口、复现与验证','',
'- `backend/cs2_agent/environment_evidence.py`：过滤并构造环境特征。',
'- AgentLoop 新工具 `inspect_environment_sample(sample_index)`：读取注册样本的过滤证据和限制，不返回全局玩家帧。',
'- `experiments/movement/predict_environment.py`：本地 CPU 加载三个环境模型检查点，输出行为概率；已运行 sample 0，结果在同目录 `prediction-example.json`。',
'- 模型尚未接管网页中的 A/B 决策模拟，也没有部署成实时游戏助手。',
'- 定向测试 25 项通过：包括未来信息隔离、隐藏敌人移动不影响输入、声音边界和子事件、事件失效、固定掩体、工具输入边界、模型维度，以及已有感知／体素／弹道测试。初次 pytest 临时目录不可写，改用项目内新临时目录后通过。','',
'在项目根目录复现：','',
'```powershell',"$env:PYTHONPATH='backend'",'.venv/Scripts/python.exe experiments/movement/extract_environment.py','.venv/Scripts/python.exe experiments/movement/build_environment.py --force','.venv/Scripts/python.exe experiments/movement/train_environment.py','.venv/Scripts/python.exe experiments/movement/predict_environment.py --sample-index 0 --output outputs/movement/environment/prediction-example.json','.venv/Scripts/python.exe experiments/movement/report_environment.py','```','',
'环境重建依赖已导出的地图和 `data/sounds/profiles.json`。`protocol.json` 保存训练约定和特征哈希；`metrics.json`、`feature-schema.json`、六个 `.pt` 文件和 `test-predictions.npz` 保存原始结果。','',
'## 下一步','',
'优先建立交火前后、急停开枪、受声触发、道具出手的事件中心样本，补充没有交火的匹配负例，按系列赛隔离并保留自然比例评估集。将声音和敌情做成逐帧历史，再用消融实验区分哪些证据有效。扩大训练前先建立包含真实体素命中的烟雾测试片段，以及 Nuke 动态门状态测试。穿墙伤害继续使用未知状态，直到针对真实命中日志校准通过。新的比赛留作未查看的独立验证，最后再接网站里的行动建议。','']
(OUT/'声音与环境感知-联合模型验证报告.md').write_text('\n'.join(lines),encoding='utf-8');print('Report saved')
