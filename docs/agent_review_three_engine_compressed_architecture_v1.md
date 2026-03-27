# 《agent_review 三引擎压缩架构 v1》

## 1. 目标

将当前对外主链正式压缩为三段：

1. `ParserEngine`
2. `ComplianceEngine`
3. `ReportEngine`

其中原先单独表述的 `planning / fact / rule / adjudication / compliance bridge / llm assist` 不再作为对外层级暴露，而是并入 `ComplianceEngine` 内部子模块。

## 2. 对外主链

```text
招标文件
-> ParserEngine
-> ComplianceEngine
-> ReportEngine
```

## 3. 三引擎职责

### 3.1 ParserEngine

职责：

- 文件类型识别
- 文本加载与归一化
- 文档树构建
- zone classification
- effect tagging
- `ClauseUnit` / `ParsedTenderDocument` 生成
- 基础头部字段解析

输入：

- 原始招标文件

输出：

- `ParseResult`
- `ParsedTenderDocument`
- `ClauseUnit[]`

### 3.2 ComplianceEngine

职责：

- 审查组织与路由
- 事实归一化
- 规则命中
- 法律依据绑定
- 风险裁决
- LLM 小范围补偿

内部子模块：

#### `ComplianceEngine.routing`

由原 planning 收口而来，负责：

- 文档画像
- 风险母题激活
- 高价值字段选择
- 定向抽取需求生成
- unknown document 路由
- LLM 上下文裁剪

#### `ComplianceEngine.fact_rule`

负责：

- `ClauseUnit -> LegalFactCandidate`
- `LegalFactCandidate -> RuleHit`
- `RuleHit -> ReviewPointInstance`

#### `ComplianceEngine.authority_adjudication`

负责：

- authority binding
- applicability check
- quality gate
- formal adjudication
- embedded compliance bridge finding 合并

#### `ComplianceEngine.llm_assist`

负责：

- parser 后小范围补偿
- 高价值字段增强
- 二审
- 误报压制

输入：

- `ParseResult`
- `ParsedTenderDocument`
- `ClauseUnit[]`

输出：

- `ReviewPoint[]`
- `Finding[]`
- `FormalAdjudication[]`
- 总体结论

### 3.3 ReportEngine

职责：

- `reviewer_report`
- `enhanced_report`
- `formal_review_opinion`
- `opinion_letter`
- artifacts / manifest / trace / eval summary

输入：

- `ComplianceEngine` 审查结果

输出：

- Markdown / JSON / artifacts

## 4. 旧概念映射

- `planning` -> `ComplianceEngine.routing`
- `fact/rule` -> `ComplianceEngine.fact_rule`
- `adjudication` -> `ComplianceEngine.authority_adjudication`
- `llm enhancement / bridge assist` -> `ComplianceEngine.llm_assist`

## 5. 当前代码映射

### ParserEngine

- `parsers/`
- `structure/`
- `extractors/`
- `parsed_tender_document.py`
- `header_info.py`

### ComplianceEngine

- `compliance/`
- `adjudication_core/`
- `rules/`
- `rule_runtime.py`
- `review_point_catalog.py`
- `review_point_contract_registry.py`
- `fact_collectors.py`

### ReportEngine

- `reporting.py`
- `outputs/`
- `app/workbench.py` 的结果展示部分

## 6. 重构原则

1. 只压缩对外层级，不立即删除内部机制
2. planning 不再独立为 `PlanningEngine`
3. 现有主链仍可保留内部细分步骤，但统一归属到三引擎之下
4. 目录对齐优先通过新入口包完成，再逐步迁移实现

## 7. 本轮代码收口目标

本轮先建立三个稳定入口包：

- `parser_engine/`
- `compliance_engine/`
- `report_engine/`

作为未来目录与实现逐步迁移的承接层。
