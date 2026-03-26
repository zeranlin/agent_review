# `agent_review` 审查点-规则-法条三层数据契约 v1

## 目标

把当前仓库里的：

- `ClauseUnit`
- `DocumentProfile / DomainProfile`
- `ReviewPlanningContract`
- `review_point_catalog`
- `formal_adjudication`

进一步收敛成一条法理驱动主链：

`parser -> LegalFactCandidate -> RuleDefinition -> ReviewPointContract -> AuthorityBinding -> adjudication`

目标不是替换现有实现，而是补齐“parser 输出、审查点、规则、法条、LLM 介入边界”之间的统一契约。

## 一、三层模型总览

### 第一层：`LegalFactCandidate`

描述“从原文中抽出来、可供规则消费的法律审查事实候选”。

这一层解决的是：

- parser 不直接下结论
- 规则不直接扫全文
- 同一句话在不同 zone 中的不同含义，先被沉淀成事实候选

### 第二层：`RuleDefinition`

描述“如何把事实候选变成规则命中”。

这一层解决的是：

- 100 个规则如何机器化
- 规则如何表达触发条件、例外条件、证据要求
- 规则如何关联现有审查点

### 第三层：`ReviewPointContract + AuthorityBinding`

描述“一个审查点在法理上是什么、需要什么事实、适用什么法条、何时必须转人工”。

这一层解决的是：

- 审查点不是标题清单，而是法理任务模板
- 法律法规不是报告附注，而是审查逻辑约束
- formal/manual boundary 不是临时判断，而是受法条和边界规则约束

## 二、对象关系

建议关系如下：

- 一个 `ClauseUnit` 可以产出多个 `LegalFactCandidate`
- 一个 `RuleDefinition` 可以消费多种 `LegalFactCandidate`
- 多个 `RuleDefinition` 可以映射到同一个 `ReviewPointContract`
- 一个 `ReviewPointContract` 可以绑定多个 `AuthorityBinding`
- 一个 `AuthorityBinding` 可以同时服务多个 `ReviewPointContract`

即：

- `ClauseUnit 1 -> N LegalFactCandidate`
- `RuleDefinition N -> 1 ReviewPointContract`
- `ReviewPointContract 1 -> N AuthorityBinding`

## 三、`LegalFactCandidate` 字段草案

## 角色

`LegalFactCandidate` 是 parser 和规则层之间的桥。

它不直接表示“违规”，只表示：

- 这里疑似有资格门槛
- 这里疑似有评分因素
- 这里疑似有证明材料来源限制
- 这里疑似有付款验收联动

## 字段定义

- `fact_id`
  - 唯一标识
  - 建议格式：`LF-<doc>-<seq>`

- `document_id`
  - 所属文档

- `source_unit_id`
  - 来源 `ClauseUnit` 标识

- `fact_type`
  - 事实类型
  - 建议枚举：
    - `qualification_requirement`
    - `qualification_material_requirement`
    - `performance_requirement`
    - `certificate_requirement`
    - `scoring_factor`
    - `scoring_scale`
    - `evidence_source_requirement`
    - `technical_parameter`
    - `delivery_requirement`
    - `payment_term`
    - `acceptance_term`
    - `breach_term`
    - `termination_term`
    - `template_reference`
    - `cross_clause_conflict_signal`

- `zone_type`
  - 继承自 `ClauseUnit.zone_type`
  - 用于表达相同语句所处语境

- `clause_semantic_type`
  - 继承或归一自 `ClauseUnit.clause_semantic_type`

- `effect_tags`
  - 继承自 `ClauseUnit.effect_tags`
  - 用于误报治理

- `subject`
  - 条款约束对象
  - 示例：`投标人`、`中标人`、`供应商`

- `predicate`
  - 条款动作或关系
  - 示例：`须具备`、`应提供`、`得分`、`扣款`

- `object_text`
  - 条款核心内容原文片段
  - 示例：`高新技术企业证书`

- `normalized_terms`
  - 归一化术语列表
  - 示例：`["高新技术企业", "企业证书"]`

