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
  engine.py                 # 审查编排主循环
  models.py                 # 结构化审查模型
  reporting.py              # Markdown/JSON 报告渲染
  cli.py                    # 本地命令行入口
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

- OCR / PDF 解析
- 直接的 LLM 集成
- 来自法规知识库的法条检索
- 针对地方采购规范的自动比对

这些能力将作为后续层继续叠加到现有 harness 上。
