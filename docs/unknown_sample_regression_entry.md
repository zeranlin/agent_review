# 未知品目真实样本回归入口

## 目标

这个入口用于在本地隔离环境里批量跑一组未知品目真实文件，输出最小但可持续回归的摘要：

- 文档画像
- 领域 profile 候选
- quality gate 摘要
- formal 候选摘要
- 评测闭环摘要：输入复杂度、review point 数量、quality gate 状态和 formal 结果

它的设计目标是轻量、可执行，并且不会污染默认全量单测。

## 入口

建议直接运行：

```bash
python tests/run_unknown_sample_regression.py --manifest /path/to/manifest.txt --output-dir runs/unknown_sample_regression
```

也可以直接传文件路径：

```bash
python tests/run_unknown_sample_regression.py \
  /path/to/a.docx \
  /path/to/b.pdf \
  --output-dir runs/unknown_sample_regression
```

## baseline manifest 机制

建议把 8 到 12 个真实样本整理成一个 baseline manifest，形成固定回归集。

可以先参考：

- [docs/unknown_sample_regression_manifest_example.txt](/Users/linzeran/code/2026-zn/agent_review/docs/unknown_sample_regression_manifest_example.txt)

常用命令：

```bash
python tests/run_unknown_sample_regression.py \
  --manifest /path/to/baseline_manifest.txt \
  --output-dir runs/unknown_sample_regression \
  --emit-manifest
```

`--emit-manifest` 会在输出目录中写出规范化的：

- `baseline_manifest.txt`
- `baseline_manifest.json`

它们会按绝对路径去重并排序，便于后续做稳定回归对比。

## manifest 格式

一行一个文件路径，支持注释：

```text
# 家具专项真实样本
/Users/linzeran/code/2026-zn/test_target/sz-q/深圳10个品目批注文件/家具/东北师范大学附属中学深圳学校家具采购.docx
/Users/linzeran/code/2026-zn/test_target/sz-q/深圳10个品目批注文件/家具/另一个样本.docx
```

## 输出

默认会写出：

- `batch_summary.json`
- `batch_summary.md`
- `files/<序号>_<文件名>.json`

其中 `batch_summary.json` 还包含每个样本的 `evaluation_summary`，便于快速对比：

- 输入字符数和 clause 规模
- review point 数量
- quality gate 状态分布
- formal 纳入数量

仓库内置了一份 baseline manifest：

- [unknown_sample_regression_manifest_v1.txt](/Users/linzeran/code/2026-zn/agent_review/docs/unknown_sample_regression_manifest_v1.txt)

可直接运行：

```bash
PYTHONPATH=src python tests/run_unknown_sample_regression.py \
  --manifest docs/unknown_sample_regression_manifest_v1.txt \
  --output-dir runs/unknown_sample_regression_baseline_v1
```

## 最小基线治理

这个回归线只保留最小治理面，避免把 unknown 样本回归做成一条新的重业务主链：

- `docs/unknown_sample_regression_manifest_v1.txt` 负责冻结输入集合，变更时先说明原因再更新文件。
- `batch_summary.json` 是主要对比对象，优先看 `input_count`、`succeeded_count`、`failed_count` 和 `aggregate`。
- `evaluation_summary` 是辅助对比对象，优先看 `input_chars`、`review_point_count` 和 `quality_gate_status_counts`。
- `files/*.json` 只作为单文件调试视图，用来定位某个样本的画像、领域候选、quality gate 和 formal 摘要是否漂移。
- manifest、batch summary 和 files 输出都已经做了规范化排序，便于直接做 baseline diff。

## 行为约束

1. 默认运行模式是 `fast`，适合先批量扫样本。
2. 入口会对每个文件单独处理，不把样本互相合并。
3. formal 摘要采用 best-effort 策略，若现有主流程在 formal 阶段报错，入口会保留错误信息并继续输出前置摘要。
4. 这个入口不属于默认单测主链，不会自动参与日常 `pytest`。
5. manifest 和输出摘要都采用规范化排序，方便做 baseline diff。

## 回归建议

建议优先把以下文件放进 manifest：

- 从未见过的新品目样本
- 家具类真实文件
- 结构复杂、模板污染重、评分表多的文件
- 需要观察画像候选是否漂移的边界样本
- 凑齐 8 到 12 个文件，尽量覆盖货物、服务、混合和家具四类画像
