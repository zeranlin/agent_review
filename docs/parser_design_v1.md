# `agent_review` parser 方案 v1

## 为什么当前 parser 不够

当前 parser 更接近“文本读取器”：

- `docx` 主要是段落和表格拼接文本
- 章节定位以关键词为主
- 条款抽取仍大量依赖全文关键词扫描

这会导致几个典型问题：

- 同一句话在不同区域含义不同，但 parser 无法区分
- 模板、示例、可选项容易污染正式条款
- 目录项和正文项可能混淆
- 表格中的评分项、参数项和资格材料要求容易丢失结构

## 招标文件的结构特点

政府采购招标文件不是普通长文，而是规则包，通常同时包含：

- 关键信息
- 招标公告
- 投标人须知
- 采购需求
- 评分信息
- 合同条款
- 投标文件格式与附件

同一句“提供检测报告”落在：

- `qualification` 可能是资格门槛
- `scoring` 可能是加分项
- `technical` 可能是参数证明
- `template` 可能只是示例或样式

所以 parser 必须先恢复结构，再解释语义。

## 新 parser 阶段

建议分为 7 个阶段：

1. `source_parsing`
2. `layout_normalization`
3. `document_tree_building`
4. `semantic_zone_classification`
5. `effect_tagging`
6. `clause_unit_building`
7. `structured_extraction`

## 中间工件

parser 主链应输出以下工件：

- `RawBlock`
- `RawTable`
- `DocumentNode`
- `SemanticZone`
- `EffectTagResult`
- `ClauseUnit`

建议落盘：

- `raw_blocks.json`
- `document_tree.json`
- `semantic_zones.json`
- `effect_tags.json`
- `clause_units.json`

## 本体与 parser 的映射关系

parser 的任务不是直接判断违规，而是把文档映射到轻量本体对象：

- 节点 -> `DocumentNode`
- 区域 -> `SemanticZone`
- 效力 -> `EffectTagResult`
- 审查单元 -> `ClauseUnit`

后续规则只消费这些结构化对象，不再直接扫全文。

## LLM 的参与边界

LLM 只用于低置信语义判定，不接管 parser 主流程。

适合使用 LLM 的地方：

- 区域分类低置信节点
- 模板/正式条款冲突节点
- 复杂评分表行的语义分类

不适合使用 LLM 的地方：

- 文件格式解析
- 标题层级构建
- 原文锚点生成
- 最终法律定性

## 与现有 pipeline 的兼容策略

第一阶段先做到：

- 新对象入模
- `docx_parser` 输出块级和表格级信息
- 保持 `ParseResult.text` 和 `ParseResult.tables` 兼容

后续阶段再将：

- 文档树
- 区域分类
- 效力标签
- 条款单元

逐步接入 `ReviewPipeline`。
