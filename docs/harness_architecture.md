# 架构设计

## 设计目标

目标不是做一个“一次性判断是否合规”的 prompt。

目标是把 SOP 变成一个可执行的审查 harness，让智能体在固定轨道上工作：

- 仓库存放流程、维度、规则、输出模式和升级策略
- 运行时按阶段推进，不跳步
- 每一步都产出结构化工件，供下一步验证
- 只有当法律判断或材料缺失无法自动核实时，才升级给人工

这对应 harness engineering 的核心思想：工程师设计环境、约束、反馈回路，让智能体稳定完成工作，而不是押注一次性提示词。

## 分层架构

### 1. 业务层

业务层负责回答“为什么审、审什么、结论怎么用”：

- 识别采购文件类型
- 确定审查边界
- 定义高风险优先级
- 规定输出结论层级
- 规定问题必须有条款出处和修改建议

### 2. 编排层

编排层负责回答“按什么顺序执行 SOP”：

1. 文件解析
2. 类型识别
3. 章节定位
4. 条款抽取
5. 风险匹配
6. 一致性检查
7. 风险分级
8. 结论生成
9. 修改建议输出

### 3. 能力层

能力层负责提供可复用能力：

- 文本提取
- OCR
- 章节索引
- 规则匹配
- 跨条款对比
- 风险分级
- 报告渲染

### 4. 数据层

数据层负责保存审查工件：

- 文件基础信息
- 章节索引表
- 条款抽取表
- 风险命中表
- 一致性检查表
- 结论与建议表

## 核心原则

### 1. Humans steer, agents execute

In this domain, humans define:

- the legal and policy basis for review
- which procurement risks matter most
- severity thresholds
- when an issue must be escalated for legal or supervisory review

Agents execute:

- document decomposition
- evidence extraction
- clause-level screening
- contradiction detection
- report drafting
- iterative self-review

### 2. Repository knowledge is the system of record

The repository should eventually hold:

- review dimensions
- output schemas
- escalation thresholds
- rule references
- test fixtures and acceptance examples

This is better than keeping all domain knowledge inside a single prompt because the harness can inspect, validate, and evolve it.

### 3. Legibility first

The agent should be able to inspect:

- the original tender text
- extracted sections and pagination anchors
- rule basis used for each conclusion
- unresolved ambiguities
- missing attachments or missing clauses

If the system cannot expose these artifacts, it cannot reliably review or defend its conclusions.

### 4. Enforce boundaries centrally

The review harness should separate:

- ingestion
- review planning
- rule execution
- evidence validation
- adjudication
- reporting

This prevents a single component from silently inventing legal conclusions without evidence.

### 5. Use loops, not single-pass generation

The review runtime should loop until:

- required dimensions were checked
- each finding has evidence
- contradictions were resolved or escalated
- the final report includes confidence and next actions

## 控制回路

```text
用户提交采购文件
  -> 文件解析
  -> 类型识别与范围声明
  -> 章节定位
  -> 条款抽取
  -> 风险规则匹配
  -> 跨条款一致性检查
  -> 风险分级
  -> 结论生成
  -> 问题-建议映射
  -> 输出报告
```

## 智能体角色分工

系统扩展后，可从单编排器演进为多角色智能体：

1. `document_ingestor`
   解析 PDF、DOCX、扫描件并输出结构化文本。
2. `scope_classifier`
   识别文件类型并生成审查边界。
3. `clause_extractor`
   定位章节并抽取关键条款。
4. `risk_reviewer`
   对限制竞争、评分、合同、政策等风险进行匹配。
5. `consistency_auditor`
   做跨条款一致性检查。
6. `adjudicator`
   汇总风险并形成结论等级。
7. `report_writer`
   输出标准审查报告和问题-建议对应表。

## 当前实现与目标架构的对应关系

- [engine.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/engine.py) 负责 SOP 主编排
- [models.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/models.py) 负责审查工件契约
- [checklist.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/checklist.py) 负责维度配置
- [reporting.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/reporting.py) 负责报告渲染
- [docs/business_design.md](/Users/linzeran/code/2026-zn/agent_review/docs/business_design.md) 负责业务口径
- [docs/dimension_design.md](/Users/linzeran/code/2026-zn/agent_review/docs/dimension_design.md) 负责维度口径

## 升级策略

以下情况必须升级人工：

- 证据不完整或前后矛盾
- 结论依赖地方性规范理解，仓库里尚未编码
- 关键附件缺失
- 高风险问题存在但材料不足以直接定性

## 工件契约

每次运行至少输出：

- 文件基础信息
- 审查范围说明
- 章节位置索引
- 条款抽取表
- 风险命中表
- 一致性检查表
- 主要问题
- 相对规范项
- 修改建议
- 人工复核清单
