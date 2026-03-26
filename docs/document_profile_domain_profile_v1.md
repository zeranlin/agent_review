# `DocumentProfile / DomainProfile` 数据契约草案 v1

## 目标

为 `agent_review` 的“未知招标文件优先”流程提供稳定的数据契约，使系统在面对从未见过的文件时，仍能先完成：

- 文档画像
- 通用风险语义识别
- 领域 profile 增强
- 证据质量控制
- 可回灌的审查 trace

这两个对象不是最终审查结论，而是位于 `ClauseUnit` 与 `ReviewPoint` 之间的中间认知层。

## 设计原则

1. `DocumentProfile` 描述“这份文件像什么”。
2. `DomainProfile` 描述“系统已知的某类领域经验包”。
3. `DocumentProfile` 来自当前文件事实。
4. `DomainProfile` 来自仓库沉淀知识。
5. 文件先生成 `DocumentProfile`，再匹配 `DomainProfile`。
6. 任何领域增强都不能绕开通用风险框架。

## 一、`DocumentProfile`

### 定义

`DocumentProfile` 是单次审查中、针对当前文件自动生成的结构化画像。

它回答：

- 这份文件更像货物、服务、工程还是混合采购
- 主要结构区域分布如何
- 模板、附件、评分表、合同条款的密度如何
- 当前是否存在高噪声、高模板污染、高表格依赖等风险
- 下一步应该优先激活哪些风险语义簇

### 建议字段

```python
DocumentProfile(
    document_id: str,
    source_path: str,
    procurement_kind: str,
    procurement_kind_confidence: float,
    domain_profile_candidates: list[DomainProfileCandidate],
    dominant_zones: list[ZoneStat],
    effect_distribution: list[EffectStat],
    clause_semantic_distribution: list[ClauseSemanticStat],
    structure_flags: list[str],
    risk_activation_hints: list[str],
    quality_flags: list[str],
    unknown_structure_flags: list[str],
    representative_anchors: list[str],
    summary: str,
)
```

### 字段说明

#### `procurement_kind`

建议枚举：

- `goods`
- `service`
- `engineering`
- `mixed`
- `unknown`

#### `domain_profile_candidates`

表示当前文件可能匹配的领域候选，按置信度排序。

```python
DomainProfileCandidate(
    profile_id: str,
    confidence: float,
    reasons: list[str],
)
```

首批建议候选：

- `generic_goods`
- `generic_service`
- `mixed_procurement`
- `furniture`

#### `dominant_zones`

记录语义区分布。

```python
ZoneStat(
    zone_type: str,
    node_count: int,
    unit_count: int,
    ratio: float,
)
```

#### `effect_distribution`

记录条款效力分布。

```python
EffectStat(
    effect_tag: str,
    unit_count: int,
    ratio: float,
)
```

#### `clause_semantic_distribution`

记录条款语义类型分布。

```python
ClauseSemanticStat(
    clause_semantic_type: str,
    unit_count: int,
    ratio: float,
)
```

#### `structure_flags`

首批建议支持：

- `heavy_scoring_tables`
- `heavy_template_pollution`
- `heavy_appendix_reference`
- `heavy_contract_terms`
- `mixed_structure_signals`
- `fragmented_table_text`
- `catalog_noise_present`

#### `risk_activation_hints`

不是最终结论，而是“推荐优先激活的风险族”。

例如：

- `competition_restriction`
- `qualification_scoring_boundary`
- `scoring_quantification`
- `contract_performance`
- `sme_policy_consistency`
- `template_conflict`

#### `quality_flags`

描述当前文件处理质量风险。

例如：

- `table_anchor_unstable`
- `template_ratio_high`
- `cross_zone_clause_conflict`
- `long_flattened_rows`
- `low_direct_binding_ratio`

#### `unknown_structure_flags`

描述系统当前还没完全理解的结构问题。

例如：

- `unclassified_dense_table`
- `unknown_appendix_like_block`
- `mixed_scoring_contract_cluster`
- `unknown_domain_lexicon_gap`

### 构建输入

`DocumentProfile` 应主要基于：

- `ParseResult`
- `DocumentNode`
- `SemanticZone`
- `EffectTagResult`
- `ClauseUnit`
- 已抽取的基础 `ExtractedClause`

### 构建方式

优先顺序：

1. 规则统计
2. 结构特征推断
3. LLM 对低置信部分补充

LLM 只能输出增量解释，不直接覆盖确定性统计值。

## 二、`DomainProfile`

### 定义

`DomainProfile` 是仓库内沉淀的领域经验包，不依赖单份文件。

它回答：

- 某类采购文件常见的结构模式是什么
- 常见风险语义和证据模式是什么
- 常见误报来源是什么
- 应如何增强 review point activation、evidence alignment 和 false positive suppression

### 核心定位

`DomainProfile` 不是“品目专项代码分支”，而是：

- 领域词典
- 证据模式
- 常见误报模式
- 风险激活加权规则

### 建议字段

