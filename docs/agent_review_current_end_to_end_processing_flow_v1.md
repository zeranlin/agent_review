# 《agent_review 当前完整处理过程 v1》

## 1. 目标

本文件用于记录 `agent_review` 当前版本在收到一份招标文件后的完整处理过程。

目标是回答以下问题：

1. 输入是什么
2. 系统收到文件后依次做了什么
3. 每一阶段的输入、处理、输出是什么
4. 哪些环节主要靠规则
5. 哪些环节会调用 LLM
6. 最终会输出什么产物

本文件作为当前系统“端到端主链行为说明”的基线文档。

---

## 2. 总体概览

当前主链可以概括为：

`文件输入 -> parser结构化 -> document profile画像 -> review planning激活 -> clause/fact/rule主链 -> applicability/quality/formal -> 报告输出 -> trace/eval落盘`

更细一点可以写成：

`input -> load_document -> document_tree -> zone/effect/clause_unit -> parser_llm_assist -> document_profile -> review_planning -> extracted_clause -> legal_fact_candidate -> rule_hit -> review_point_instance -> applicability_check -> quality_gate -> formal_adjudication -> reporting -> artifacts`

---

## 3. 阶段拆解

## 3.1 输入阶段

### 输入

- 单份招标文件
- 或多份联合审查文件

支持类型包括：

- `docx`
- `pdf`
- `txt`
- `md`

### 入口

- CLI
- Web 上传

### 处理内容

- 确认文件路径
- 判断文件类型
- 调用对应 parser

### 输出

- 原始 `ParseResult`

### 主导方式

- 规则/代码主导
- 不依赖 LLM

---

## 3.2 文档解析阶段

### 输入

- 原始文件

### 处理内容

- `docx/pdf/text parser` 提取文本
- 提取原始 block
- 提取原始表格
- 生成锚点信息

### 输出

- `text`
- `raw_blocks`
- `raw_tables`
- `ParseResult`

### 主导方式

- 规则/解析器主导
- 不依赖 LLM

---

## 3.3 文档树构建阶段

### 输入

- `raw_blocks`
- `raw_tables`

### 处理内容

- 构建 `DocumentNode` 树
- 识别章节
- 识别段落
- 识别表格与表格行
- 识别标题层级
- 识别目录和导航结构

### 输出

- `document_nodes`

### 主导方式

- 规则/结构识别主导
- 不依赖 LLM

---

## 3.4 主区块 zone 分类阶段

### 输入

- `document_nodes`

### 处理内容

为每个节点识别主区块 `zone_type`。

当前主区块包括：

1. `administrative_info`
2. `qualification`
3. `conformity_review`
4. `technical`
5. `business`
6. `scoring`
7. `contract`
8. `policy_explanation`
9. `template`
10. `appendix_reference`
11. `catalog_or_navigation`
12. `public_copy_or_noise`
13. `mixed_or_uncertain`

### 输出

- `semantic_zones`

### 主导方式

- 规则主导
- 标题词、路径词、表格语境、上下文继承
- 默认不依赖 LLM

---

## 3.5 效力标签 effect tagging 阶段

### 输入

- `document_nodes`
- `semantic_zones`

### 处理内容

判断每个节点的效力标签：

- `binding`
- `template`
- `example`
- `optional`
- `reference_only`
- `policy_background`
- `catalog`
- `public_copy_noise`

### 输出

- `effect_tag_results`

### 主导方式

- 规则主导
- 不依赖 LLM

---

## 3.6 ClauseUnit 构建阶段

### 输入

- `document_nodes`
- `semantic_zones`
- `effect_tag_results`

### 处理内容

把可供审查消费的最小单元统一成 `ClauseUnit`。

每个 `ClauseUnit` 目前会带：

- `zone_type`
- `clause_semantic_type`
- `effect_tags`
- `legal_effect_type`
- `anchor`
- `path`

当前条款语义包括：

- `administrative_clause`
- `qualification_condition`
- `qualification_material_requirement`
- `qualification_review_clause`
- `conformity_review_clause`
- `preliminary_review_clause`
- `invalid_bid_clause`
- `technical_requirement`
- `business_requirement`
- `sample_or_demo_requirement`
- `scoring_rule`
- `scoring_factor`
- `contract_obligation`
- `payment_term`
- `acceptance_term`
- `breach_term`
- `termination_term`
- `policy_clause`
- `conditional_policy`
- `template_instruction`
- `declaration_template`
- `example_clause`
- `reference_clause`
- `catalog_clause`
- `noise_clause`
- `unknown_clause`

### 输出

- `clause_units`

### 主导方式

- 规则主导
- 依赖 parser ontology
- 默认不依赖 LLM

---

## 3.7 Parser LLM Assist 阶段

### 输入

- `ParseResult`
- `DocumentProfile` 预画像

### 处理内容

只对低置信和冲突节点做小范围歧义消解，例如：

- `mixed_or_uncertain`
- zone 冲突
- clause semantic 冲突

### 输出

- 更新后的 `ParseResult`
- `parser_semantic_trace`

### 主导方式

- LLM 辅助
- 但仅为低置信补偿
- 不是 parser 主链主体

### 当前设计原则

- parser 主体不能依赖 LLM
- 最优方案是：
  - `规则主链 + profile路由 + LLM小范围补偿`

---

## 3.8 Document Profile 画像阶段

### 输入

- `ParseResult`

### 处理内容

生成 `DocumentProfile`，包括：

- 采购类型画像
- dominant zones
- clause semantic 分布
- 模板污染和未知结构标记
- routing mode
- representative anchors

### 输出

- `document_profile`

