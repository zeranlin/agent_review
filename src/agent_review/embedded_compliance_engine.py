from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import re


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class EmbeddedLLMConfig:
    enabled: bool
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: int


def detect_embedded_llm_config() -> EmbeddedLLMConfig:
    return EmbeddedLLMConfig(
        enabled=_env_flag("AGENT_COMPLIANCE_LLM_ENABLED", default=False),
        base_url=os.getenv("AGENT_COMPLIANCE_LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
        model=os.getenv("AGENT_COMPLIANCE_LLM_MODEL", "qwen3.5-27b"),
        api_key=os.getenv("AGENT_COMPLIANCE_LLM_API_KEY"),
        timeout_seconds=int(os.getenv("AGENT_COMPLIANCE_LLM_TIMEOUT_SECONDS", "1800")),
    )


def detect_embedded_parser_mode(default: str = "assist") -> str:
    value = (os.getenv("AGENT_COMPLIANCE_TENDER_PARSER_MODE") or default).strip().lower()
    if value not in {"off", "assist", "required"}:
        return default
    return value


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EmbeddedClause:
    clause_id: str
    text: str
    line_start: int
    line_end: int
    source_section: str | None = None
    section_path: str | None = None
    table_or_item_label: str | None = None
    page_hint: str | None = None
    document_structure_type: str | None = None
    risk_scope: str | None = None
    scope_reason: str | None = None
    scope_type: str | None = None
    clause_function: str | None = None
    effect_strength: str | None = None
    is_effective_requirement: bool | None = None
    is_high_weight_requirement: bool | None = None
    scope_confidence: str | None = None


@dataclass
class EmbeddedPageSpan:
    page_number: int
    line_start: int
    line_end: int
    is_estimated: bool


@dataclass
class EmbeddedNormalizedDocument:
    source_path: str
    document_name: str
    file_hash: str
    normalized_text_path: str
    clause_count: int
    clauses: list[EmbeddedClause]
    page_map: list[EmbeddedPageSpan] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class EmbeddedRuleDefinition:
    rule_id: str
    issue_type: str
    pattern: re.Pattern[str]
    rationale: str
    severity_score: int
    source_section: str
    rewrite_hint: str
    merge_key: str
    related_rule_ids: tuple[str, ...] = ()
    related_reference_ids: tuple[str, ...] = ()


@dataclass
class EmbeddedRuleHit:
    rule_hit_id: str
    rule_id: str
    merge_key: str
    issue_type_candidate: str
    matched_text: str
    matched_clause_id: str
    line_start: int
    line_end: int
    rationale: str
    severity_score: int
    related_rule_ids: tuple[str, ...]
    related_reference_ids: tuple[str, ...]
    source_section: str
    rewrite_hint: str


@dataclass
class EmbeddedFinding:
    finding_id: str
    document_name: str
    problem_title: str
    page_hint: str | None
    clause_id: str
    source_section: str
    section_path: str | None
    table_or_item_label: str | None
    text_line_start: int
    text_line_end: int
    source_text: str
    issue_type: str
    risk_level: str
    severity_score: int
    confidence: str
    compliance_judgment: str
    why_it_is_risky: str
    impact_on_competition_or_performance: str
    legal_or_policy_basis: str | None
    rewrite_suggestion: str
    needs_human_review: bool
    human_review_reason: str | None
    primary_authority: str | None = None


@dataclass
class EmbeddedReviewResult:
    document_name: str
    review_scope: str
    jurisdiction: str | None
    review_timestamp: str
    overall_risk_summary: str
    findings: list[EmbeddedFinding]
    items_for_human_review: list[str]
    review_limitations: list[str]


@dataclass
class EmbeddedLLMArtifacts:
    llm_node_summary: dict[str, object] | None = None


@dataclass
class EmbeddedComplianceRunResult:
    normalized: EmbeddedNormalizedDocument
    review: EmbeddedReviewResult
    llm_artifacts: EmbeddedLLMArtifacts
    cache_enabled: bool
    cache_used: bool
    cache_key: str
    parser_mode: str
    llm_config: EmbeddedLLMConfig


def build_page_map(text: str, *, lines_per_page: int = 45) -> list[EmbeddedPageSpan]:
    line_count = max(len(text.splitlines()), 1)
    spans: list[EmbeddedPageSpan] = []
    page_no = 1
    start = 1
    while start <= line_count:
        end = min(start + lines_per_page - 1, line_count)
        spans.append(EmbeddedPageSpan(page_number=page_no, line_start=start, line_end=end, is_estimated=True))
        page_no += 1
        start = end + 1
    return spans


EMBEDDED_RULES: tuple[EmbeddedRuleDefinition, ...] = (
    EmbeddedRuleDefinition(
        rule_id="QUAL-003",
        issue_type="irrelevant_certification_or_award",
        pattern=re.compile(r"国家级高新技术企业|高新技术企业证书|高新技术企业|AAA|纳税信用A级|科技型中小企业"),
        rationale="将企业称号、荣誉、信用等级或政策认定结果作为门槛或高权重因素，通常与具体履约无直接关系。",
        severity_score=3,
        source_section="申请人的资格要求",
        rewrite_hint="删除企业称号、信用等级或政策认定结果门槛，改为与项目直接相关的履约能力要求。",
        merge_key="qualification-award",
    ),
    EmbeddedRuleDefinition(
        rule_id="QUAL-008",
        issue_type="geographic_restriction",
        pattern=re.compile(r"本地分支机构|本地售后服务机构|本地服务团队|在项目所在地设有|在深圳市注册|项目所在地注册"),
        rationale="通过属地机构、属地注册或本地服务团队要求限制供应商范围，可能构成属地性门槛。",
        severity_score=3,
        source_section="申请人的资格要求",
        rewrite_hint="删除本地机构或注册地前置要求，改为响应时效、到场时限等履约要求。",
        merge_key="qualification-geographic",
    ),
    EmbeddedRuleDefinition(
        rule_id="QUAL-011",
        issue_type="excessive_supplier_qualification",
        pattern=re.compile(r"类似项目业绩.*方可投标|类似项目业绩.*不得少于\d+个|成立满\d+年|经营年限不低于|提供类似业绩证明材料方可"),
        rationale="将类似业绩、经营年限或成立年限直接前置为资格条件，容易把履约经验泛化成准入门槛。",
        severity_score=3,
        source_section="申请人的资格要求",
        rewrite_hint="删除前置类似业绩或成立年限门槛，如确需评价履约经验，可在评分中低权重设置。",
        merge_key="qualification-past-performance",
    ),
    EmbeddedRuleDefinition(
        rule_id="QUAL-012",
        issue_type="excessive_supplier_qualification",
        pattern=re.compile(r"注册资本不低于|年收入不低于|净利润不低于|员工总数不得少于|参保人数不得少于"),
        rationale="设置一般性财务、资产或人员规模门槛，通常超出法定资格和必要履约能力范围。",
        severity_score=3,
        source_section="申请人的资格要求",
        rewrite_hint="删除一般性财务和规模门槛，仅保留与项目履约直接相关的法定资质和能力证明。",
        merge_key="qualification-financial-threshold",
    ),
    EmbeddedRuleDefinition(
        rule_id="QUAL-013",
        issue_type="qualification_domain_mismatch",
        pattern=re.compile(r"非金属矿采矿许可证|采矿许可证|人力资源测评师|有害生物防制|SPCA"),
        rationale="资格条件出现与采购标的领域明显不匹配的资质或登记要求，疑似模板错贴或条款域错配。",
        severity_score=3,
        source_section="申请人的资格要求",
        rewrite_hint="删除与项目标的不相称的资质或登记要求，改为与履约直接相关的条件。",
        merge_key="qualification-domain-mismatch",
    ),
    EmbeddedRuleDefinition(
        rule_id="SCORE-003",
        issue_type="irrelevant_certification_or_award",
        pattern=re.compile(r"高新技术企业.*得\d+分|AAA.*得\d+分|科技型中小企业.*得\d+分|纳税信用A级.*得\d+分"),
        rationale="将企业称号、信用等级或政策认定结果作为评分项，通常与采购标的履约质量无直接关系。",
        severity_score=3,
        source_section="评标信息",
        rewrite_hint="删除与履约无直接关系的企业称号和信用评分项。",
        merge_key="scoring-award",
    ),
    EmbeddedRuleDefinition(
        rule_id="SCORE-008",
        issue_type="qualification_domain_mismatch",
        pattern=re.compile(r"非金属矿采矿许可证.*得\d+分|人力资源测评师.*得\d+分"),
        rationale="评分项出现与采购标的领域明显不匹配的证书或人员要求，疑似条款错贴。",
        severity_score=3,
        source_section="评标信息",
        rewrite_hint="删除与采购标的无直接关系的评分项。",
        merge_key="scoring-domain-mismatch",
    ),
    EmbeddedRuleDefinition(
        rule_id="SCORE-010",
        issue_type="scoring_content_mismatch",
        pattern=re.compile(r"类似业绩.*得\d+分|项目业绩.*得\d+分"),
        rationale="类似业绩作为评分项时，应防止与资格门槛重复放大或权重过高。",
        severity_score=2,
        source_section="评标信息",
        rewrite_hint="核减业绩评分权重，并避免与资格条件重复设置。",
        merge_key="scoring-past-performance",
    ),
    EmbeddedRuleDefinition(
        rule_id="TECH-001",
        issue_type="narrow_technical_parameter",
        pattern=re.compile(r"不允许正偏离|响应时间[:：]?\s*\d+ms|精度[:：]?\s*0\.\d+-0\.\d+mm|设备重量≤\d+kg"),
        rationale="技术参数设置过窄或限制偏离，可能不当收缩竞争范围。",
        severity_score=3,
        source_section="用户需求书",
        rewrite_hint="放宽技术区间或补充必要性论证，避免指向性参数。",
        merge_key="technical-parameter-range",
    ),
    EmbeddedRuleDefinition(
        rule_id="TECH-002",
        issue_type="technical_justification_needed",
        pattern=re.compile(r"GB/T 99999-2024|指定.*检测中心出具的产品检测报告|深圳市医疗器械检测中心"),
        rationale="指定罕见标准或单一机构出具检测报告，可能形成证明来源限制或技术壁垒。",
        severity_score=3,
        source_section="用户需求书",
        rewrite_hint="删除单一机构限定，改为认可具备资质的同类检测机构或等效证明。",
        merge_key="technical-proof-source",
    ),
    EmbeddedRuleDefinition(
        rule_id="CONTRACT-001",
        issue_type="payment_acceptance_linkage",
        pattern=re.compile(r"验收合格后支付|尾款.*验收合格|支付.*与验收挂钩|满意度考核后支付"),
        rationale="付款节点与验收或主观满意度过度绑定，可能形成不对等支付前提。",
        severity_score=3,
        source_section="商务要求",
        rewrite_hint="明确客观验收和付款条件，避免以主观满意度作为支付前提。",
        merge_key="contract-payment-linkage",
    ),
    EmbeddedRuleDefinition(
        rule_id="CONTRACT-002",
        issue_type="one_sided_commercial_term",
        pattern=re.compile(r"质量保证金|第三方检测费用由中标人承担|最终解释权归采购人所有|无论检测结果是否合格"),
        rationale="存在单方责任加重、费用转嫁或解释权失衡条款，可能形成不公平合同安排。",
        severity_score=3,
        source_section="商务要求",
        rewrite_hint="删除单方加重责任、费用转嫁和解释权归一方所有的条款。",
        merge_key="contract-one-sided",
    ),
    EmbeddedRuleDefinition(
        rule_id="CONTRACT-003",
        issue_type="one_sided_commercial_term",
        pattern=re.compile(r"报价不得低于预算金额的80%|低于此价格的投标将被视为无效"),
        rationale="设置最低报价门槛可能影响价格竞争，应审查其合法性和必要性。",
        severity_score=3,
        source_section="商务要求",
        rewrite_hint="删除缺乏依据的最低报价门槛，依法通过异常低价评审机制处理。",
        merge_key="contract-price-floor",
    ),
)


def run_embedded_rule_scan(document: EmbeddedNormalizedDocument) -> list[EmbeddedRuleHit]:
    hits: list[EmbeddedRuleHit] = []
    counter = 1
    for clause in document.clauses:
        matched_by_merge_key: dict[str, EmbeddedRuleHit] = {}
        for rule in EMBEDDED_RULES:
            if not rule.pattern.search(clause.text):
                continue
            hit = EmbeddedRuleHit(
                rule_hit_id=f"ERH-{counter:04d}",
                rule_id=rule.rule_id,
                merge_key=rule.merge_key,
                issue_type_candidate=rule.issue_type,
                matched_text=clause.text,
                matched_clause_id=clause.clause_id,
                line_start=clause.line_start,
                line_end=clause.line_end,
                rationale=rule.rationale,
                severity_score=rule.severity_score,
                related_rule_ids=rule.related_rule_ids,
                related_reference_ids=rule.related_reference_ids,
                source_section=rule.source_section,
                rewrite_hint=rule.rewrite_hint,
            )
            current = matched_by_merge_key.get(hit.merge_key)
            if current is None or hit.severity_score > current.severity_score:
                matched_by_merge_key[hit.merge_key] = hit
                counter += 1
        hits.extend(matched_by_merge_key.values())
    return hits


def build_embedded_review_result(
    document: EmbeddedNormalizedDocument,
    hits: list[EmbeddedRuleHit],
) -> EmbeddedReviewResult:
    findings: list[EmbeddedFinding] = []
    for index, hit in enumerate(hits, start=1):
        clause = next((item for item in document.clauses if item.clause_id == hit.matched_clause_id), None)
        if clause is None:
            continue
        findings.append(
            EmbeddedFinding(
                finding_id=f"EC-{index:03d}",
                document_name=document.document_name,
                problem_title=_problem_title(hit),
                page_hint=clause.page_hint,
                clause_id=clause.clause_id,
                source_section=clause.source_section or hit.source_section,
                section_path=clause.section_path,
                table_or_item_label=clause.table_or_item_label,
                text_line_start=clause.line_start,
                text_line_end=clause.line_end,
                source_text=clause.text,
                issue_type=hit.issue_type_candidate,
                risk_level=_risk_level(hit.severity_score),
                severity_score=hit.severity_score,
                confidence=_confidence_label(hit.severity_score),
                compliance_judgment=_judgment(hit.issue_type_candidate, hit.severity_score),
                why_it_is_risky=hit.rationale,
                impact_on_competition_or_performance=_impact_text(hit.issue_type_candidate),
                legal_or_policy_basis=_basis_text(hit.issue_type_candidate),
                rewrite_suggestion=hit.rewrite_hint,
                needs_human_review=hit.issue_type_candidate in {"technical_justification_needed"},
                human_review_reason="需要结合项目背景核查必要性。" if hit.issue_type_candidate in {"technical_justification_needed"} else None,
                primary_authority=_primary_authority(hit.issue_type_candidate),
            )
        )
    return EmbeddedReviewResult(
        document_name=document.document_name,
        review_scope="资格条件、评分规则、技术要求、商务及验收条款",
        jurisdiction="中国",
        review_timestamp=utc_now_iso(),
        overall_risk_summary=_overall_summary(findings),
        findings=findings,
        items_for_human_review=[item.problem_title for item in findings if item.needs_human_review],
        review_limitations=[
            "当前为 agent_review 内嵌 compliance engine v1，已去除对外部仓库的直接代码依赖。",
            "当前 LLM 评审节点默认关闭，优先保证单仓可运行和规则主链稳定。",
        ],
    )


def run_embedded_compliance_review(
    document: EmbeddedNormalizedDocument,
    *,
    llm_config: EmbeddedLLMConfig | None = None,
    parser_mode: str | None = None,
) -> EmbeddedComplianceRunResult:
    resolved_llm_config = llm_config or detect_embedded_llm_config()
    resolved_parser_mode = parser_mode or detect_embedded_parser_mode(default="assist")
    hits = run_embedded_rule_scan(document)
    review = build_embedded_review_result(document, hits)
    llm_summary = {"status": "llm_disabled"} if not resolved_llm_config.enabled else {"status": "not_implemented"}
    return EmbeddedComplianceRunResult(
        normalized=document,
        review=review,
        llm_artifacts=EmbeddedLLMArtifacts(llm_node_summary=llm_summary),
        cache_enabled=False,
        cache_used=False,
        cache_key=f"embedded:{document.file_hash}:{resolved_parser_mode}",
        parser_mode=resolved_parser_mode,
        llm_config=resolved_llm_config,
    )


def _risk_level(severity_score: int) -> str:
    if severity_score >= 3:
        return "high"
    if severity_score == 2:
        return "medium"
    return "low"


def _confidence_label(severity_score: int) -> str:
    if severity_score >= 3:
        return "high"
    if severity_score == 2:
        return "medium"
    return "low"


def _judgment(issue_type: str, severity_score: int) -> str:
    if issue_type == "technical_justification_needed":
        return "needs_human_review"
    if severity_score >= 3:
        return "likely_non_compliant"
    if severity_score == 2:
        return "potentially_problematic"
    return "likely_compliant"


def _problem_title(hit: EmbeddedRuleHit) -> str:
    mapping = {
        "irrelevant_certification_or_award": "企业称号、信用或政策认定要求可能不当",
        "geographic_restriction": "存在属地性或本地化限制风险",
        "excessive_supplier_qualification": "资格门槛可能过高或与履约弱相关",
        "qualification_domain_mismatch": "资格或评分项与采购标的领域疑似错配",
        "scoring_content_mismatch": "评分项与资格边界或相关性存在风险",
        "narrow_technical_parameter": "技术参数可能过窄或限制偏离",
        "technical_justification_needed": "技术标准或证明来源限制需论证必要性",
        "payment_acceptance_linkage": "付款与验收或主观评价挂钩风险",
        "one_sided_commercial_term": "合同条款存在单方不利或费用转嫁风险",
    }
    return mapping.get(hit.issue_type_candidate, "采购条款存在合规风险")


def _impact_text(issue_type: str) -> str:
    if issue_type in {"geographic_restriction", "excessive_supplier_qualification", "irrelevant_certification_or_award"}:
        return "可能不当缩小供应商竞争范围。"
    if issue_type in {"narrow_technical_parameter", "technical_justification_needed"}:
        return "可能形成技术壁垒或证明来源限制。"
    return "可能导致评审或履约责任边界失衡。"


def _basis_text(issue_type: str) -> str:
    mapping = {
        "geographic_restriction": "政府采购应当维护公平竞争，不得以不合理条件限制供应商。",
        "excessive_supplier_qualification": "资格条件应与项目履约能力直接相关，不得设置与采购需求无关门槛。",
        "irrelevant_certification_or_award": "企业荣誉、信用等级等通常不得替代与标的直接相关的履约能力要求。",
        "qualification_domain_mismatch": "资格、评分因素应与采购标的、履约能力直接相关，避免模板错贴。",
        "scoring_content_mismatch": "评分因素应与采购标的和履约质量直接相关，避免重复放大资格条件。",
        "technical_justification_needed": "技术标准和证明来源限制应有必要性和可替代性论证。",
        "one_sided_commercial_term": "合同条款应遵循公平原则，不得单方加重中标人责任。",
        "payment_acceptance_linkage": "付款与验收条款应明确客观条件，不得设置不对等支付前提。",
    }
    return mapping.get(issue_type, "需结合政府采购公平竞争与需求编制规则综合判断。")


def _primary_authority(issue_type: str) -> str:
    mapping = {
        "geographic_restriction": "《政府采购法》公平竞争原则",
        "excessive_supplier_qualification": "《政府采购法》资格条件适度性原则",
        "irrelevant_certification_or_award": "《政府采购需求管理办法》需求相关性要求",
        "qualification_domain_mismatch": "《政府采购需求管理办法》需求相关性要求",
        "scoring_content_mismatch": "综合评分法相关规范",
        "technical_justification_needed": "《政府采购需求管理办法》需求编制要求",
        "one_sided_commercial_term": "合同公平原则",
        "payment_acceptance_linkage": "验收与付款边界要求",
    }
    return mapping.get(issue_type, "政府采购一般合规原则")


def _overall_summary(findings: list[EmbeddedFinding]) -> str:
    if not findings:
        return "当前未发现明确风险。"
    high = sum(1 for item in findings if item.risk_level == "high")
    manual = sum(1 for item in findings if item.needs_human_review)
    return f"共识别 {len(findings)} 条风险，其中高风险 {high} 条，需人工复核 {manual} 条。"