- `constraint_type`
  - 约束类型
  - 示例：
    - `mandatory`
    - `scoring_bonus`
    - `negative_penalty`
    - `range_limit`
    - `source_designation`
    - `time_limit`
    - `regional_limit`

- `constraint_value`
  - 结构化约束值
  - 可为对象
  - 示例：
    - `{"min_years": 5}`
    - `{"min_count": 2}`
    - `{"region": "深圳市"}`
    - `{"score": 5}`

- `evidence_stage`
  - 材料要求出现的阶段
  - 建议枚举：
    - `qualification`
    - `bidding`
    - `evaluation`
    - `contract_performance`
    - `acceptance`
    - `unknown`

- `counterparty`
  - 相对方
  - 合同类场景可填：`采购人`、`中标人`

- `anchor`
  - 定位锚点
  - 对应原文页码、段号、表格坐标

- `table_context`
  - 若来自表格，保留行列上下文

- `supporting_context`
  - 上下文句段
  - 用于 LLM 小范围补偿和正式引文

- `confidence`
  - 事实抽取置信度

- `needs_llm_disambiguation`
  - 是否建议进入 LLM 歧义消解

## 与现有代码映射

- 输入来源：
  - `src/agent_review/extractors/clause_units.py`
  - `src/agent_review/extractors/clauses.py`
- 上游依赖：
  - `ClauseUnit`
- 下游消费者：
  - `RuleDefinition`
  - `ReviewPlanningContract`

## 四、`RuleDefinition` 字段草案

## 角色

`RuleDefinition` 是规则引擎中的最小执行单元。

它回答：

- 什么事实会触发规则
- 触发后归到哪个审查点
- 这条规则是硬规则、软规则还是边界规则
- 需要什么证据才可升级为 formal

## 字段定义

- `rule_id`
  - 唯一标识
  - 建议格式：`RULE-<family>-<seq>`

- `version`
  - 规则版本

- `name`
  - 规则名称

- `status`
  - `active / shadow / deprecated`

- `point_id`
  - 对应 `ReviewPointContract.point_id`

- `rule_type`
  - 建议枚举：
    - `hard_rule`
    - `soft_rule`
    - `cross_clause_rule`
    - `boundary_rule`

- `risk_family`
  - 母题
  - 示例：`qualification`、`scoring`、`contract`

- `applicable_zone_types`
  - 可适用 zone

- `applicable_fact_types`
  - 可消费的 `LegalFactCandidate.fact_type`

- `trigger_patterns`
  - 触发词、正则、结构信号或字段条件
  - 应支持：
    - 文本 trigger
    - 表格 trigger
    - 数值阈值 trigger
    - 关系 trigger

- `required_fact_slots`
  - 规则命中前必须补齐的事实槽位
  - 示例：
    - `region`
    - `industry_scope`
    - `score_value`
    - `material_stage`

- `evidence_requirements`
  - 证据要求
  - 示例：
    - `direct_quote_required`
    - `table_row_preferred`
    - `cross_clause_alignment_required`

- `exception_patterns`
  - 例外或排除条件
  - 示例：
    - `法定资质`
    - `行业强制标准`
    - `医疗安全必要性`

- `severity_hint`
  - 规则层风险建议
  - `low / medium / high / critical`

- `default_disposition`
  - 规则命中默认流向
  - `warning / manual_review_required / candidate_confirmed_issue`

- `llm_assist_policy`
  - 建议枚举：
    - `forbidden`
    - `low_confidence_only`
    - `boundary_only`
    - `allowed`

- `llm_questions`
  - 若允许 LLM，限定其只回答哪些问题
  - 示例：
    - 是否存在履约必要性
    - 是否属于法定例外
    - 是否存在跨段重复设门槛

- `remedy_template_ids`
  - 建议修订模板标识

- `authority_binding_ids`
  - 关联 `AuthorityBinding`

## 与现有代码映射

- 当前最接近的位置：
  - `src/agent_review/review_point_catalog.py`
  - `src/agent_review/applicability.py`
  - `src/agent_review/review_quality_gate.py`
