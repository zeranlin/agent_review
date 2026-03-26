# `agent_review` Unknown Document First Sprint 清单 v1

这份清单把“未知招标文件优先处理主链”拆成 Sprint 1 到 Sprint 4 的可开发任务。目标不是继续平铺补规则，而是把：

`未知文件 -> 结构画像 -> 任务激活 -> 定向抽取 -> 审查裁定 -> 评测回归`

做成稳定闭环。

---

## 总体原则

1. parser 主体仍然以规则与结构恢复为主，不允许依赖 LLM 才能运行。
2. LLM 只用于低置信度歧义消解、unknown routing 辅助和高价值字段增强。
3. 对未知文件优先走 conservative routing，不默认平铺激活全部审查点。
4. planning 必须决定 extraction，而不是 extraction 先做完再回头解释 planning。
5. 所有行为变化都要进入 regression baseline 和 trace。

---

## Sprint 1：Unknown Routing 收口

### 目标

- 把 unknown document 从“若干 flags”升级成真正影响主链的 routing 决策。

### 可直接开发任务

1. `DocumentProfile` unknown 信号收口
- 梳理并稳定 `unknown_procurement_kind / mixed_zone_dense / template_appendix_mix / low_structure_confidence` 等信号。
- 明确哪些信号来自 parser，哪些来自 profile 推导。
- 输出统一 unknown 信号摘要。

2. parser-assist 接入 profile 主链
- 将 `ParserSemanticTrace` 中的 `activated / candidate_count / applied_count / warnings` 接入 `DocumentProfile` 摘要或 routing 输入。
- 明确 parser-assist 不直接激活审查点，只影响置信度与 route tags。

3. unknown routing policy
- 新增 conservative routing 规则：
- unknown 文件下优先保留 `结构 / 模板 / 附件 / 评分 / 合同 / 政策基础` 母题
- 对强领域依赖、强专项依赖任务降低默认激活优先级
- 输出 `routing_reason / suppressed_families / promoted_families`

4. routing trace 落盘
- 在 artifact / evaluation summary 中输出：
- unknown 是否命中
- 命中了哪些 unknown flags
- route tags 来源
- 是否触发 parser-assist

### 重点文件

- [src/agent_review/structure/document_profile.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/structure/document_profile.py)
- [src/agent_review/structure/parser_semantic_assist.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/structure/parser_semantic_assist.py)
- [src/agent_review/pipeline.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/pipeline.py)
- [src/agent_review/outputs/artifacts.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/outputs/artifacts.py)

### 验收标准

- unknown 文件有明确 routing 策略，而不是仅挂几个 flags。
- parser-assist 结果能进入 routing。
- 输出中可回看 unknown routing 的触发原因。

---

## Sprint 2：Planning 定向化

### 目标

- 把 `DocumentProfile -> ReviewPlanningContract` 做成真正的任务激活器。

### 可直接开发任务

1. 母题优先激活
- 先激活 `risk_family`，再在母题内部选择具体 review points。
- unknown 文件下限制一次性激活过多 review points。
- 增加“抑制原因”记录。

2. planning summary 结构化
- 输出：
- `activated_risk_families`
- `suppressed_risk_families`
- `activation_reasons`
- `target_zones`
- `planned_catalog_ids`

3. extraction demands 三档化
- 将需求字段固定拆分为：
- `base_required_extraction_demands`
- `task_enhancement_extraction_demands`
- `unknown_fallback_extraction_demands`
- 保证三档之间含义稳定、可测。

4. high-value field 口径统一
- 明确哪些字段可进入后续 LLM 高价值上下文。
- planning 输出中加入高价值字段清单。

### 重点文件

- [src/agent_review/pipeline.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/pipeline.py)
- [src/agent_review/review_point_catalog.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/review_point_catalog.py)
- [src/agent_review/models.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/models.py)

### 验收标准

- planning 能解释“为什么激活这些点、为什么没激活那些点”。
- unknown 文件下激活范围明显收窄。
- extraction demands 三档在输出与测试中都可见。

---

## Sprint 3：Planning 驱动抽取

### 目标

- 让抽取器从“全量广撒网”切换为“按 planning 定向抽取”。

### 可直接开发任务

1. ClauseUnit 定向优先
- 按 `target_zones` 优先筛选 ClauseUnit。
- 按 `required_fields` 优先抽取。
- 不足时再走全文回退抽取。

2. unknown fallback 抽取兜底
- 为 unknown 文件保留最小安全兜底字段，例如：
- 项目属性
- 采购标的
- 资格要求
- 评分方法
- 评分项
- 合同付款
- 验收
- 模板/附件引用

3. extraction trace
- 输出：
- demand 总数
- demand 命中数
- 按档位命中率
- 触发了哪些回退抽取

