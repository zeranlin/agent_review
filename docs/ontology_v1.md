# `agent_review` 轻量本体 v1

## 目标

本体用于定义政府采购招标文件审查中的稳定概念边界，为 parser、LLM、规则和报告提供共享语义基础。

它回答 4 个问题：

1. 文档里这段内容是什么对象
2. 它属于哪个业务区域
3. 它是否具有正式约束效力
4. 它能否作为审查证据

## 核心实体

- `TenderDocument`: 单份待审查文件
- `DocumentPackage`: 一次审查中提交的文件集合
- `DocumentNode`: 文档中的结构化节点
- `ClauseUnit`: 可供审查消费的最小条款单元
- `SourceAnchor`: 原文定位锚点

## 业务区域

- `administrative_info`: 项目编号、预算、时间、联系人等基础信息
- `qualification`: 资格、资质、业绩、准入门槛
- `technical`: 技术参数、功能要求、样品、检测要求
- `business`: 商务要求、实施、售后、交付、驻场
- `scoring`: 评分方法、评分项、分值和评分标准
- `contract`: 付款、验收、违约、解除、争议解决
- `template`: 投标文件格式、声明函样式、报价表模板
- `policy_explanation`: 政策说明、中小企业与节能环保政策
- `appendix_reference`: 详见附件、见附表、另册提供
- `catalog_or_navigation`: 目录、导航项、章节树
- `public_copy_or_noise`: 页眉页脚、平台提示、信息公开残片
- `mixed_or_uncertain`: 无法稳定归入单一区域

## 条款语义类型

- `qualification_condition`
- `qualification_material_requirement`
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
- `template_instruction`
- `declaration_template`
- `example_clause`
- `reference_clause`
- `catalog_clause`
- `noise_clause`
- `unknown_clause`

## 效力标签

- `binding`: 正式约束内容
- `template`: 模板文本
- `example`: 示例文本
- `optional`: 可选项
- `reference_only`: 引用性文本
- `policy_background`: 政策背景说明
- `catalog`: 目录导航
- `public_copy_noise`: 噪音或公开副本文本
- `uncertain_effect`: 效力不明确

## 证据角色

- `direct_evidence`
- `supporting_evidence`
- `conflicting_evidence`
- `rebuttal_evidence`
- `missing_evidence_signal`

## 关键关系

- `contains`
- `parent_of`
- `child_of`
- `belongs_to_zone`
- `has_clause_semantic_type`
- `has_effect_tag`
- `references_appendix`
- `supports_review_point`
- `conflicts_with_review_point`
- `requires_manual_review`

## parser 映射要求

parser 应至少输出以下对象：

- `DocumentNode`
- `SemanticZone`
- `EffectTagResult`
- `ClauseUnit`

parser 不直接产出违规结论，只负责把原始文件映射到本体概念。

## 与 LLM 的关系

LLM 不是本体本身，而是文本到本体的映射器。

优先由规则完成：

- 结构识别
- 标题层级识别
- 目录识别
- 明显模板/示例/可选项识别

仅在低置信或冲突节点使用 LLM：

- 区域分类
- 效力标签判定
- 复杂表格语义切分
