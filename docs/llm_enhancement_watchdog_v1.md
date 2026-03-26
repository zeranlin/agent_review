# agent_review LLM 增强看门狗 v1

这份说明只约束增强链的外层行为，不改变 `QwenReviewEnhancer` 内部的任务设计。

## 目标

- 避免 enhanced 模式在单次 LLM 调用卡住时阻塞整个命令行流程。
- 即使增强失败，也要保留基础审查结果并继续落盘。
- 让回退原因、耗时和任务轨迹可以在产物里追踪。

## 行为约定

1. CLI 先运行 fast 结果作为基础报告。
2. enhanced 结果在独立的 daemon 线程里执行，并受 `--llm-timeout` 约束。
3. 超时或异常时，最终结果回退到基础报告，但会补写 `llm_warnings` 和 `llm_enhancement_watchdog` stage 记录。
4. 报告正文会显式显示增强链状态。

## 产物

- `base_report.json` / `base_report.md`
- `enhanced_report.json` / `enhanced_report.md`
- `enhancement_trace.json`
- `evaluation_summary.json`
- `llm_tasks.json`
- `review_point_trace.json`
- `run_manifest.json`

## trace 重点字段

- `requested_mode`
- `base_mode`
- `final_mode`
- `outcome`
- `timeout_seconds`
- `elapsed_seconds`
- `fallback_applied`
- `llm_warnings`

## 评测闭环

`evaluation_summary.json` 用来做最小的增强闭环对比，优先看这几类字段：

- `prompt_volume.task_char_counts`
- `task_duration.task_seconds`
- `dynamic_task_counts`
- `quality_gates.status_counts`
