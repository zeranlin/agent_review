# agent_review

`agent_review` 是一个面向政府采购招标文件合规审查的 harness engineering 风格项目骨架。

仓库围绕一个核心原则设计：由人定义政策口径、风险容忍度和验收标准，由智能体执行可重复、可审计的审查循环。

当前版本重点解决以下问题：

- 将采购文件审查拆成清晰、分层、可扩展的智能体工作流
- 让仓库知识成为系统事实来源，而不是依赖单次提示词
- 让每个问题都能回溯到招标文件中的证据
- 让业务流程、系统架构和审查维度与 SOP 对齐
- 提供一个最小可运行 CLI，便于后续扩展为多智能体审查系统

## 为什么这样设计

仓库架构参考了 OpenAI 关于 harness engineering 和 agent loop 的方法：

- 工程师需要设计环境、指定目标、建设反馈回路，而不是只写一次 prompt
- 仓库知识应当成为系统记录中心，而不是依赖一个臃肿的说明文件
- 架构边界和输出契约应集中定义，方便检查和约束
- 审查应当采用循环式执行，包含自查、复核和必要的人工升级

参考资料：

- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)
- [Unrolling the Codex agent loop](https://openai.com/zh-Hans-CN/index/unrolling-the-codex-agent-loop/)

## 仓库结构

```text
docs/
  business_design.md        # 面向 SOP 的业务设计
  dimension_design.md       # 审查维度与风险分类
  harness_architecture.md   # 审查系统架构与控制回路
  review_workflow.md        # 审查流程与升级规则
src/agent_review/
  checklist.py              # 审查维度配置
  engine.py                 # 审查编排入口
  models.py                 # 结构化审查模型
  pipeline.py               # stage pipeline 与共享运行状态
  merge.py                  # 结果去重与归并
  reporting.py              # Markdown/JSON 报告渲染
  cli.py                    # 本地命令行入口
  parsers/                  # 输入与解析层
  structure/                # 文件类型识别、章节定位、范围声明
  extractors/               # 条款抽取层
  rules/                    # 风险规则、注册中心与建议映射
  consistency/              # 一致性检查与结论裁决
  outputs/                  # 报告、专项表和运行索引输出
tests/
  test_engine.py            # 轻量校验测试
AGENTS.md                   # 仓库内智能体协作规则
pyproject.toml              # 包配置与测试配置
```

## 审查模型

招标文件审查主循环与 SOP 的九步流程对齐：

1. 解析采购文件并标准化文本
2. 识别文件类型并声明审查范围
3. 定位关键章节
4. 抽取关键条款
5. 执行规则化风险匹配
6. 执行跨条款一致性检查
7. 进行风险分级
8. 形成总体结论
9. 输出问题与修改建议对应关系

当前仓库已经提供该流程的最小可运行实现，便于在接入模型、OCR、法规知识库之前，先把架构和工件契约跑通。

当前执行链已进一步收敛为明确的 stage pipeline：

1. `document_structure`
2. `clause_extraction`
3. `clause_role_classification`
4. `dimension_review`
5. `rule_evaluation`
6. `consistency_review`
7. `review_point_assembly`
8. `applicability_check`
9. `review_quality_gate`
10. `formal_adjudication`
11. `finalize_report`

这样 `engine.py` 只负责装配输入源、触发 pipeline 和控制 LLM 增强，规则扩展和结果归并不再散落在主编排代码里。

其中新增的 `clause_role_classification` 会对条款标注角色，例如采购约束条款、投标文件模板、政策说明、定义说明、附件引用等，用于后续降低模板误报。

当前还新增了 3 个“审查点驱动”核心骨架：

- `ReviewPoint`：以审查点为核心组织问题，而不是直接围绕单条 finding 输出
- `EvidenceBundle`：为每个审查点汇总直接证据、辅助证据、冲突证据、反证、缺失证据和条款角色
- `FormalAdjudication`：在正式意见输出前，单独记录该审查点是进入正式意见、待人工确认还是被过滤
- `ApplicabilityCheck`：围绕审查点的法规要件、排除条件和适法性判断
- `ReviewQualityGate`：围绕模板噪音、弱证据和重复问题的质量关卡
- `ReviewPointCatalog`：为高频审查点提供标准化目录、要件和场景标签

当前内部主链也已开始切换为“`ReviewPoint` 优先”：

- 维度筛查层优先产出 `ReviewPoint`
- 规则层优先产出 `ReviewPoint`
- 一致性层优先产出 `ReviewPoint`
- `Finding` 不再作为这两层的第一产物，而是在汇总阶段由 `ReviewPoint` 统一回写，以兼容既有报告、意见书和 JSON 输出
- `formal_adjudication` 直接围绕 `ReviewPoint + EvidenceBundle + ApplicabilityCheck + ReviewQualityGate` 做正式裁决，不再依赖回写后的 `Finding`

当前规则执行采用“双层规则架构”：

- 核心必跑规则：始终执行，覆盖通用风险、政策口径和模板冲突
- 场景增强规则：根据项目属性、合同特征和少量场景标签做增强检查

这意味着场景识别不会成为是否审查的总开关，只会影响专项规则的增强深度。

当前也已支持“多文件联合审查”入口，可把正文、采购需求附件、评分细则、合同草案一起送入同一审查上下文。系统会：

- 先分别解析每个文件
- 再合并成统一文本上下文
- 最终在同一份报告中保留联合文件清单和统一审查结论

在此基础上，当前还会显式执行“跨文件一致性专项”，重点检查：

- 正文 vs 评分细则
- 正文 vs 合同草案

当前版本还引入了“法规依据层”最小实现：

- 常见风险命中会自动挂接结构化法规依据
- 一致性问题会同步挂接对应规范依据
- Markdown 和 JSON 输出中都可直接看到“法规依据”

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m agent_review.cli --input sample.txt --format markdown
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest
```

## 当前范围

当前版本不直接代替正式法律意见。

它已经提供：

- 结构化的合规审查流程
- 带严重程度、置信度、理由和证据的审查结果模型
- 文件类型、审查范围、章节索引、条款抽取、风险命中和一致性检查工件
- 可复用的审查维度清单
- 最小 CLI 和测试集

当前版本尚未提供：

- 完整法规知识库检索与地方口径差异化适配
- 针对地方采购规范的自动比对

这些能力将作为后续层继续叠加到现有 harness 上。

## 当前解析能力

当前版本已接入基础真实文件解析能力：

- `txt` / `md`：直接文本读取
- `docx`：段落和表格抽取
- `pdf`：使用 `pypdf` 提取页文本，并对 PDF 内嵌图片执行 OCR 补充
- 图片文件：使用 `pytesseract` 执行 OCR

当前 OCR 增强已包含：

- 图片预处理
- 多轮 OCR 尝试
- 图片表格型内容的结构化抽取
- PDF 内嵌图片 OCR 补充
- 基于视觉模型的图片类型与关键信息增强识别

注意：

- 当前环境如果没有安装 `tesseract` 可执行程序，图片 OCR 会返回 warning，但不会让整次审查失败。
- `.doc` 仍建议先转换为 `.docx` 或 PDF 后再审查。

## LLM 增强

当前版本已提供一个最小可用的 LLM 增强层，默认不启用。

启用后，LLM 会围绕 7 个关键节点做语义增强，包括：

- 条款抽取后的语义补全，补抓规则未显式抽出的隐含条款事实
- ReviewPoint 的条款角色复核，识别模板、定义说明、附件引用等角色误判
- ReviewPoint 的证据复核，识别证据是否充分、是否仍缺关键直接证据
- ReviewPoint 的适法性复核，识别法规要件是否真正成立
- 专项规则后的语义复核，补抓近似但未命中的专项风险
- 一致性矩阵后的深层冲突分析，补抓跨章节、跨表格、跨措辞的隐性矛盾
- 高风险结论前的裁决复核，提示是否仍存在未被规则覆盖的实质性风险

同时，LLM 还会继续输出：

- 基于专项表和语义复核结果的总体结论摘要
- 对修改建议的定向优化
- 项目结构、中小企业政策、人员与用工边界、合同履约、模板冲突 5 张专项表摘要
- 对语义补充结果做“可直接采用 / 需人工确认”的分级

当前 LLM 结果分级规则：

- 规则链直接产出的结果默认视为 `rule_based`
- LLM 语义补充结果会标记为 `可直接采用` 或 `需人工确认`
- 标记为 `需人工确认` 的补充结果会自动进入待确认问题单

运行模式：

- `fast`：只跑确定性主链路，快速生成基础报告
- `enhanced`：先生成基础报告，再调用 LLM 增强总体结论和修改建议

启用方式：

```bash
PYTHONPATH=src python -m agent_review.cli --input examples/sample_tender.txt --format markdown --mode fast
PYTHONPATH=src python -m agent_review.cli --input examples/sample_tender.txt --format markdown --mode enhanced --use-llm
```

默认会读取以下配置；如未设置，则回退到当前本地预设：

- `AGENT_REVIEW_LLM_BASE_URL`
- `AGENT_REVIEW_LLM_MODEL`
- `AGENT_REVIEW_LLM_API_KEY`
- `AGENT_REVIEW_LLM_TIMEOUT`

当前本地预设为：

- Base URL: `http://112.111.54.86:10011/v1`
- Model: `qwen3.5-27b`

## 双产物输出

每次运行默认都会输出两份产物到 `runs/<文件名>/`：

- `base_report.json`
- `base_report.md`
- `enhanced_report.json`
- `enhanced_report.md`
- `opinion_letter.md`
- `formal_review_opinion.md`
- `run_manifest.json`
- `llm_tasks.json`
- `high_risk_review_checklist.json`
- `pending_confirmation_items.json`
- `project_structure_table.base.json`
- `project_structure_table.json`
- `sme_policy_table.base.json`
- `sme_policy_table.json`
- `personnel_boundary_table.base.json`
- `personnel_boundary_table.json`
- `contract_performance_table.base.json`
- `contract_performance_table.json`
- `template_conflicts_table.base.json`
- `template_conflicts_table.json`

其中：

- 在 `fast` 模式下，基础报告和最终报告内容相同
- 在 `enhanced` 模式下，基础报告保留确定性结果，增强报告叠加 LLM 输出

这样即使 LLM 超时或失败，也不会影响基础报告交付。

`run_manifest.json` 会统一记录：

- 本次运行的文件名、模式和结论
- 解析摘要
- 各 stage 执行状态
- 报告、专项表和人工复核产物的落盘路径

`llm_tasks.json` 会单独记录 7 个 LLM 语义子任务状态：

- `llm_clause_supplement`
- `llm_specialist_review`
- `llm_consistency_review`
- `llm_verdict_review`

每个任务都会显式标记为 `pending`、`running`、`completed`、`failed`、`timed_out` 或 `skipped`，便于人工判断增强链路是否完整执行。

人工复核相关产物包括：

- `high_risk_review_checklist.json`：从高风险/严重风险问题自动汇总出的复核清单
- `pending_confirmation_items.json`：汇总所有“需人工确认”的 LLM 语义补充结果与基础人工复核项
- `opinion_letter.md`：面向正式流转的审查意见书模板文本
- `formal_review_opinion.md`：按“问题标题、条款位置、原文摘录、问题类型、风险等级、合规判断、法律/政策依据”结构输出的高风险正式审查意见

`formal_review_opinion.md` 在输出前会经过正式出具过滤：

- 仅保留高风险问题
- 要求存在较强证据锚点
- 会过滤模板文本、定义说明、附件引用等弱证据来源
- 会校验问题标题与原文摘录是否基本一致