- 后续建议：
  - 把分散的 `required_fields / enhancement_fields / applicability logic` 收敛到 `RuleDefinition`

## 五、`ReviewPointContract` 字段草案

## 角色

`ReviewPointContract` 是审查点层的正式契约。

它不是单纯标题，而是一个法理任务模板。

它回答：

- 该审查点审什么
- 需要什么事实
- 适用哪些 zone
- 绑定哪些法条
- 哪些情况必须保留人工边界

## 字段定义

- `point_id`
  - 唯一标识
  - 建议沿用当前 `RP-*`

- `title`
  - 审查点标题

- `description`
  - 审查点说明

- `risk_family`
  - 风险母题

- `legal_theme`
  - 法理主题
  - 示例：
    - `公平竞争`
    - `资格必要性`
    - `评分相关性`
    - `评分可复核性`
    - `合同公平性`
    - `需求可执行性`

- `applicable_procurement_kinds`
  - `goods / service / mixed / engineering_related / unknown`

- `target_zone_types`
  - 主要依赖的 zone

- `primary_review_types`
  - 资格、技术、商务、评分、合同等主审查类型

- `required_fact_types`
  - 至少需要哪些 `LegalFactCandidate.fact_type`

- `supporting_fact_types`
  - 辅助事实类型

- `activation_rule_ids`
  - 可激活本审查点的规则集

- `suppression_rule_ids`
  - 可抑制或降级本审查点的规则集

- `required_fields`
  - 与当前 planning 兼容的抽取字段

- `enhancement_fields`
  - 当前 planning 的增强字段

- `evidence_policy`
  - 证据政策
  - 示例：
    - `single_direct_quote_sufficient`
    - `cross_clause_evidence_required`
    - `table_and_text_alignment_required`

- `quality_gate_policy`
  - 如何受 `review_quality_gate` 约束
  - 示例：
    - 模板命中是否直接过滤
    - `reference_only` 是否仅能进入 manual

- `manual_boundary_policy`
  - 人工边界策略
  - 示例：
    - `authority_driven`
    - `evidence_insufficient_or_boundary`
    - `always_manual_when_special_industry`

- `authority_binding_ids`
  - 主法条绑定列表

- `severity_policy`
  - 审查点层严重性策略

- `report_group`
  - 报告分组
  - 示例：
    - `资格与公平竞争`
    - `评分不规范风险`
    - `合同履约风险`

- `report_priority`
  - 报告展示优先级

## 与现有代码映射

- 当前最接近的位置：
  - `docs/review_point_catalog.md`
  - `src/agent_review/review_point_catalog.py`
  - `src/agent_review/pipeline.py` 中的 planning 字段
- 后续建议：
  - 将当前“标准审查点清单 + applicability + external authority map”统一到 `ReviewPointContract`

## 六、`AuthorityBinding` 字段草案

## 角色

`AuthorityBinding` 表示“某条法规条款如何约束某个审查点或规则”。

它不是单纯法条引用，而是机器可执行的法理绑定。

## 字段定义

- `binding_id`
  - 唯一标识

- `authority_id`
  - 法规文件标识
  - 对应外部 `authorities.json`

- `clause_id`
  - 法条标识
  - 对应外部 `clause-index.json`

- `doc_title`
  - 法规名称

- `article_label`
  - 条文标识

- `norm_level`
  - 法规层级
  - 示例：
    - `law`
    - `administrative_regulation`
    - `ministerial_order`
    - `normative_guidance`

- `binding_scope`
  - 绑定范围
  - `point / rule / shared_principle`

- `point_id`
  - 若绑定审查点，填写对应点

- `rule_id`
  - 若绑定规则，填写对应规则

- `legal_proposition`
  - 机器可消费的法理命题
  - 示例：
    - `资格条件应与履约能力直接相关`
    - `评分因素应与采购需求和履约质量相关`
    - `验收标准应当明确客观`

- `applicability_conditions`
  - 该法条在什么场景适用

