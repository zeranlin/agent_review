# 《agent_review 法理驱动审查设计 v1》

## 1. 设计目标

本版本将 `agent_review` 从“词面命中式审查”升级为“法理母题驱动审查”。

核心目标：

- 先判断条款的法律作用，再判断风险，不直接用地名、行业名、机构名做结论。
- 把人工审核时真正使用的法理标准沉淀成稳定的数据契约和代码逻辑。
- parser 保持规则主链，LLM 仅作为低置信度歧义消解和未知结构补偿，不承担主体解析职责。
- 每条问题都回到证据、法理母题、法律依据三层闭环。

## 2. 为什么不能继续按表层规则设计

如果直接把 `深圳市医疗器械行业同类项目业绩不少于2个` 写成规则，会出现三个问题：

1. 泛化失败
   - 换成 `广州市`、`江苏省`、`华南地区`、`粤港澳大湾区` 就会漏检。
2. 法理错位
   - 人工审核关注的不是“深圳市”三个字，而是“是否以地域范围限制业绩”“是否缩小竞争范围”“是否与履约能力直接相关”。
3. 无法处理未知文件
   - 采购人给新结构、新行业、新措辞的文件时，词面规则扩库速度永远跟不上实际场景。

因此主链必须升级为：

`条款文本 -> 法律作用 -> 约束表示 -> 法理母题 -> 审查点要件 -> 裁决`

## 3. 政府采购招标文件的法理审查对象

政府采购招标文件不是普通说明书，而是同时承载以下法律功能的规范文本：

- 准入功能
  - 谁能投，哪些资格是必须的。
- 竞争组织功能
  - 是否公平开放，是否通过门槛、评分、材料负担变相限制竞争。
- 需求表达功能
  - 采购标的、技术参数、服务要求是否客观明确。
- 评审分配功能
  - 评分因素是否量化、相关、不过度偏向。
- 合同约束功能
  - 付款、验收、违约、保证金、风险承担是否平衡。
- 政策适用功能
  - 中小企业、进口产品、预留份额等政策口径是否一致。

因此 parser 不能只分“资格/技术/商务/评分/合同”，还必须识别条款在该区域中的法律作用。

## 4. 人工审核的法理母题

结合人工审核结果，当前优先固化的母题如下：

### 4.1 资格条件必要性

- 问题本体：
  - 该资格条件是否与履约能力、项目风险、监管要求直接相关？
- 常见表现：
  - 高新技术企业
  - 科技型中小企业
  - 纳税信用 A 级
  - 成立满 X 年

### 4.2 资格条件非歧视性

- 问题本体：
  - 是否通过地域、行业口径、企业身份、企业规模等缩小竞争范围？
- 常见表现：
  - 本地业绩
  - 特定地区业绩
  - 特定行业口径过窄
  - 企业规模、纳税额、注册资本

### 4.3 资格与评分边界

- 问题本体：
  - 已作为资格门槛的事项，是否又在评分中重复放大？
- 常见表现：
  - 同类业绩既作资格条件又作评分项
  - 证书既作准入又作加分

### 4.4 评分因素关联性

- 问题本体：
  - 评分因素是否与采购标的、服务质量、履约能力直接相关？
- 常见表现：
  - 行业无关证书
  - 企业规模/经营结果打分
  - 与标的不相干的人员资质

### 4.5 证明来源限制

- 问题本体：
  - 是否无正当理由指定特定检测机构、特定实验室、特定出具单位？
- 常见表现：
  - 指定某检测中心出具检测报告
  - 指定某主管机关或单一机构出具证明

### 4.6 文件内部一致性

- 问题本体：
  - 政策口径、资格口径、评分口径之间是否互相矛盾？
- 常见表现：
  - 非专门面向中小企业采购，却要求“科技型中小企业”
  - 项目属性、评分项、模板口径之间冲突

## 5. 轻量法理本体

### 5.1 zone ontology

继续保留：

- `administrative_info`
- `qualification`
- `technical`
- `business`
- `scoring`
- `contract`
- `template`
- `policy_explanation`
- `appendix_reference`
- `catalog_or_navigation`
- `public_copy_or_noise`
- `mixed_or_uncertain`

### 5.2 legal effect ontology

新增：

- `qualification_gate`
- `scoring_factor`
- `technical_requirement`
- `business_requirement`
- `contract_obligation`
- `evidence_source_requirement`
- `policy_statement`
- `template_instruction`
- `reference_notice`
- `unknown`

### 5.3 principle ontology

新增：

- `qualification_necessity`
- `qualification_nondiscrimination`
- `qualification_scoring_boundary`
- `scoring_relevance`
- `evidence_source_restriction`
- `internal_consistency`

### 5.4 constraint ontology

新增约束类型：

- `entity_identity`
- `certification`
- `credit_rating`
- `establishment_age`
- `performance_experience`
- `geographic_scope`
- `industry_scope`
- `institution_source`
- `evidence_document`
- `enterprise_scale`
- `policy_targeting`

新增限制轴：

