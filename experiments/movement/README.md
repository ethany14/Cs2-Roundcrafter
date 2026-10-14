# 全地图移动预测实验

本实验复用项目现有 demo 解析器和本地 PyTorch，不调用付费模型。

执行顺序（在项目根目录）：

```powershell
.\.venv\Scripts\python.exe experiments/movement/prepare.py
.\.venv\Scripts\python.exe experiments/movement/extract_all.py
.\.venv\Scripts\python.exe experiments/movement/train.py
```

- 原始压缩包只读，SHA-256 去重；所有地图提取到 data/movement/demos。
- 每 0.5 秒提取状态，每 2 秒生成一个样本；过去 2 秒预测未来 0.5、1、2 秒 XY 位移。
- 输入为以当前朝向旋转的自身历史轨迹、俯仰/蹲下/闪光状态、自身血甲、阵营、回合时间、双方存活人数、下包计时及最近两名存活队友的相对位置。没有隐藏敌人坐标，没有玩家身份，没有未来事件或胜负。
- 队友位置与存活计数假定来自游戏队伍雷达/记分板；并未完整模拟个人感知或通讯。
- 当前基线不含地图几何、可达性、导航、道具影响或视线。它只验证跨地图的运动规律，不用于给用户直接判错。
- 一个压缩包对应一场系列赛，全部地图保持在同一划分。按压缩包哈希排序固定划分，训练前保存 protocol.json。
- 以验证集选 checkpoint，三个固定随机种子平均。测试集只用于最终比较，不用测试结果调参。
- 对比不动、匀速、验证集选择衰减系数的匀速模型；报告整体、移动样本、每图、每场结果和以比赛为单位的配对 bootstrap 区间。
- 仅使用整个历史及未来窗口均存活的样本，存在生存者选择偏差；不覆盖被击杀结局。
- 一条真实职业轨迹是行为示例，不是该局势的唯一合理路线，更不是最优解标签。长残局推荐需要另外建模地图、观察、候选动作和结果。

输出：outputs/movement/metrics.json、三个 movement-seed-*.pt、test_predictions.npz、protocol.json 以及 Markdown 报告。
