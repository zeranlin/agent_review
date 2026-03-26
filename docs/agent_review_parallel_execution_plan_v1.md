# Sprint 并行推进任务编排表 v1

这份编排表用于统筹 Sprint 1 到 Sprint 5 的并行开发。原则不是“五个 Sprint 同时平推”，而是“分波次并行、主链串行”。

## 总体原则

1. `Sprint 1` 是所有主线的上游，必须先稳定契约和术语。
2. `Sprint 2` 与 `Sprint 3` 可以在 `Sprint 1` 初稿稳定后并行推进。
3. `Sprint 4` 必须建立在 `Sprint 2 + Sprint 3` 的稳定输出之上。
4. `Sprint 5` 可提前建设基建，但主闭环应放在 `Sprint 4` 后收口。
5. 每条子线都必须明确写入边界，避免多个 agent 改同一批核心文件。

## 波次划分

### 第 1 波：基础语义与契约

- 主目标：把术语、契约、头部信息、主线阶段接口固定下来。
- 对应 Sprint：`Sprint 1`
- 可并行副线：`Sprint 3 预研`

### 第 2 波：解析与任务库并行

- 主目标：同时推进 parser 语义层和审查点任务库。
- 对应 Sprint：`Sprint 2 + Sprint 3`
- 可并行副线：`Sprint 5 基建`

### 第 3 波：主链编排与正式裁决

- 主目标：把 planning、applicability、quality gate、formal adjudication 收拢成稳定主链。
- 对应 Sprint：`Sprint 4`

### 第 4 波：增强与评测闭环

- 主目标：收窄 LLM 上下文、强化二审、固化 regression baseline。
- 对应 Sprint：`Sprint 5`

## 子 agent 任务归属

### 主线 A：ontology-contract

- 负责 Sprint：`Sprint 1`
- 任务：
- 轻量本体 v2 术语收口
- 数据契约稳定化
- HeaderInfo 扩展契约
- 推荐写入范围：
- `docs/ontology_v1.md`
- `docs/agent_review_next_stage_architecture_v1.md`
- `src/agent_review/models.py`
- `src/agent_review/header_info.py`

### 主线 B：parser-semantic

- 负责 Sprint：`Sprint 2`
- 任务：
- document tree
- zone classification
- ClauseUnit
- effect tagging
- anchor normalization
- 推荐写入范围：
- `src/agent_review/structure/`
- `src/agent_review/parsers/`
- `src/agent_review/extractors/`
- `tests/*parser*`

### 主线 C：review-task-library

- 负责 Sprint：`Sprint 3`
- 任务：
- 70+ 审查点重组
- 风险母题层
- 审查点元数据
- DomainProfile / Lexicon / EvidencePattern
- 推荐写入范围：
- `src/agent_review/review_point_catalog.py`
- `src/agent_review/domain_profiles.py`
- `docs/review_point_catalog.md`
- `docs/document_profile_domain_profile_v1.md`

### 主线 D：planning-adjudication

- 负责 Sprint：`Sprint 4`
- 任务：
- review planning 正式主链化
- extraction demands 分层
- applicability / quality gate / formal adjudication 收口
- 推荐写入范围：
- `src/agent_review/pipeline.py`
- `src/agent_review/applicability.py`
- `src/agent_review/review_quality_gate.py`
- `src/agent_review/adjudication.py`

### 主线 E：llm-eval

- 负责 Sprint：`Sprint 5`
- 任务：
- LLM 高价值字段链路
- 二审纠偏
- artifact / trace / regression
- baseline manifest
- 推荐写入范围：
- `src/agent_review/llm/`
- `src/agent_review/outputs/`
- `src/agent_review/eval/`
- `docs/llm_enhancement_watchdog_v1.md`
- `docs/unknown_sample_regression_entry.md`

## 当前建议分发

1. `domain_profile_mainline_v1`
- 负责：`Sprint 3` 中的 `DomainProfile / Lexicon / EvidencePattern`

2. `sprint2_document_profile_v2`
- 负责：`Sprint 2` 中的 document tree / zone classification / ClauseUnit 主线

3. `sprint2_domain_profile_v2`
- 负责：`Sprint 3` 中的风险母题层与审查点路由元数据

4. `sprint2_profile_routing`
- 负责：`Sprint 4` 前置接口，梳理 `DocumentProfile -> ReviewPlanningContract -> extraction demands`

5. `sprint3_quality_gate_v2`
- 负责：`Sprint 4` 中的 quality gate / formal adjudication 收口

6. `llm_output_eval_mainline_v1`
- 负责：`Sprint 5` 中的 LLM trace / regression / baseline 指标闭环

## 主线程职责

- 维护统一任务编排表
- 处理跨主线接口整合
- 审核子 agent 写入边界冲突
- 负责最终测试、回归、commit、push

## 当前执行策略

1. 主线程先维护架构事实源和编排表。
2. 子 agent 并行推进各自主线，不共享写入文件。
3. 每轮先合并 `Sprint 1/2/3` 的基础产出，再进入 `Sprint 4`。
4. `Sprint 5` 基建可提前，但基于主链稳定结果再做最终收口。
