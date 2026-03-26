# 未知品目真实样本回归入口

## 目标

这个入口用于在本地隔离环境里批量跑一组未知品目真实文件，输出最小但可持续回归的摘要：

- 文档画像
- 领域 profile 候选
- quality gate 摘要
- formal 候选摘要

它的设计目标是轻量、可执行，并且不会污染默认全量单测。

## 入口

建议直接运行：

```bash
PYTHONPATH=src python tests/run_unknown_sample_regression.py --manifest /path/to/manifest.txt --output-dir runs/unknown_sample_regression
```

也可以直接传文件路径：

```bash
PYTHONPATH=src python tests/run_unknown_sample_regression.py \
  /path/to/a.docx \
  /path/to/b.pdf \
  --output-dir runs/unknown_sample_regression
```

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

## 行为约束

1. 默认运行模式是 `fast`，适合先批量扫样本。
2. 入口会对每个文件单独处理，不把样本互相合并。
3. formal 摘要采用 best-effort 策略，若现有主流程在 formal 阶段报错，入口会保留错误信息并继续输出前置摘要。
4. 这个入口不属于默认单测主链，不会自动参与日常 `pytest`。

## 回归建议

建议优先把以下文件放进 manifest：

- 从未见过的新品目样本
- 家具类真实文件
- 结构复杂、模板污染重、评分表多的文件
- 需要观察画像候选是否漂移的边界样本
