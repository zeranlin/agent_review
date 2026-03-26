# `agent_review` parser 第二阶段收口与评测说明

## 目的

这份说明用于把 parser、`ClauseUnit`、`effect_tags` 和回归测试的第二阶段能力收拢成仓库事实源，便于后续继续扩展时保持判断口径稳定。

## 当前已落地的事实链

当前 parser 主链不再只是“文本拼接器”，而是按下面顺序产出结构化工件：

`RawBlock` / `RawTable` -> `DocumentNode` -> `SemanticZone` -> `EffectTagResult` -> `ClauseUnit`

这些工件随后会被后续流程消费：

`ClauseUnit` 优先抽取 -> 质量门 -> 正式裁定 -> 报告输出

## 需要优先识别的招标文件区域

政府采购招标文件中，下面几类区域最容易互相混淆：

- 模板与正式条款
- 附件引用与正文要求
- 评分表与资格条件
- 商务要求与技术要求
- 目录项与正文项

parser 的目标不是直接做合规判断，而是先把这些区域稳定位，再把条款效力和审查单元交给后续环节。

## 第二阶段回归覆盖面

本阶段回归测试优先覆盖以下场景：

| 场景 | 期待结果 |
| --- | --- |
| 模板文本 | 被识别为 `template` 区域或弱效力条款，不应直接当作正式条款 |
| 附件/附表引用 | 被识别为 `appendix_reference` 或 `reference_only` |
| 评分表 | 表头与评分行保持结构，评分区域进入 `scoring` |
| 资格条件 | 保持 `qualification` 区域，不与模板混淆 |
| 商务/技术区 | `business` 与 `technical` 需要分开，不应只靠全文关键词判断 |

## 评测约束

- 只要区域或效力信号不稳定，就应进入人工复核，不要硬判
- `ClauseUnit` 优先不等于 `ClauseUnit` 独占，全文补位仍然保留
- 模板/示例/引用性内容只能在证据足够时参与后续裁定
- 评分表、资格条件和商务/技术要求要优先看结构位置和表格锚点

## 对应回归文件

- [tests/test_parser_second_phase_regression.py](/Users/linzeran/code/2026-zn/agent_review/tests/test_parser_second_phase_regression.py)
- [tests/test_clause_unit_pipeline_and_quality.py](/Users/linzeran/code/2026-zn/agent_review/tests/test_clause_unit_pipeline_and_quality.py)
- [tests/test_zone_classifier.py](/Users/linzeran/code/2026-zn/agent_review/tests/test_zone_classifier.py)
- [tests/test_effect_tagger.py](/Users/linzeran/code/2026-zn/agent_review/tests/test_effect_tagger.py)