- `qualification_level`
- `credit_grade`
- `establishment_years`
- `geographic_region`
- `industry_segment`
- `performance_count`
- `designated_institution`
- `enterprise_size`
- `policy_scope`
- `stage_burden`
- `source_authority`

## 6. 数据契约改造

### 6.1 ClauseUnit

新增：

- `legal_effect_type`
- `legal_principle_tags`
- `clause_constraint`

作用：

- ClauseUnit 不再只是“分句 + zone”，而是 parser 语义层的主载体。

### 6.2 ExtractedClause

新增：

- `legal_effect_type`
- `legal_principle_tags`
- `clause_constraint`

作用：

- 后续 applicability、fact collector、formal adjudication 不再只靠 `field_name + relation_tags`。

### 6.3 ReviewPointCondition

新增：

- `legal_effects`
- `principle_tags`
- `constraint_types`
- `restriction_axes`

作用：

- 审查点要件可直接表达“必须是资格门槛”“必须命中地域轴”“必须属于证明来源限制”等语义条件。

### 6.4 ReviewPointDefinition

新增：

- `legal_principle_tags`

作用：

- 法律依据和报告解释优先绑定法理母题，不绑定偶然措辞。

## 7. parser 主链改造

### 7.1 parser 主体仍为规则主链

原因：

- 政府采购审查要求稳定、可回溯、可复现。
- 独立隔离环境下，不能把主链建立在模型随时波动的自由发挥上。

### 7.2 LLM 只作低置信度歧义消解

仅在以下情况介入：

- zone 冲突过高
- 同一条款兼具模板/正文双重特征
- unknown document 路由后仍无法稳定归类

LLM 不负责：

- 整篇文件主解析
- 大段自由抽取
- 直接输出最终审查结论

### 7.3 parser 输出链路

规则流程：

`raw blocks / raw tables -> document tree -> zone classification -> clause units -> legal effect -> constraint normalization -> extracted clauses`

## 8. 审查点任务库改造

### 8.1 从“词规则”改成“法理要件”

示例：

- 旧：
  - `深圳市 + 同类业绩 + 不少于`
- 新：
  - `legal_effect = qualification_gate`
  - `constraint_type = performance_experience`
  - `restriction_axis in {geographic_region, industry_segment, performance_count}`

### 8.2 当前优先沉淀的法理驱动审查点

- `RP-QUAL-003`
  - 资格条件可能缺乏履约必要性或带有歧视性门槛
- `RP-QUAL-004`
  - 资格业绩要求可能存在地域限定、行业口径过窄或与评分重复
- `RP-EVID-001`
  - 证明材料来源可能被限定为特定机构或特定出具口径
- `RP-CONS-011`
  - 资格条件与政策适用口径可能自相矛盾
- `RP-SCORE-013`
  - 评分因素可能与采购标的和履约能力关联不足

## 9. applicability / adjudication 改造

### 9.1 applicability

由：

- `field_name + signal_groups`

升级为：

- `field_name + signal_groups + legal_effects + principle_tags + constraint_types + restriction_axes`

这样可以避免：

- 只有词面命中，却不是同一法律作用
- 命中模板文本，却被误当正文
- 命中某城市名，却不是限制性业绩门槛

### 9.2 formal adjudication

formal 层重点改为审：

- 是否有直接证据
- 证据是否来自有效正文
- 法理母题是否成立
- 是否仍存在明显反证或应升级人工的歧义

## 10. 与现有主链兼容方式

本次改造遵循“兼容升级”：

- 保留现有 zone / field_name / relation_tags
- 新增法理字段作为第二判据
- 优先改造资格、证明来源、评分相关性三条高价值主线
- 未改造的老审查点仍可继续运行

## 11. Sprint 拆解

### Sprint 1

- 新增 legal effect / principle / constraint ontology
- 扩展 ClauseUnit / ExtractedClause / ReviewPointCondition / ReviewPointDefinition
- 文档固化《法理驱动审查设计 v1》

### Sprint 2

- parser / extractor 接入 legal effect 和 constraint normalization
- ClauseUnit 与 ExtractedClause 统一产出法理语义
- proof source / qualification gate / scoring relevance 基础抽取闭环

### Sprint 3

- 重构 RP-QUAL-003 / RP-QUAL-004
- 新增 RP-EVID-001 / RP-CONS-011 / RP-SCORE-013
- 更新 legal basis 映射

### Sprint 4

- applicability 按法理要件判断
- fact collector 改为 constraint-aware evidence selection
- formal adjudication 压低模板、附件、词面误报

### Sprint 5

- 真实样本回归
- reviewer report 增加法理母题说明
- regression verdict 看“法理层能力变化”而不只看词命中数量

## 12. 本版本落地原则

- 能确定的，用规则和结构化契约确定。
- 不能确定的，输出 `manual_review_required` 或 `missing_evidence`。
- 法律解释边界不清时，不做武断定性。
- 每次新增法理母题，都必须同步更新：
  - 数据契约
  - 审查点目录
  - 法律依据映射
  - 测试样本
