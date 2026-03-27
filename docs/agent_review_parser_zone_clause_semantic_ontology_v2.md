# 《agent_review parser zone / clause semantic 政府采购审查本体草案 v2》

## 1. 目标

本草案用于把 `agent_review` 的 parser 主链正式收口到“政府采购招标文件审查语义”。

目标不是让 parser 直接判断违法，而是让 parser 能稳定回答两类问题：

1. 这段内容属于招标文件的哪个主区块
2. 这段内容在该区块里扮演什么条款语义角色

也就是把 parser 输出从“切出文本”升级为“切出政府采购审查可用的结构语义对象”。

---

## 2. 设计原则

### 2.1 主区块和条款语义分层

- `zone` 解决“这段话大致属于哪块”
- `clause semantic` 解决“这段话具体在做什么”

同一 `zone` 下可以有多种 `clause semantic`。

### 2.2 优先描述法律作用，不直接下违法结论

parser 只负责把文本映射成：

- 资格门槛
- 符合性审查
- 初审程序
- 无效投标后果
- 技术要求
- 商务要求
- 评分规则
- 合同义务
- 模板说明
- 政策说明

不直接输出“违规”。

### 2.3 政府采购审查视角优先

parser 的区块设计，不按写作习惯切，而按审查使用方式切。

例如：

- `资格性审查表` 和 `符合性审查表` 在文件里都像“审查表”
- 但在审查中，它们属于两个不同程序环节
- 因此不能长期都挂在 `qualification`

---

## 3. 主区块 Zone Ontology v2

| zone_type | 中文含义 | 典型内容 | 审查用途 |
| --- | --- | --- | --- |
| `administrative_info` | 基础信息区 | 项目名称、项目编号、预算金额、最高限价、采购人、代理机构、项目属性 | 用于头信息抽取和跨条款口径校验 |
| `qualification` | 资格区 | 资格要求、资格门槛、资质证书、资格证明、业绩要求 | 用于资格条件适度性和歧视性审查 |
| `conformity_review` | 符合性审查区 | 符合性审查表、初审、实质性响应、投标无效判定程序 | 用于审查程序、无效投标边界、否决规则 |
| `technical` | 技术区 | 技术参数、功能要求、样品要求、检测报告、性能指标 | 用于技术倾向性、排他性、参数一致性审查 |
| `business` | 商务区 | 交货、实施、售后、培训、服务响应、质保要求 | 用于商务合理性和履约匹配性审查 |
| `scoring` | 评分区 | 评分项、分值、评分标准、评审因素、量化规则 | 用于评分相关性、量化性、重复设门槛审查 |
| `contract` | 合同区 | 付款、验收、违约、解除、争议解决、履约担保 | 用于合同风险分配和履约公平性审查 |
| `policy_explanation` | 政策说明区 | 中小企业政策、价格扣除、节能环保、扶持政策说明 | 用于政策适用口径和项目事实绑定 |
| `template` | 模板区 | 声明函、承诺函、报价表、格式说明、样式文本 | 用于模板污染过滤和正式约束剥离 |
| `appendix_reference` | 附件引用区 | 详见附件、附表、另册、引用说明 | 用于附件依赖识别，不直接作为主证据 |
| `catalog_or_navigation` | 导航区 | 目录、章节标题、结构索引、导航节点 | 用于段落树组织，不直接作为结论证据 |
| `public_copy_or_noise` | 噪声区 | 页眉页脚、平台提示、公开副本残片 | 用于剔除干扰 |
| `mixed_or_uncertain` | 未确定区 | 暂时无法稳定归类的混合内容 | 用于后续消解和质量度量 |

### 3.1 v2 的关键变化

v2 相比此前版本，最重要的变化是：

- 把 `conformity_review` 从 `qualification` 中独立出来

原因：

1. `资格审查` 和 `符合性审查` 在政府采购审查中属于不同程序环节
2. `初审 / 实质性响应 / 投标无效` 不应被简单误认成资格条件本身
3. 后续 rule / planning / formal 需要明确知道这类条款属于“程序性约束”

---

## 4. 条款语义 Clause Semantic Ontology v2

