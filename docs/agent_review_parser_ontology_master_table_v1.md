# 《agent_review parser 本体总表 v1》

## 1. 目标

本表用于把 `agent_review` parser 相关的设计文档收敛成一份主文档。

它统一回答 6 个问题：

1. 这段内容属于哪个主区块
2. 这段内容在该区块中是什么条款语义
3. 它通常长什么标题
4. 它通常长什么条款
5. 它主要服务哪些审查点
6. 它在后续主链中应如何使用

本表作为 parser 主链、planning 主链、formal 主链的共同对照表。

---

## 2. 设计原则

### 2.1 两层结构

- `zone`：主区块层，回答“属于哪块”
- `clause semantic`：条款语义层，回答“在做什么”

### 2.2 parser 不直接下违法结论

parser 负责把文本映射到：

- 资格门槛
- 符合性审查
- 初审程序
- 投标无效后果
- 技术要求
- 商务要求
- 评分规则
- 合同义务
- 政策说明
- 模板说明

不直接判断是否违规。

### 2.3 政府采购审查视角优先

parser 的区不是按写作文风切，而是按审查使用方式切。

例如：

- `资格性审查表` 属于资格审查程序
- `符合性审查表` 属于符合性审查程序
- 两者都不是普通“资格门槛条款”

---

## 3. 主区块总表

| 区 | zone_type | 中文定义 | 典型标题 | 典型条款 | 审查点用途 |
| --- | --- | --- | --- | --- | --- |
| 基础信息区 | `administrative_info` | 项目基本信息与头信息 | 招标文件信息、关键信息、采购人信息、项目基本情况 | 项目编号、项目名称、预算金额、最高限价、采购单位、代理机构、项目属性 | 头信息抽取、项目属性判断、预算/最高限价核对、报告抬头、跨条款一致性校验 |
| 资格区 | `qualification` | 投标准入门槛与资格审查相关内容 | 资格要求、申请人的资格要求、投标人资格要求、一般资格要求、特定资格要求、资格性审查表 | 投标人须具备某资质、须提供某证明、须成立满几年、须具备同类业绩、须为某类企业 | 资格门槛适度性、歧视性门槛、资格与评分重复设门槛、指定资质/业绩/地域限制审查 |
| 符合性审查区 | `conformity_review` | 符合性审查、初审、投标无效程序与后果 | 符合性审查表、投标文件初审、符合性审查、符合性检查、实质性响应要求 | 未实质性满足招标文件要求作投标无效处理、初审包括资格性审查和符合性审查、符合性条款不通过则投标无效 | 无效投标边界、程序性否决条件、符合性审查合法性、资格/符合性/评分边界拆分 |
| 技术区 | `technical` | 采购需求中的技术要求 | 技术要求、技术参数、技术规范、用户需求书、检测报告、样品要求 | 产品响应时间、性能指标、设备重量、检测报告要求、标准引用、样品递交要求 | 技术倾向性、参数排他性、标准真伪/适用性、参数一致性、检测要求负担、样品演示风险 |
| 商务区 | `business` | 招标阶段的商务履约要求 | 商务要求、商务部分、服务要求、售后服务要求、交货及付款要求 | 交货期、实施周期、培训要求、售后服务、免费保修期、服务响应时间 | 商务合理性、履约周期适度性、售后要求必要性、商务要求与项目属性匹配性审查 |
| 评分区 | `scoring` | 评标评分与量化规则 | 评分标准、评标信息、评标办法、综合评分法、评分项、评审因素 | 检测报告得分、业绩得分、证书得分、偏离扣分、样品演示评分、商务偏离评分 | 评分相关性、量化性、客观性、行业相关性、资格与评分重复、主观评分和超权重问题审查 |
| 合同区 | `contract` | 中标后合同履约与责任条款 | 合同条款、专用条款、通用条款、付款方式、验收条款、违约责任 | 付款节点、验收标准、违约责任、履约保证金、质量保证金、解除合同、争议解决 | 合同风险分配、付款验收联动、违约责任失衡、保证金占压、检测费用转嫁、解约条款失衡审查 |
| 政策说明区 | `policy_explanation` | 政府采购政策适用口径 | 中小企业政策说明、价格扣除说明、政策适用说明、节能环保政策 | 专门面向中小企业采购的项目不再执行价格扣除、非专门面向中小企业采购执行价格扣除、节能产品政策说明 | 政策适用口径审查、项目事实绑定、政策与资格/评分/分包条款冲突、模板政策误留审查 |
| 模板区 | `template` | 格式、声明函、模板、样式文本 | 投标文件格式、声明函、承诺函、报价表、样式、格式 | 中小企业声明函格式、承诺函模板、报价表示例、下划线处如实填写 | 模板污染过滤、示例文本剥离、模板误报压制、模板残留识别 |
| 附件引用区 | `appendix_reference` | 附件、附表、另册引用关系 | 详见附件、见附表、另册提供、附件说明 | 详见附件1、详见附表、另册提供技术参数、附件中另行规定 | 附件依赖识别、附件引用提示、证据定位辅助，不直接作为主证据 |
| 导航区 | `catalog_or_navigation` | 目录、章节树、结构索引 | 目录、第一章招标公告、第三章用户需求书、第七章评审程序及评审方法 | 章节标题、目录项、结构树节点 | 段落树组织、标题上下文继承、路径定位，不直接作为风险结论证据 |
| 噪声区 | `public_copy_or_noise` | 页眉页脚、平台提示、公开副本残片 | 页眉页脚、平台提示、公开副本残片、复制提示 | 深圳政府采购网自动公开提示、下载说明、公开副本说明 | 噪声剔除、公开副本文本隔离、避免误入审查主链 |
| 未确定区 | `mixed_or_uncertain` | 暂时无法稳定归类的混合内容 | 混合标题、混合段落、低置信条款 | 同时带评分/资格/模板信号的句子、缺少上下文的混合条款 | 低置信待消解池、LLM 小范围补偿入口、质量度量、后续规则收口目标 |

