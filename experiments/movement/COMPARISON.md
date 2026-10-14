# 三组对照实验复现

在 `C:/Users/zhiyu/Documents/Cs2-agent` 执行。所有输出保存在本项目。

## 数据和协议

```powershell
.\.venv\Scripts\python.exe experiments/movement/prepare.py
.\.venv\Scripts\python.exe experiments/movement/extract_all.py
.\.venv\Scripts\python.exe experiments/movement/prepare_comparison.py
```

最后一步固定抽样与按系列赛划分，不要在看到测试结果后重新挑选划分。此次配置需要当前 77 份 demo，新增数据应另建版本。每张地图均进入三个划分，每场系列赛不会拆分。

## 冻结模型特征

复用既有 ManifoldLLm 的只读 Qwen3-4B 缓存及其已安装的 Transformers 运行环境。实验脚本、数据、特征和训练产物全部位于 Cs2-agent；没有导入另一个项目的业务代码，也不读任何 API 密钥。

```powershell
& 'C:/Users/zhiyu/Documents/ManifoldLLm/.venv/Scripts/python.exe' experiments/movement/embed_qwen.py
```

模型加载使用固定本地 snapshot、`local_files_only=True`、`trust_remote_code=False`，同时启用离线环境变量。模型冻结，BF16 前向、FP32 池化。每 128 个样本显示进度；缓存完成后写入 qwen-metadata.json。不要在同一缓存目录并发执行多个提取任务。

## 训练、验证和报告

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_movement_experiment.py tests/test_movement_comparison.py -q
.\.venv\Scripts\python.exe experiments/movement/compare.py
.\.venv\Scripts\python.exe experiments/movement/report_comparison.py
```

冻结特征一致性以 prompt 哈希检查；标准化仅拟合训练样本。三组使用相同训练样本、loss、随机种子、epoch 上限、验证规则。参数量不完全相同，必须在解释中保留这一限制。

完整的 537810 个合格窗口保存在 `data/movement/samples/`。此次对照使用所有 77 份 demo 抽取的 4928 个窗口，不等于全量窗口训练。测试分数生成后，该测试集即成为已查看数据；后续调参必须在新比赛上做确认验证。

当前脚本只用于离线实验，没有接入现有网站自动决策。