- `exclusion_conditions`
  - 该法条在什么场景不直接适用

- `requires_human_review_when`
  - 哪些边界情形必须转人工
  - 应与 formal/manual boundary 直接打通

- `evidence_expectations`
  - 证据期望
  - 示例：
    - `需要直接引文`
    - `需要评分表行证据`
    - `需要资格与评分跨段对齐`

- `reasoning_template`
  - 法理说明模板

- `suggested_remedy_template`
  - 建议修订模板

- `priority`
  - 主依据、次依据、补充依据

## 与现有代码映射

- 当前最接近的位置：
  - `data/legal-authorities/index/review-point-authority-map.json`
  - `data/legal-authorities/index/clause-index.json`
  - `src/agent_review/external_data.py`
  - `src/agent_review/legal_basis.py`
- 后续建议：
  - 将目前外部 authority map 从“查得出”升级为“可驱动 applicability / manual boundary / reporting”

## 七、四个对象的串联示例

例句：

`投标人须具备深圳市医疗器械行业同类项目业绩不少于2个。`

### parser / fact 层

- `ClauseUnit`
  - `zone_type=qualification`
  - `effect_tags=[binding]`

- `LegalFactCandidate`
  - `fact_type=performance_requirement`
  - `subject=投标人`
  - `predicate=须具备`
  - `object_text=深圳市医疗器械行业同类项目业绩不少于2个`
  - `constraint_type=regional_limit`
  - `constraint_value={"region": "深圳市", "industry_scope": "医疗器械", "min_count": 2}`

### 规则层

- `RuleDefinition`
  - `rule_id=RULE-QUAL-PERF-REGION-001`
  - `point_id=RP-QUAL-004`
  - `rule_type=soft_rule`
  - `required_fact_slots=["region", "industry_scope", "min_count"]`

### 审查点层

- `ReviewPointContract`
  - `point_id=RP-QUAL-004`
  - `legal_theme=资格必要性与公平竞争`
  - `required_fact_types=["performance_requirement"]`
  - `evidence_policy=cross_clause_evidence_required`

### 法条层

- `AuthorityBinding`
  - `point_id=RP-QUAL-004`
  - `legal_proposition=资格业绩条件不得无必要地收窄地域和行业范围`
  - `requires_human_review_when=["项目确有现场连续运行、应急保障等客观场景需要"]`

## 八、LLM 介入边界

四个契约里，只有以下位置允许 LLM 介入：

- `LegalFactCandidate.needs_llm_disambiguation=true`
- `RuleDefinition.llm_assist_policy != forbidden`
- `AuthorityBinding.requires_human_review_when` 触发边界解释
- `ReviewPointContract.manual_boundary_policy` 要求进行必要性解释

LLM 不应直接生成新的审查点，也不应绕过规则和法条直接下最终结论。

## 九、落地顺序建议

### Sprint 1

- 新增 `LegalFactCandidate` 契约文档与最小数据类
- 先覆盖资格、评分、合同三大类事实

### Sprint 2

- 把当前高频规则整理为 `RuleDefinition`
- 先迁移：
  - 资格门槛
  - 评分相关性
  - 评分量化
  - 验收/付款联动

### Sprint 3

- 将 `review_point_catalog` 升级为 `ReviewPointContract`
- 把 `required_fields / target_zones / risk_family` 正式收口

### Sprint 4

- 将外部 `review-point-authority-map + clause-index` 升级为 `AuthorityBinding`
- 接入 `applicability / formal/manual boundary / reporting`

## 十、结论

这四个契约的分工应固定为：

- `LegalFactCandidate`
  - 负责把 parser 输出转成法律事实候选

- `RuleDefinition`
  - 负责把法律事实转成规则命中

- `ReviewPointContract`
  - 负责把规则命中组织成法理审查任务

- `AuthorityBinding`
  - 负责把法条、人工边界和法理说明真正绑定到审查主链

这样，`agent_review` 才能从“规则 + 审查点 + 法规 + LLM 的松散拼接”升级成“法理驱动的结构化审查系统”。