### 主导方式

- 规则统计主导
- 不依赖 LLM

---

## 3.9 Review Planning 阶段

### 输入

- `DocumentProfile`
- `ClauseUnit`
- parser 结构信号

### 处理内容

激活本次文件应跑的审查任务族，并生成：

- `ReviewPlanningContract`
- `extraction_demands`

例如会激活：

- 资格门槛审查
- 符合性/无效投标边界审查
- 技术限制性审查
- 评分相关性与量化性审查
- 合同风险审查
- 中小企业政策审查

### 输出

- `review_planning_contract`

### 主导方式

- 规则路由主导
- 不是 LLM 主导

---

## 3.10 Clause Extraction 阶段

### 输入

- `ClauseUnit`
- `review_planning_contract`

### 处理内容

把 `ClauseUnit` 归一成后续规则和报告更方便消费的 `ExtractedClause`。

当前已切到：

- `ClauseUnit 优先`
- 文本 fallback 仅补缺失字段

### 输出

- `extracted_clauses`

### 主导方式

- 规则主导
- 不依赖 LLM

---

## 3.11 LegalFactCandidate 阶段

### 输入

- `ClauseUnit`
- `ExtractedClause`

### 处理内容

把条款转成“可审查的法律事实候选”，例如：

- 资格门槛
- 指定检测机构
- 指定证明来源
- 技术参数约束
- 履约保证金
- 投标无效后果
- 政策适用口径

### 输出

- `legal_fact_candidates`

### 主导方式

- 规则主导
- 不依赖 LLM

---

## 3.12 RuleHit 阶段

### 输入

- `LegalFactCandidate`
- `RuleDefinition`
- `AuthorityBinding`

### 处理内容

对法律事实运行规则，生成：

- 命中的规则
- 命中的原因
- 对应法条/依据绑定

### 输出

- `rule_hits`

### 主导方式

- 规则引擎主导
- 不依赖 LLM

---

## 3.13 ReviewPointInstance 阶段

### 输入

- `rule_hits`
- `ReviewPointContract`

### 处理内容

把规则命中聚合成正式的“审查点实例”。

### 输出

- `review_point_instances`

### 主导方式

- 规则聚合主导
- 不依赖 LLM

---

## 3.14 Applicability Check 阶段

### 输入

- `review_point_instances`
- `extracted_clauses`
- `facts`

### 处理内容

检查：

- 本审查点在本文件中是否适用
- 要件链是否完整
- 证据是否足够

### 输出

- `applicability_checks`

### 主导方式

- 规则主导

---

## 3.15 Quality Gate 阶段

### 输入

- `review_points`
- `extracted_clauses`
- `effect_tags`

### 处理内容

过滤或降级：

- 模板误报
- 附件引用误报
- 噪声误报
- 弱证据误报
- 重复问题

### 输出

- `quality_gates`

### 主导方式

- 规则主导

---

## 3.16 Formal Adjudication 阶段

### 输入

- `review_points`
- `applicability_checks`
- `quality_gates`
- `evidence`

### 处理内容

形成正式裁决，决定：

- 是否纳入正式报告
- 如何定性

当前要求区分：

- `confirmed_issue`
- `warning`
- `missing_evidence`
- `manual_review_required`

### 输出

- `formal_adjudication`

### 主导方式

- 规则与证据门控主导
- 不是 LLM 主裁判

---

## 3.17 Enhanced LLM 阶段

### 输入

- 基础报告
- enhancement 任务

### 处理内容

如果使用 `enhanced` 模式，则：

- 先落基础报告
- 再调用本地 LLM 做增强
- 超时或失败则回退基础报告

增强主要用于：

- 风险说明润色
- 修改建议补强
- 局部语义补充

### 输出

- `enhanced_report`
- `enhancement_trace`

### 主导方式

- LLM 增强
- 不是基础审查主链

---

## 3.18 Reporting 与 Artifacts 阶段

### 输入

- 基础报告
- formal adjudication
- enhanced 结果

### 处理内容

渲染多种输出，并将运行痕迹落盘。

### 输出

用户可读输出：

- `reviewer_report.md`
- `formal_review_opinion.md`
- `opinion_letter.md`
- `base_report.md/json`
- `enhanced_report.md/json`

trace 与运行产物：

- `run_manifest.json`
- `review_point_trace.json`
- `enhancement_trace.json`
- `llm_tasks.json`
- `pending_confirmation_items.json`
- 若干专项表

默认落盘位置：

- `runs/<文件名>/`

### 主导方式

- 规则/模板渲染主导

---

## 4. 规则与 LLM 的分工

## 4.1 规则/硬编码主导环节

- 文件解析
- 文档树构建
- zone 分类
- effect tagging
- ClauseUnit 构建
- clause extraction
- legal fact 抽取
- rule hit
- review point instance
- applicability
- quality gate
- formal adjudication
- 基础报告生成

## 4.2 LLM 参与环节

- parser 低置信歧义消解
- enhanced 模式下的增强说明与补充

## 4.3 当前总体模式

当前系统不是：

- 全规则
- 也不是全 LLM

而是：

- `规则主链 + parser ontology + review point/rule/authority 主链`
- `LLM 作为低置信补偿和增强层`

---

## 5. 一句话总结

当前 `agent_review` 收到一份招标文件后，会先把文件解析成结构化文档树和条款单元，再基于 parser ontology 和规则主链生成法律事实、规则命中和审查点实例，经过适用性检查、质量门控与正式裁决后输出报告；LLM 只在低置信 parser 消解和 enhanced 增强阶段小范围参与，不主导基础审查结论。
