from __future__ import annotations

from .models import AuthorityBinding


AUTHORITY_BINDINGS: list[AuthorityBinding] = [
    AuthorityBinding(
        binding_id="AUTH-RP-QUAL-003-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-018",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-QUAL-003",
        legal_proposition="资格条件应与采购需求和合同履行直接相关，不得设置超出必要的门槛。",
        applicability_conditions=["存在资格条件、资质证书、信用等级或成立年限门槛"],
        exclusion_conditions=["法律法规明确要求的行业许可或法定资质"],
        requires_human_review_when=[
            "行业许可、医疗安全、保密资质等可能具有特殊法定必要性",
            "采购人主张该门槛与重大履约风险直接相关但尚未提供论证",
        ],
        evidence_expectations=["需要直接引文", "优先识别资格区绑定条款"],
        reasoning_template="如该资格门槛无法证明与履约能力直接相关，应审慎认定存在不合理限制竞争风险。",
        suggested_remedy_template="删除与履约无直接关联的门槛，改为围绕履约能力设置可验证条件。",
        priority="primary",
    ),
    AuthorityBinding(
        binding_id="AUTH-RP-QUAL-004-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-018",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-QUAL-004",
        legal_proposition="资格业绩条件不得无必要地收窄地域和行业范围，也不宜与评分要求重复构成隐性门槛。",
        applicability_conditions=["存在资格业绩数量、地域、行业范围或与评分重复的信号"],
        exclusion_conditions=["采购人已说明现场连续运行、应急保障等客观必要性"],
        requires_human_review_when=[
            "项目确有现场连续运行、应急保障等客观场景需要",
            "采购人已说明为何必须设置本地场地或极短响应时限",
        ],
        evidence_expectations=["需要资格条款直接引文", "需要资格与评分跨段对齐"],
        reasoning_template="应重点审查业绩条件是否超过履约所必需的边界，并防止资格与评分重复设门槛。",
        suggested_remedy_template="删除地域限定或过窄行业口径，仅保留与履约能力直接相关的同类经验描述。",
        priority="primary",
    ),
    AuthorityBinding(
        binding_id="AUTH-RP-SCORE-005-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-009",
        doc_title="政府采购需求管理办法",
        article_label="第九条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-SCORE-005",
        legal_proposition="评分因素应与采购需求和合同履行质量相关，不宜将行业无关证书或财务规模因素作为主要评分依据。",
        applicability_conditions=["评分表或评分细则中出现证书、检测报告、财务指标"],
        exclusion_conditions=["采购人能够证明评分内容对履约质量具有直接影响"],
        requires_human_review_when=[
            "采购人能够证明相关评分内容对履约质量具有直接影响",
            "混合采购场景下评分项同时覆盖主标的和次标的能力",
        ],
        evidence_expectations=["需要评分表行证据", "需要分值或评分描述"],
        reasoning_template="如评分项无法说明与采购需求和履约质量的直接关系，应认定存在评分相关性风险。",
        suggested_remedy_template="删除无关证书或财务指标评分项，改为与履约方案、服务能力直接相关的量化指标。",
        priority="primary",
    ),
    AuthorityBinding(
        binding_id="AUTH-RP-EVID-001-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-018",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-EVID-001",
        legal_proposition="证明材料、检测报告和认证要求应必要、适度，不得无正当理由限定特定机构或唯一出具来源。",
        applicability_conditions=["存在检测报告、证明材料或机构出具来源限制"],
        exclusion_conditions=["法律法规明确要求特定机构、法定检验检疫或行业主管部门强制要求"],
        requires_human_review_when=[
            "项目确有法定检验检疫、注册备案或唯一监管机构要求",
            "采购人已提供充分论证证明必须限定特定出具口径",
        ],
        evidence_expectations=["需要直接引文", "优先保留特定检测中心或机构名称"],
        reasoning_template="如证明材料被限定为特定检测中心、实验室或唯一出具来源，应审慎认定存在限制竞争风险。",
        suggested_remedy_template="将特定机构名称改写为具备法定资质或等效能力的机构，不限定唯一来源。",
        priority="primary",
    ),
    AuthorityBinding(
        binding_id="AUTH-RP-CONTRACT-009-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-021",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-CONTRACT-009",
        legal_proposition="验收标准应明确、客观、可执行，不宜依赖优胜原则或采购人单方弹性判断。",
        applicability_conditions=["存在验收标准、验收合格条件或验收判定机制"],
        exclusion_conditions=["行业主管部门另有法定验收标准或第三方检测强制要求"],
        requires_human_review_when=[
            "行业主管部门另有法定验收标准或第三方检测强制要求",
            "项目采取分期实施、分段验收且合同中已有完整配套机制",
        ],
        evidence_expectations=["需要合同条款直接引文", "优先保留验收与付款相关上下文"],
        reasoning_template="如验收标准以采购人单方解释或弹性判断为核心，应审慎认定合同公平性风险。",
        suggested_remedy_template="将验收标准改写为明确、客观、可复核的指标和程序。",
        priority="primary",
    ),
    AuthorityBinding(
        binding_id="AUTH-RP-CONTRACT-011-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-021",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
        binding_scope="point",
        point_id="RP-CONTRACT-011",
        legal_proposition="付款节点、验收、考核和满意度机制应客观、明确、可执行，不宜形成采购人单方控制付款的安排。",
        applicability_conditions=["存在付款节点与验收、考核或满意度条款联动"],
        exclusion_conditions=["法定分期验收付款机制且考核标准客观量化明确"],
        requires_human_review_when=[
            "项目属于持续服务且合同已设置客观量化考核体系",
            "付款联动仅对应法定验收节点且不存在采购人单方自由裁量",
        ],
        evidence_expectations=["需要付款条款直接引文", "优先保留与验收或考核的上下文联动"],
        reasoning_template="如付款释放明显受采购人主观验收、考核或满意度控制，应审慎认定合同公平性风险。",
        suggested_remedy_template="将付款条件改写为客观、量化、可复核的验收或考核节点，避免单方主观控制。",
        priority="primary",
    ),
]


AUTHORITY_BINDING_INDEX: dict[str, AuthorityBinding] = {
    item.binding_id: item for item in AUTHORITY_BINDINGS
}


def get_authority_binding(binding_id: str) -> AuthorityBinding | None:
    return AUTHORITY_BINDING_INDEX.get(binding_id.strip())


def list_authority_bindings() -> list[AuthorityBinding]:
    return list(AUTHORITY_BINDINGS)


def list_bindings_for_point(point_id: str) -> list[AuthorityBinding]:
    normalized = point_id.strip()
    return [item for item in AUTHORITY_BINDINGS if item.point_id == normalized]
