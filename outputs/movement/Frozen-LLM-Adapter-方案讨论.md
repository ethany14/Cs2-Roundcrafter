# Frozen LLM + Adapter：CS2 实验路线讨论

日期：2026-10-13。状态：方案讨论；尚未启动模型训练，也没有验证结果。

## 参考实现核对

已读取用户引用的 Create personality manifold PDF 对话，并核对本机 ManifoldLLm/Ethan/affective_adapter/model.py 和 REPRODUCIBILITY.md。
其早期实现是：文本 → 冻结 Qwen3-4B → 最后一层 masked-mean embedding → 独立 MLP adapter → 低维表示和辅助预测头。冻结模型输出可缓存，训练只更新后面的 MLP。它不是在 LLM 内部插入 LoRA，也没有改变 LLM 的生成能力。该项目后来的问卷流形实验是另一条路线，不能将其结果当成 frozen LLM 方法已验证的证据。

## CS2 可行方案

在严格限定玩家已知信息后，将局势分成两支：

1. 结构化数字分支：过去移动、视角、队友相对位置、血甲、计时等，由小型时序编码器处理。
2. 语义分支：将同一时刻可知的局势转换成固定模板文本，由冻结本地 LLM 提取并缓存 embedding。

拼接两支表示后，训练小型 adapter 和预测头。第一阶段目标是职业选手后续移动/行为预测，而不是将职业行为直接标注为最优。

廉价验证采用同一比赛划分的三组比较：数字分支；冻结 LLM embedding + adapter；两者融合。严格使用同样的目标、信息范围和训练样本，验证集决定配置，最终测试集仅使用一次。大模型不优于数字分支时，应报告无增益，而不是仅凭结构复杂就采用它。

## 边界与成本

- 冻结主干会降低训练参数和优化器开销，但仍需支付大模型前向推理时间；缓存特征后才可以低成本反复训练 adapter。
- 若 adapter 位于输入端并需要梯度穿过冻结 LLM，仍有主干反向传播的计算与激活开销，不能等同于缓存输出的方案。
- 普通商用聊天 API 通常不开放 hidden states 或模型内部梯度接口；可调用其输出当特征，但不等价于本地 frozen LLM + adapter。
- 用户本机之前有 Qwen3-4B 工作流，可优先核对并复用本地模型缓存；具体运行精度、显存和时间必须实测，尚未执行。
- LLM 的文字能力不能替代地图拓扑、遮挡、道具与可达性。把大量坐标转成文字也不保证获得空间理解。
- 当前提取器只包含运动和基础局势，未包含完整地图几何。后续决策模型需要扩充证据输入。

## 当前 CS2 工作状态

31 个 RAR 经内容去重后为 30 个系列赛、77 份独立 demo。原始压缩包未改动。第一次提取任务处理了当时已经解压好的 61 份 demo；余下 16 份仍需补提取。模型训练没有启动。现有数据准备与训练脚本已保存，可用于后续对照实验。

## 研究依据

- Time-LLM 展示了冻结语言模型与可训练输入/输出映射用于时间序列预测的可行性；不是 CS2 效果证明：https://proceedings.iclr.cc/paper_files/paper/2024/hash/680b2a8135b9c71278a09cafb605869e-Abstract-Conference.html
- Are Language Models Actually Useful for Time Series Forecasting? 对所研究方法的消融发现，移除 LLM 或替换成简单模块可以不降低甚至提升效果，说明需要匹配对照：https://proceedings.neurips.cc/paper_files/paper/2024/hash/6ed5bf446f59e2c6646d23058c86424b-Abstract-Conference.html