---

## 4. 条款语义总表

| 条款语义 | clause_semantic_type | 中文定义 | 典型文本 | 推荐主区块 | 法律作用 |
| --- | --- | --- | --- | --- | --- |
| 基础信息条款 | `administrative_clause` | 头信息或基础信息条款 | 招标文件信息、关键信息、采购人信息 | `administrative_info` | `unknown` |
| 资格条件 | `qualification_condition` | 资格门槛本身 | 投标人须具备、须为、须成立满、须具备同类业绩 | `qualification` | `qualification_gate` |
| 资格证明材料要求 | `qualification_material_requirement` | 资格证明材料提交要求 | 提供证书、证明扫描件、原件备查 | `qualification` | `qualification_gate` |
| 资格性审查程序条款 | `qualification_review_clause` | 资格性审查的程序容器 | 资格性审查表 | `qualification` | `review_procedure` |
| 符合性审查条款 | `conformity_review_clause` | 符合性审查程序条款 | 符合性审查表、符合性检查 | `conformity_review` | `review_procedure` |
| 初审条款 | `preliminary_review_clause` | 初审流程和初审范围 | 投标文件初审、初审包括资格性审查和符合性审查 | `conformity_review` | `review_procedure` |
| 投标无效条款 | `invalid_bid_clause` | 规定投标无效后果或否决条件 | 作投标无效处理、按投标无效处理、不予通过 | `conformity_review` 或原业务区 | `review_procedure` |
| 技术要求 | `technical_requirement` | 技术参数、功能、性能要求 | 参数、性能、功能、检测要求 | `technical` | `technical_requirement` |
| 商务要求 | `business_requirement` | 交货、售后、实施等商务要求 | 交货、售后、实施、服务响应 | `business` | `business_requirement` |
| 样品/演示要求 | `sample_or_demo_requirement` | 样品或演示相关要求 | 样品递交、样品清单、演示内容 | `technical` | `technical_requirement` |
| 评分规则 | `scoring_rule` | 量化得分或扣分规则 | 得分、扣分、评分标准、量化办法 | `scoring` | `scoring_factor` |
| 评分因素 | `scoring_factor` | 评分项标题或评分因素名称 | 技术保障措施、近三年同类业绩、检测报告 | `scoring` | `scoring_factor` |
| 合同义务 | `contract_obligation` | 一般合同履约义务 | 履行义务、履约责任、一般合同约定 | `contract` | `contract_obligation` |
| 付款条款 | `payment_term` | 付款安排和付款节点 | 付款方式、支付节点 | `contract` | `contract_obligation` |
| 验收条款 | `acceptance_term` | 验收标准和验收流程 | 验收标准、验收流程 | `contract` | `contract_obligation` |
| 违约条款 | `breach_term` | 违约责任和违约金 | 违约责任、违约金 | `contract` | `contract_obligation` |
| 解约条款 | `termination_term` | 解除合同或解约条件 | 解除合同、解约条件 | `contract` | `contract_obligation` |
| 政策条款 | `policy_clause` | 政策说明或适用口径 | 中小企业政策、价格扣除、政策适用说明 | `policy_explanation` | `policy_statement` |
| 条件型政策条款 | `conditional_policy` | 带条件分支的政策条款 | 专门面向中小企业采购/非专门面向中小企业采购的项目 | `policy_explanation` | `policy_statement` |
| 模板说明 | `template_instruction` | 格式说明、填写说明、样式说明 | 下划线处如实填写、样式见本招标文件 | `template` | `template_instruction` |
| 声明函模板 | `declaration_template` | 声明函或承诺函模板正文 | 中小企业声明函、承诺函格式 | `template` | `template_instruction` |
| 示例条款 | `example_clause` | 示例、样例、仅供参考条款 | 示例、样例、仅供参考 | `template` | `template_instruction` |
| 引用条款 | `reference_clause` | 指向附件、附表、另册的引用说明 | 详见附件、见附表 | `appendix_reference` | `reference_notice` |
| 目录/结构条款 | `catalog_clause` | 目录和章节结构节点 | 目录、章节标题、导航结构 | `catalog_or_navigation` | `reference_notice` |
| 噪声条款 | `noise_clause` | 页眉页脚或无关残片 | 页眉页脚、公开残片 | `public_copy_or_noise` | `unknown` |
| 未知条款 | `unknown_clause` | 暂时未稳定判定的条款 | 暂未稳定归类 | `mixed_or_uncertain` | `unknown` |