4. parser-assist 影响抽取优先级
- 若 parser-assist 修正 zone / effect，则优先使用修正后的 ClauseUnit 参与抽取。

### 重点文件

- [src/agent_review/extractors/clauses.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/extractors/clauses.py)
- [src/agent_review/pipeline.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/pipeline.py)
- [src/agent_review/outputs/artifacts.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/outputs/artifacts.py)

### 验收标准

- 抽取结果能体现 planning 的定向作用。
- unknown 文件下 fallback 可兜底但不过度膨胀。
- 可在 trace 中看见“抽取为什么成功/为什么回退”。

---

## Sprint 4：Unknown Regression 与闭环评测

### 目标

- 为未知文件主链建立真正的评测与回归抓手。

### 可直接开发任务

1. unknown sample manifest v2
- 扩展到 8-12 个样本。
- 至少覆盖：
- 通用货物
- 通用服务
- 混合采购
- 附件驱动
- 模板污染高
- 评分密集型
- 合同密集型

2. regression 指标扩展
- 增加：
- parser-assist activated/applied ratio
- unknown routing hit ratio
- planning activation count
- suppression count
- extraction demand hit ratio
- high-value field count
- LLM prompt volume 变化

3. 升级前后对比输出
- 生成 baseline diff：
- planning 变化
- formal 数量变化
- quality gate 分布变化
- LLM 耗时变化

4. 回归异常分层
- 区分 parser 漂移、planning 漂移、adjudication 漂移、LLM 漂移。
- 输出最小定位摘要，便于回修。

### 重点文件

- [src/agent_review/eval/unknown_sample_regression.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/eval/unknown_sample_regression.py)
- [src/agent_review/outputs/artifacts.py](/Users/linzeran/code/2026-zn/agent_review/src/agent_review/outputs/artifacts.py)
- [docs/unknown_sample_regression_manifest_v1.txt](/Users/linzeran/code/2026-zn/agent_review/docs/unknown_sample_regression_manifest_v1.txt)

### 验收标准

- unknown regression 能直接反映主链收益和回归风险。
- 可比较升级前后变化，而不只是看“是否通过”。

---

## 依赖顺序

1. `Sprint 1` 必须先落地  
原因：unknown routing 是 planning 的上游。

2. `Sprint 2` 建立在 `Sprint 1` 上  
原因：没有稳定 routing，planning 会继续发散。

3. `Sprint 3` 建立在 `Sprint 2` 上  
原因：抽取必须消费稳定的 planning contract。

4. `Sprint 4` 可以和 `Sprint 3` 后半段部分并行，但最终收口依赖 `Sprint 3`

---

## 并行开发编排

### 并行线 A：profiling-routing

- 对应 Sprint：`Sprint 1`
- 负责：
- unknown flags 收口
- parser-assist -> profile 接入
- conservative routing policy
- 写入范围：
- `structure/document_profile.py`
- `structure/parser_semantic_assist.py`
- `pipeline.py`

### 并行线 B：planning-contract

- 对应 Sprint：`Sprint 2`
- 负责：
- 母题优先激活
- suppression 机制
- extraction demands 三档化
- high-value fields
- 写入范围：
- `pipeline.py`
- `models.py`
- `review_point_catalog.py`

### 并行线 C：targeted-extraction

- 对应 Sprint：`Sprint 3`
- 负责：
- ClauseUnit 定向抽取
- unknown fallback 抽取
- extraction trace
- 写入范围：
- `extractors/clauses.py`
- `pipeline.py`
- `outputs/artifacts.py`

### 并行线 D：eval-regression

- 对应 Sprint：`Sprint 4`
- 负责：
- unknown regression manifest v2
- 指标扩展
- baseline diff
- 写入范围：
- `eval/unknown_sample_regression.py`
- `outputs/artifacts.py`
- `docs/unknown_sample_regression_*`

---

## 推荐执行波次

### 第 1 波

- 先做：并行线 A
- 同时预热：并行线 D 的样本清单整理

### 第 2 波

- 在 A 基础上启动：并行线 B
- D 继续补 baseline

### 第 3 波

- 在 B 基础上启动：并行线 C
- D 接入 planning / extraction 新指标

### 第 4 波

- 主线程统一收口：
- 全量测试
- unknown regression
- 真实样本复跑
- 产出升级前后对比

---

## 当前主线程统筹建议

1. 主线程优先负责 `Sprint 1` 的 routing 收口与接口稳定。
2. `pipeline.py` 是冲突高发区，应由主线程统一集成。
3. 并行开发时，尽量避免两条子线同时改 `pipeline.py` 的同一段。
4. 所有子线最终都要回到 unknown regression 上收口，不接受“只做模块、不进回归”的交付。