| clause_semantic_type | 中文含义 | 典型文本 | 主要落点 |
| --- | --- | --- | --- |
| `administrative_clause` | 基础信息条款 | 招标文件信息、关键信息、采购人信息 | `administrative_info` |
| `qualification_condition` | 资格条件 | 投标人须具备、须为、须成立满、须具备同类业绩 | `qualification` |
| `qualification_material_requirement` | 资格证明材料要求 | 提供证书、证明扫描件、原件备查 | `qualification` |
| `qualification_review_clause` | 资格性审查程序条款 | 资格性审查表 | `qualification` |
| `conformity_review_clause` | 符合性审查条款 | 符合性审查表、符合性检查 | `conformity_review` |
| `preliminary_review_clause` | 初审条款 | 投标文件初审、初审包括资格性审查和符合性审查 | `conformity_review` |
| `invalid_bid_clause` | 投标无效条款 | 作投标无效处理、按投标无效处理、不予通过 | `conformity_review` 或保留原业务区 |
| `technical_requirement` | 技术要求 | 参数、性能、功能、检测要求 | `technical` |
| `business_requirement` | 商务要求 | 交货、售后、实施、服务响应 | `business` |
| `sample_or_demo_requirement` | 样品/演示要求 | 样品递交、演示内容 | `technical` |
| `scoring_rule` | 评分规则 | 得分、扣分、评分标准、量化办法 | `scoring` |
| `scoring_factor` | 评分因素 | 评分项标题、评分因素名称 | `scoring` |
| `contract_obligation` | 合同义务 | 一般履约约定 | `contract` |
| `payment_term` | 付款条款 | 付款方式、支付节点 | `contract` |
| `acceptance_term` | 验收条款 | 验收标准、验收流程 | `contract` |
| `breach_term` | 违约条款 | 违约责任、违约金 | `contract` |
| `termination_term` | 解约条款 | 解除合同、解约条件 | `contract` |
| `policy_clause` | 政策条款 | 中小企业政策、价格扣除、政策适用说明 | `policy_explanation` |
| `conditional_policy` | 条件型政策条款 | 专门面向中小企业采购/非专门面向中小企业采购的项目 | `policy_explanation` |
| `template_instruction` | 模板说明 | 下划线处如实填写、样式见本招标文件 | `template` |
| `declaration_template` | 声明函模板 | 中小企业声明函、承诺函格式 | `template` |
| `example_clause` | 示例条款 | 示例、样例、仅供参考 | `template` |
| `reference_clause` | 引用条款 | 详见附件、见附表 | `appendix_reference` |
| `catalog_clause` | 结构/目录条款 | 目录、章节标题、导航结构 | `catalog_or_navigation` |
| `noise_clause` | 噪声条款 | 页眉页脚、公开残片 | `public_copy_or_noise` |
| `unknown_clause` | 未知条款 | 暂未稳定归类 | `mixed_or_uncertain` |

---

## 5. 主区块与条款语义的对应关系

### 5.1 推荐的一对多映射

| zone_type | 推荐 clause semantic |
| --- | --- |
| `administrative_info` | `administrative_clause` |
| `qualification` | `qualification_condition` / `qualification_material_requirement` / `qualification_review_clause` |
| `conformity_review` | `conformity_review_clause` / `preliminary_review_clause` / `invalid_bid_clause` |
| `technical` | `technical_requirement` / `sample_or_demo_requirement` / `invalid_bid_clause` |
| `business` | `business_requirement` / `invalid_bid_clause` |
| `scoring` | `scoring_factor` / `scoring_rule` |
| `contract` | `contract_obligation` / `payment_term` / `acceptance_term` / `breach_term` / `termination_term` |
| `policy_explanation` | `policy_clause` / `conditional_policy` |
| `template` | `template_instruction` / `declaration_template` / `example_clause` |
| `appendix_reference` | `reference_clause` |
| `catalog_or_navigation` | `catalog_clause` |
| `public_copy_or_noise` | `noise_clause` |
| `mixed_or_uncertain` | `unknown_clause` |

### 5.2 特别说明

`invalid_bid_clause` 不要求永远独占 `conformity_review`。

原因：

- 有些“投标无效”是程序性否决规则
- 有些“投标无效”嵌在技术、商务、模板、合同语境中

因此 v2 采用：

- 主区块优先保留业务语境
- 条款语义单独标记 `invalid_bid_clause`

---

## 6. Parser 输出契约要求

Parser 至少应稳定输出：

- `zone_type`
- `clause_semantic_type`
- `effect_tags`
- `legal_effect_type`
- `anchor`

其中：

- `zone_type` 负责结构主区块
- `clause_semantic_type` 负责审查语义角色
- `legal_effect_type` 负责后续 rule / formal 的程序法与实体法分流

### 6.1 v2 对齐要求

本轮代码对齐至少应做到：

1. `符合性审查表` 能进入 `conformity_review`
2. `投标文件初审` 能进入 `preliminary_review_clause`
3. `按投标无效处理 / 作投标无效处理` 能进入 `invalid_bid_clause`
4. `资格性审查表` 不再与 `符合性审查表` 混成同一类普通资格条件

---

## 7. 对下游的影响

### 7.1 对 LegalFactCandidate

后续应把：

- `qualification_review_clause`
- `conformity_review_clause`
- `preliminary_review_clause`
- `invalid_bid_clause`

映射为程序性事实，而不是普通资格或合同事实。

### 7.2 对 review planning

后续应增加：

- `资格审查程序风险`
- `符合性审查/无效投标边界风险`

### 7.3 对 formal adjudication

formal 在选证时应能区分：

- 资格门槛条款
- 符合性否决条款
- 初审程序条款
- 无效投标后果条款

避免把不同性质条款混成一个问题簇。

---

## 8. 当前 v2 的边界

本草案仍是轻量本体，不追求一次穷尽全部政府采购语义。

当前不单独升为主区块，但后续可能继续升级的有：

- `procedure_or_timeline`
- `sample_demo_review`
- `complaint_and_query`
- `bid_submission`

本次 v2 的重点，是先把政府采购审查里最容易混淆、又最影响后续审查效果的：

- `qualification`
- `conformity_review`
- `scoring`
- `template`
- `policy_explanation`

之间的边界打稳。