---

## 5. zone 与 clause semantic 的推荐映射

| zone_type | 推荐 clause semantic |
| --- | --- |
| `administrative_info` | `administrative_clause` |
| `qualification` | `qualification_condition` / `qualification_material_requirement` / `qualification_review_clause` |
| `conformity_review` | `conformity_review_clause` / `preliminary_review_clause` / `invalid_bid_clause` |
| `technical` | `technical_requirement` / `sample_or_demo_requirement` / `invalid_bid_clause` |
| `business` | `business_requirement` / `invalid_bid_clause` |
| `scoring` | `scoring_factor` / `scoring_rule` |
| `contract` | `contract_obligation` / `payment_term` / `acceptance_term` / `breach_term` / `termination_term` / `invalid_bid_clause` |
| `policy_explanation` | `policy_clause` / `conditional_policy` |
| `template` | `template_instruction` / `declaration_template` / `example_clause` / `invalid_bid_clause` |
| `appendix_reference` | `reference_clause` |
| `catalog_or_navigation` | `catalog_clause` |
| `public_copy_or_noise` | `noise_clause` |
| `mixed_or_uncertain` | `unknown_clause` / 低置信 `policy_clause` / 低置信 `invalid_bid_clause` |

---

## 6. 下游使用规则

### 6.1 对 parser

优先顺序：

1. 先判主区块
2. 再判条款语义
3. 再赋法律作用和效力标签
4. 模板、导航、噪声优先剥离
5. 判不稳再进入 `mixed_or_uncertain`

### 6.2 对 review planning

应按区激活审查任务，而不是全文件盲打。

例如：

- `qualification`：资格门槛、歧视性门槛、资格与评分重复
- `conformity_review`：无效投标边界、程序性否决、初审范围
- `technical`：技术倾向性、标准引用、参数一致性
- `scoring`：评分量化性、相关性、主观性
- `contract`：付款、验收、违约、保证金、费用转嫁
- `policy_explanation`：中小企业政策口径、价格扣除、政策冲突

### 6.3 对 formal adjudication

formal 层应尽量同区取证：

- 资格问题优先引用 `qualification`
- 符合性/无效投标问题优先引用 `conformity_review`
- 技术问题优先引用 `technical`
- 评分问题优先引用 `scoring`
- 合同问题优先引用 `contract`

### 6.4 对 LLM

LLM 不应取代 parser 主链，只应作为：

- `mixed_or_uncertain` 消解器
- 区和语义冲突的补偿器
- 复杂表格和跨条款上下文的辅助解释器

---

## 7. 当前最关键的边界

最需要长期打稳的边界有：

- `qualification` vs `conformity_review`
- `technical` vs `scoring`
- `policy_explanation` vs `template`
- `contract` vs `business`

其中当前优先级最高的是：

1. `conformity_review`
2. `policy_explanation`
3. 持续压缩 `mixed_or_uncertain`

---

## 8. 当前版本建议

从本体演进看，后续最顺的任务是：

1. 把 `review_procedure` 语义链接进 `LegalFactCandidate`
2. 让 planning 显式消费 `conformity_review`
3. 让 formal 输出能区分：
   - 资格门槛
   - 符合性否决
   - 初审程序
   - 投标无效后果

这样 parser 本体就不只是“设计存在”，而是能真正影响后续正式审查效果。
