# `agent_review` 本体与数据契约统一草案 v1

## 目标

把“政府采购招标文件是什么”沉淀成 parser、profile、planning 共用的稳定语义骨架，避免字段定义和 zone 语义散落在局部实现里。

## 一、统一 zone ontology

核心原则：

- zone 先表达“这段内容属于什么区域”，不直接表达是否违规。
- 审查主区统一收敛到：`资格 / 技术 / 商务 / 评分 / 合同 / 模板 / 附件 / 无关内容`。
- `administrative_info` 作为头信息与基础事实区保留，用于 HeaderInfo、项目画像和任务路由。
- `policy_explanation / catalog_or_navigation / mixed_or_uncertain` 作为辅助区保留，用于误报治理与低置信路由。

### zone 到主审查类型映射

- `administrative_info` -> `基础信息`
- `qualification` -> `资格`
- `technical` -> `技术`
- `business` -> `商务`
- `scoring` -> `评分`
- `contract` -> `合同`
- `template` -> `模板`
- `appendix_reference` -> `附件`
- `public_copy_or_noise` -> `无关内容`
- `policy_explanation` -> `政策说明`
- `catalog_or_navigation` -> `导航`
- `mixed_or_uncertain` -> `未确定`

## 二、核心数据契约

### `DocumentProfile`

描述“当前文件的结构画像”，是未知文件 routing 的第一输入。

关键字段：

- `ontology_version`
- `procurement_kind`
- `routing_mode / routing_reasons`
- `dominant_zones`
- `primary_review_types`
- `effect_distribution`
- `clause_semantic_distribution`
- `structure_flags / quality_flags / unknown_structure_flags`
- `risk_activation_hints`

### `DomainProfile`

描述“仓库内沉淀的领域经验包”，不是单份文件事实。

关键字段：

- `ontology_version`
- `applies_to_procurement_kinds`
- `supported_zone_types`
- `primary_review_types`
- `trigger_keywords / negative_keywords`
- `risk_lexicon_pack_id / evidence_pattern_pack_id / false_positive_pack_id`

### `ClauseUnit`

描述“可供审查消费的最小条款单元”，是 extractor 和 adjudication 的核心输入。

关键字段：

- `ontology_version`
- `zone_type`
- `primary_review_type`
- `clause_semantic_type`
- `effect_tags`
- `anchor / path`
- `confidence`

### `HeaderInfo`

描述“头部关键事实”，不是固定模板字段，而是头信息解析结果容器。

关键字段：

- `ontology_version`
- `project_name / project_code`
- `purchaser_name / agency_name`
- `budget_amount / max_price`
- `source_evidence`
- `confidence`

### `ReviewPlanningContract`

描述“结构画像 -> 任务激活 -> 抽取需求”的统一计划输出。

关键字段：

- `ontology_version`
- `routing_mode / route_tags / routing_flags`
- `activated_risk_families / suppressed_risk_families`
- `target_zones`
- `target_primary_review_types`
- `planned_catalog_ids`
- `base / required / optional / unknown_fallback extraction demands`
- `high_value_fields`

## 三、实现边界

- parser 负责把原文映射到 `DocumentNode / SemanticZone / ClauseUnit / HeaderInfo`
- profile 层负责生成 `DocumentProfile / DomainProfile`
- planning 层负责生成 `ReviewPlanningContract`
- adjudication 层只消费这些契约，不自行发明新语义

## 四、对未知文件的意义

面对从未见过的招标文件，系统优先依赖：

- zone ontology 的稳定分区
- DocumentProfile 的结构画像
- ReviewPlanningContract 的定向激活

而不是直接把全文交给 LLM。
