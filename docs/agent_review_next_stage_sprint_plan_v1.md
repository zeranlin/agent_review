# agent_review 下一阶段 Sprint 任务清单 v1

这份清单把下一阶段工作按 Sprint 1 到 Sprint 5 展开成可开发任务包。目标不是一次性做大，而是把本体、parser、任务库、harness 与评测闭环逐步打稳。

## Sprint 1：本体与契约收口

### 目标

- 固化轻量本体和阶段接口，避免术语继续分散。

### 任务包

1. 轻量本体 v2 收口
- 梳理 `Document / SemanticZone / ClauseUnit / EffectTag / Evidence / ReviewPoint / FormalAdjudication` 的统一术语。
- 明确 zone taxonomy、effect taxonomy、evidence taxonomy、formal disposition taxonomy。
- 更新仓库事实源文档，使术语与代码一致。

2. 数据契约稳定化
- 固化 `DocumentProfile / DomainProfile / ReviewPlanningContract / HeaderInfo` 字段定义。
- 明确哪些字段属于 parser 输出、哪些字段属于 planning 输出、哪些字段属于 adjudication 输出。
- 为新契约补最小单测和样例。

3. HeaderInfo 体系扩展
- 在 `HeaderInfo Resolver` 上补 `项目编号 / 采购代理机构 / 预算金额 / 最高限价`。
- 定义头部字段候选排序规则、模板污染过滤规则、优先 zone 规则。
- 为 `reviewer_report` 之外的输出层预留统一调用入口。

### 验收标准

- 契约文档与代码字段一致。
- 头部信息抽取具备独立入口和测试覆盖。
- 术语不再在 `reporting / parser / review logic` 中重复发明。

## Sprint 2：Parser 语义层补强

### 目标

- 把“未知文件可理解”作为 parser 主目标，而不是只做格式提取。

### 任务包

1. document tree 增强
- 补章节标题、表格、列表、附件、目录、页眉页脚、声明函模板的结构识别。
- 统一 node/path/anchor 生成策略，保证后续 evidence 可回指。

2. zone classification 提升
- 优化 `资格 / 技术 / 评分 / 商务 / 合同 / 模板 / 附件 / 其他` 分类精度。
- 增加跨区域混合段识别，降低“同句错区”带来的误报。
- 为真实复杂样本补回归集。

3. ClauseUnit & table semantic parsing
- 强化表格行到 `ClauseUnit` 的切分。
- 重点补评分表、商务要求表、合同条款表、资格条款表。
- 降低整行长串被误识别成多个无关字段的问题。

4. effect tagging 增强
- 细化 `binding / scoring / template / appendix_reference / policy / explanation / noise` 等 tag。
- 把 effect tag 正式接进 header、planning、quality gate 使用链路。

5. evidence alignment / anchor normalization
- 统一 `line / table / paragraph / block` 锚点格式。
- 让 evidence 和 reviewer/formal 报告引用的定位口径一致。

### 验收标准

- 对未知 pdf/docx 样本，zone 与 ClauseUnit 结果可稳定回看。
- 评分表、合同条款、模板段的误切率下降。
- evidence 引用位置在不同输出里一致。

## Sprint 3：审查点任务库重组

### 目标

- 把现有 70+ 审查点从“散规则”改造成“任务库”。

### 任务包

1. 风险母题层建设
- 把审查点映射到母题：评分不规范、项目属性错配、中小企业政策、限制竞争、合同履约、模板残留、一致性等。
- 让 planning 激活的是“母题 + 审查点组合”，而不是平铺的 70+ 点。

2. 审查点元数据补全
- 为每个审查点补齐：
- `适用前提`
- `目标 zone`
- `必需字段`
- `证据模式`
- `常见反证`
- `是否允许 formal include`
- `推荐 legal basis hint`

3. DomainProfile / Lexicon / EvidencePattern
- 建立领域词典和证据模式层。
- 区分家具、通用货物、通用服务、合同重、信息化、林业等画像候选。
- 让新品目优先通过领域词典扩展，而不是新开专项主线。

4. unknown document routing
- 当文档画像置信度不足或领域候选分散时，走 unknown routing。
- 激活 unknown fallback 审查点和抽取字段。

### 验收标准

- 70+ 审查点具备结构化元数据。
- planning 能基于母题和画像激活任务。
- 未知品目不需要复制新专项逻辑。

## Sprint 4：Harness 编排主链增强

### 目标

- 正式把 harness engineering 变成主链，而不是设计说明。

### 任务包

1. review planning 正式主链化
- 把 `结构画像 -> 激活任务 -> extraction demands` 固定为正式阶段。
- 输出 `ReviewPlanningContract` 作为后续统一输入。

2. extraction demands 分层
- 把字段需求分成：
- `基础必抽`
- `任务必需`
- `可选增强`
- `unknown fallback`
- 将现有抽取逻辑切换为 planning 定向抽取优先。

3. applicability + quality gate 增强
- 补目标 zone 检查、模板污染过滤、证据强度判断、重复点合并。
- 降低样品条款、声明函模板、说明性文本误入 formal 的概率。

4. formal adjudication 标准化
- 稳定四类输出：
- `confirmed_issue`
- `warning`
- `missing_evidence`
- `manual_review_required`
- 明确何时必须升级人工。

### 验收标准

- 审查任务激活范围明显收窄。
- formal 输出不再依赖全量粗放抽取。
- 模板误报率与跨区误判率下降。

## Sprint 5：LLM 与评测闭环

### 目标

- 让本地 qwen 成为“高价值增强器”，而不是主判断器；同时建立稳定评测闭环。

### 任务包

1. LLM 高价值字段链路
- 只把 planning 后的高价值字段送入 LLM。
- 区分 `任务必需字段` 与 `可选增强字段`，控制 prompt 体积。
- 继续优化 timeout / watchdog / fallback 行为。

2. 二审与纠偏
- 把评分语义复核、动态任务、review point second review 继续接入 formal 前链路。
- 对证据错位、主证据失准、模板误命中做二审降级。

3. artifact / trace / regression 增强
- 持续输出 `evaluation_summary / enhancement_trace / review_point_trace / llm_tasks`。
- 在 unknown sample regression 中纳入 planning、prompt、llm duration、dynamic task 等指标。

4. baseline manifest 与真实样本回归
- 固化 8 到 12 个未知品目真实样本 baseline。
- 建立升级前后 `batch_summary` 对比口径。
- 明确哪些指标用于观察 parser 漂移，哪些指标用于观察 adjudication 漂移。

### 验收标准

- 本地 qwen 在 1800 秒预算内可稳定跑增强链，超时能安全回退。
- regression 输出能直接对比 planning / prompt / llm / formal 变化。
- Sprint 迭代可用 baseline diff 评估收益与回归风险。

## 推荐实施顺序

1. 先做 Sprint 1  
原因：先把术语和契约打稳，避免后面反复返工。

2. 再做 Sprint 2  
原因：parser 是未知文件主挑战的基础设施。

3. 接着做 Sprint 3  
原因：任务库不稳，planning 就会失焦。

4. 然后做 Sprint 4  
原因：只有 parser 和任务库稳定后，review planning / formal adjudication 才能真正收敛。

5. 最后做 Sprint 5  
原因：等主链稳定后再做 LLM 与评测闭环，收益最大，也更容易看出改动效果。
