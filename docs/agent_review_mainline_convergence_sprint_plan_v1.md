# agent_review 主链收敛开发任务清单 v1

这份清单基于《agent_review 主链收敛重构方案 v1》，目标是把现有可运行但偏重的主链，逐步收敛成：

`Parser -> Fact -> Planning -> Rule -> Adjudication -> Output`

## Sprint 1：主链边界收口

### 目标

- 先把阶段边界写实，避免继续在多层重复判断。

### 任务包

1. 数据流映射收口
- 梳理当前 `pipeline.py / engine.py` 中各阶段输入输出。
- 明确每层唯一主对象：
  - Parser: `ClauseUnit`
  - Fact: `LegalFactCandidate`
  - Planning: `ReviewPlanningContract`
  - Rule: `RuleHit / ReviewPointInstance`
  - Adjudication: `FormalAdjudication`
- 产出主链阶段 trace 字段对照表。

2. `review_point_catalog` 角色降权
- 区分“注册表职责”和“裁判职责”。
- 将 catalog 侧的任务激活说明沉淀为元数据，不再继续堆业务判断。

3. `risk hit / consistency` 用途收口
- 明确它们仅作为：
  - fallback
  - trace
  - 调试
- 不再让其直接主导正式输出。

### 验收标准

- 主链阶段对象一一对应。
- 新文档与实际代码职责基本一致。
- 后续开发不再新增跨层重复判断。

## Sprint 2：Fact 主线强化

### 目标

- 把 `ClauseUnit -> LegalFactCandidate` 变成真正主中轴。

### 任务包

1. `ClauseUnit` 语义增强
- 扩展 `conditional_context / legal_effect / role / rebuttal markers / project-binding markers`。
- 继续补：
  - 条件政策
  - 反证
  - 模板残留
  - 附件依赖

2. `LegalFactCandidate` 标准化
- 明确：
  - `fact_type`
  - `effect_scope`
  - `binding_strength`
  - `rebuttal_strength`
  - `project_binding`
  - `source_zone`
- 让高频审查点优先消费 `LegalFactCandidate`。

3. `ExtractedClause` 退成投影视图
- 对能由 `LegalFactCandidate` 直接表达的字段，减少重复推断。
- 保留它作为：
  - 报表字段
  - 兼容接口
  - 定向抽取视图

### 验收标准

- 高频中小企业、资格门槛、合同风险点优先走 `LegalFactCandidate`。
- `ExtractedClause` 不再承担过多规则本体语义。

## Sprint 3：Rule 主线强化

### 目标

- 让 `RuleHit / ReviewPointInstance` 成为正式裁判入口。

### 任务包

1. 高频规则迁移
- 将高频正式风险点迁入 `RuleDefinition`：
  - 资格门槛簇
  - 证明来源限制
  - 评分错配
  - 质量保证金/检测费用/最低报价门槛
  - 中小企业政策冲突

2. `RuleHit -> ReviewPointInstance` 聚合标准化
- 统一：
  - 同母题聚类
  - 同证据去重
  - 资格/评分跨段对齐
  - 反证优先级

3. `AuthorityBinding` 前置
- 在 Rule 阶段就绑定法条与法理母题。
- Formal 层不再承担大部分“找依据”工作。

### 验收标准

- 核心高频点能够由 `ReviewPointInstance` 直接驱动正式问题输出。
- `risk hit` 的正式裁判地位明显下降。

## Sprint 4：Adjudication 收窄

### 目标

- 让 adjudication 只负责适用性、证据质量和正式 disposition。

### 任务包

1. Applicability 收敛
- 只判断：
  - 适用前提是否成立
  - 是否存在反证
  - 是否完成项目事实绑定
- 不再重复定义业务规则本体。

2. Quality Gate 收窄
- 只保留：
  - 模板污染过滤
  - 弱来源压制
  - 重复实例合并
  - 明显错区纠偏

3. Formal Adjudication 规范化
- 统一 disposition 生成来源：
  - include
  - manual_confirmation
  - filtered_out
- 让 `manual_confirmation` 与 `filtered_out` 的边界可测试、可解释。

### 验收标准

- formal 不再承担“第二规则引擎”职责。
- 同一问题不会在 formal 阶段重新发明业务条件。

## Sprint 5：Output / Eval 去策略化

### 目标

- 让输出层只消费正式裁判结果。

### 任务包

1. 报告层去业务策略
- `reporting.py` 不再隐含业务判断。
- 报告只展示：
  - 正式问题
  - 证据
  - 法律依据
  - trace 摘要

2. trace / regression 分层化
- 增加分层指标：
  - parser 漂移
  - fact 漂移
  - rule 漂移
  - adjudication 漂移

3. 样本回归拆层
- 除最终报告对比外，增加：
  - `ClauseUnit diff`
  - `LegalFactCandidate diff`
  - `RuleHit diff`
  - `Formal diff`

### 验收标准

- 报告层基本不做策略性压制。
- 回归能定位问题漂移发生在哪一层。

## 推荐开发顺序

1. 先做 Sprint 1
- 原因：先把边界写清楚，否则每一层都会继续长逻辑。

2. 再做 Sprint 2
- 原因：Fact 层不稳，Rule 层无法真正统一。

3. 接着做 Sprint 3
- 原因：让高频点真正进入新链。

4. 然后做 Sprint 4
- 原因：等 Rule 主线稳了，再把 formal 收窄。

5. 最后做 Sprint 5
- 原因：输出和评测应建立在稳定主链上。

## 建议的并行开发分工

### A 线：Parser / Fact

- `ClauseUnit`
- `LegalFactCandidate`
- `ExtractedClause` 投影收敛

### B 线：Rule / Authority

- `RuleDefinition`
- `AuthorityBinding`
- `RuleHit / ReviewPointInstance`

### C 线：Adjudication

- `Applicability`
- `QualityGate`
- `FormalAdjudication`

### D 线：Output / Eval

- `reporting`
- `artifacts`
- `trace`
- `regression`

## 当前建议的直接开工点

如果现在进入开发，最顺的起点是：

1. Sprint 1
- 先把 `pipeline / engine / review_point_catalog / rule_runtime / reporting` 的边界收口。

2. Sprint 2 的一部分
- 继续把 `ClauseUnit -> LegalFactCandidate` 主线做厚。

这两步完成后，再进入 Sprint 3 会更稳，因为那时规则就能真正以“法律事实”为输入，而不是继续混用文本片段、结构字段和旧 catalog 逻辑。