```python
DomainProfile(
    profile_id: str,
    display_name: str,
    version: str,
    applies_to_procurement_kinds: list[str],
    trigger_keywords: list[str],
    negative_keywords: list[str],
    risk_lexicon_pack_id: str,
    evidence_pattern_pack_id: str,
    false_positive_pack_id: str,
    preferred_risk_families: list[str],
    preferred_zone_weights: list[ZoneWeight],
    preferred_effect_weights: list[EffectWeight],
    notes: str,
)
```

### 支撑对象

#### `RiskLexiconPack`

```python
RiskLexiconPack(
    pack_id: str,
    terms_by_family: dict[str, list[str]],
    anti_terms_by_family: dict[str, list[str]],
)
```

作用：

- 为领域内常见术语、近义表达、误报排除词提供词汇包

#### `EvidencePatternPack`

```python
EvidencePatternPack(
    pack_id: str,
    primary_patterns: list[EvidencePattern],
    supporting_patterns: list[EvidencePattern],
    weak_patterns: list[EvidencePattern],
)
```

```python
EvidencePattern(
    pattern_id: str,
    risk_family: str,
    expected_zones: list[str],
    expected_effects: list[str],
    signal_groups: list[list[str]],
    anti_signal_groups: list[list[str]],
)
```

作用：

- 指导某领域里什么样的条款组合更像强证据
- 指导什么样的词虽然命中，但更像弱来源或误报

#### `FalsePositivePack`

```python
FalsePositivePack(
    pack_id: str,
    patterns: list[FalsePositivePattern],
)
```

```python
FalsePositivePattern(
    pattern_id: str,
    risk_family: str,
    description: str,
    trigger_signals: list[str],
    weak_zone_constraints: list[str],
    weak_effect_constraints: list[str],
)
```

作用：

- 把真实文件里高频误报沉淀成可复用抑制规则

## 三、两者关系

### 匹配流程

1. 当前文件生成 `DocumentProfile`
2. 根据 `procurement_kind + trigger_keywords + zone/effect 分布` 匹配 `DomainProfile`
3. 取前 `N` 个 profile 候选参与增强
4. 所有增强必须以 `DocumentProfile` 的当前事实为边界

### 约束

1. `DomainProfile` 不能凭空创造事实
2. `DocumentProfile` 不能直接给出法律定性
3. `DomainProfile` 只能影响：
   - risk activation weighting
   - evidence ranking
   - false positive suppression
   - LLM prompt context

## 四、在 pipeline 中的位置

建议放置顺序：

1. `document_structure`
2. `clause_extraction`
3. `document_profiling`
4. `domain_profile_matching`
5. `review_task_planning`
6. `fact_collecting`
7. `applicability`
8. `review_quality_gate`
9. `formal_adjudication`

## 五、LLM 接口建议

### `document_profiling_llm`

输入：

- zone/effect/clause unit 统计摘要
- 代表性章节标题
- 代表性表格标题
- 代表性条款片段

输出：

- `DocumentProfileDelta`

```python
DocumentProfileDelta(
    candidate_procurement_kind: str,
    candidate_domain_profiles: list[str],
    extra_structure_flags: list[str],
    extra_risk_activation_hints: list[str],
    reasons: list[str],
)
```

### `evidence_alignment_llm`

输入：

- review point title
- primary evidence quote
- supporting quotes
- clause unit context
- zone/effect summary

输出：

- `alignment_supported: bool`
- `risk_of_false_positive: float`
- `reason`

## 六、落盘工件建议

建议新增：

- `document_profile.json`
- `domain_profile_match.json`
- `unknown_structure_trace.json`
- `false_positive_trace.json`

## 七、首批实现建议

### `DocumentProfile` v1 必做

1. `procurement_kind`
2. `domain_profile_candidates`
3. `dominant_zones`
4. `effect_distribution`
5. `structure_flags`
6. `risk_activation_hints`
7. `quality_flags`

### `DomainProfile` v1 必做

1. `generic_goods`
2. `generic_service`
3. `mixed_procurement`
4. `furniture`

### v1 落地说明

当前仓库中的第一版实现采用“静态 profile 目录 + 规则匹配”的方式落地：

1. `DocumentProfile` 由当前文件文本与已抽取条款共同生成。
2. `DomainProfile` 作为仓库沉淀知识包，提供词汇、证据模式与风险激活偏好。
3. `review_point_catalog` 会把 profile 候选带来的激活标签并入现有结构化标签。
4. `generic_goods / generic_service / mixed_procurement / furniture` 是第一批最小可用 profile。
5. 任何 profile 结果都只是任务激活增强，不直接替代事实判断或正式定性。

## 八、当前真实文件回灌建议

以“东北师范大学附属中学深圳学校家具采购.docx”为首个未知文件样本，优先沉淀：

- 家具类评分表 / 样品要求 / 检测报告模式
- 模板/法规引用/长表格串接导致的误报模式
- 强证据与弱证据的主证据排序规则

这份文件应作为 `DocumentProfile / DomainProfile` 机制的第一批回归样本，而不是单独演化成“家具专用主干逻辑”。
