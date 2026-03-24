from __future__ import annotations

from .models import ConsistencyCheck, Finding, LegalBasis, RiskHit


LEGAL_BASIS_REGISTRY: dict[str, list[LegalBasis]] = {
    "指定品牌/原厂限制": [
        LegalBasis(
            source_name="中华人民共和国政府采购法",
            article_hint="第二十二条、第二十五条",
            summary="供应商条件和采购需求设置应当公平合理，不得以不合理条件排斥或者限制潜在供应商。",
        ),
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="相关公平竞争条款",
            summary="招标文件技术、商务条件不得指向特定供应商或者特定产品来源。",
            basis_type="部门规章",
        ),
    ],
    "产地厂家商标限制": [
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="公平竞争相关条款",
            summary="采购需求不得以产地、厂家、商标等不合理条件限制供应商竞争。",
            basis_type="行政法规",
        )
    ],
    "专利要求": [
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="采购需求编制相关条款",
            summary="技术要求应当与采购项目实际需要相适应，不得设置与履约无关的专利门槛。",
            basis_type="行政法规",
        )
    ],
    "认证证书要求": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="资格条件和技术要求应与项目特点和实际履约需要相匹配。",
            basis_type="部门规范性文件",
        )
    ],
    "检测报告要求": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="证明材料要求应当必要、适度，不得抬高投标门槛。",
            basis_type="部门规范性文件",
        )
    ],
    "主观评分表述": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素量化相关条款",
            summary="评审因素和分值设置应细化量化，减少过度主观裁量。",
            basis_type="部门规章",
        )
    ],
    "业绩加分": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与评审关联性要求",
            summary="评分因素应与采购需求和合同履约能力直接相关，不宜设置无关加分项。",
            basis_type="部门规范性文件",
        )
    ],
    "采购人单方决定": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平与诚实信用原则",
            summary="合同条款应遵循公平原则，不宜保留一方单方决定权影响相对方主要权利义务。",
        )
    ],
    "采购人单方解释或决定条款": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平与诚实信用原则",
            summary="单方解释或单方决定条款可能破坏合同公平与争议处理平衡。",
        )
    ],
    "付款节点不明确": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="合同履约管理相关要求",
            summary="合同履约条款应明确付款节点、条件和验收依据，避免执行歧义。",
            basis_type="部门规范性文件",
        )
    ],
    "考核条款可能控制付款或履约评价": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同履行与公平原则",
            summary="考核、付款、违约责任安排应明确合理，避免以单方主观评价替代客观履约标准。",
        )
    ],
    "扣款机制可能过度依赖单方考核": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平原则",
            summary="违约责任和扣款机制应当明确触发条件、计算方式和程序保障。",
        )
    ],
    "解约条件可能过宽": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同解除相关条款",
            summary="解除合同应有明确法定或约定条件，不宜使用过宽、过泛触发标准。",
        )
    ],
    "尾款支付与考核条款联动风险": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="合同履约条款管理要求",
            summary="付款与验收安排应客观明确，不宜由满意度等主观评价直接控制大额尾款。",
            basis_type="部门规范性文件",
        )
    ],
    "专门面向中小企业却仍保留价格扣除": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="专门面向中小企业采购相关条款",
            summary="专门面向中小企业的采购项目不再适用价格评审优惠条款。",
            basis_type="部门规范性文件",
        )
    ],
    "服务项目声明函类型疑似错用货物模板": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="声明函模板适用要求",
            summary="中小企业声明函应与项目属性一致，货物和服务项目应使用对应模板口径。",
            basis_type="部门规范性文件",
        )
    ],
    "货物项目声明函类型不完整": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="声明函模板适用要求",
            summary="货物采购项目应准确使用制造商等相应声明口径。",
            basis_type="部门规范性文件",
        )
    ],
    "预留份额采购但比例信息不明确": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="预留份额相关条款",
            summary="预留份额采购应明确预留比例和执行方式，保证政策可操作性。",
            basis_type="部门规范性文件",
        )
    ],
    "性别限制": [
        LegalBasis(
            source_name="中华人民共和国就业促进法",
            article_hint="公平就业相关条款",
            summary="除法律法规规定的特殊岗位外，不得设置与履职无关的歧视性就业条件。",
        )
    ],
    "年龄限制": [
        LegalBasis(
            source_name="中华人民共和国就业促进法",
            article_hint="公平就业相关条款",
            summary="招聘和人员要求应避免无正当理由设置年龄门槛。",
        )
    ],
    "身高限制": [
        LegalBasis(
            source_name="中华人民共和国就业促进法",
            article_hint="公平就业相关条款",
            summary="与履职无直接关系的身高条件通常不属于合理人员要求。",
        )
    ],
    "容貌体形要求": [
        LegalBasis(
            source_name="中华人民共和国就业促进法",
            article_hint="公平就业相关条款",
            summary="容貌体形要求原则上不应作为一般采购服务人员的履职条件。",
        )
    ],
    "采购人审批录用": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同履行边界与公平原则",
            summary="采购人与供应商之间应是合同管理关系，不宜深度介入供应商内部用工管理。",
        )
    ],
    "采购人批准更换": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同履行边界与公平原则",
            summary="关键岗位资格核验可以约定，但不宜扩张为采购人审批供应商内部任免。",
        )
    ],
    "采购人直接指挥": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同履行边界与公平原则",
            summary="采购人与供应商员工之间不宜形成直接管理指挥关系，以免突破合同边界。",
        )
    ],
    "人员证明材料负担偏重": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与资格条件适度性要求",
            summary="资格、评分材料要求应与项目需要相适应，不得不合理增加投标负担。",
            basis_type="部门规范性文件",
        )
    ],
    "一般模板残留": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件编制完整性要求",
            summary="采购文件应完整、明确、可执行，减少空白和待定条款。",
            basis_type="部门规范性文件",
        )
    ],
    "服务项目保留货物类声明函模板": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="声明函模板适用要求",
            summary="声明函模板应与项目属性和政策适用范围保持一致。",
            basis_type="部门规范性文件",
        )
    ],
    "专门面向中小企业却保留价格扣除模板": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="专门面向中小企业采购相关条款",
            summary="专门面向中小企业采购时不应继续适用价格扣除模板。",
            basis_type="部门规范性文件",
        )
    ],
    "项目属性 vs 履约内容": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购需求与项目属性匹配要求",
            summary="采购需求、合同类型和项目属性应保持一致，避免货物服务口径错配。",
            basis_type="部门规范性文件",
        )
    ],
    "技术要求 vs 评分标准": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素与采购需求关联性要求",
            summary="评分标准应与采购需求直接对应并量化。",
            basis_type="部门规章",
        )
    ],
    "预算金额 vs 最高限价": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件编制完整性要求",
            summary="预算金额、最高限价等关键金额信息应完整一致。",
            basis_type="部门规范性文件",
        )
    ],
    "中小企业政策 vs 价格扣除政策": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="价格评审优惠与专门面向采购条款",
            summary="中小企业价格扣除与专门面向中小企业采购属于不同政策路径，应避免混用。",
            basis_type="部门规范性文件",
        )
    ],
    "正文 vs 评分细则跨文件一致性": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="招标文件与评审标准一致性要求",
            summary="评分细则应与正文采购需求和政策口径一致，不得出现跨文件冲突。",
            basis_type="部门规章",
        )
    ],
    "正文 vs 合同草案跨文件一致性": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购需求、合同文本与履约管理衔接要求",
            summary="招标文件正文承诺与合同草案付款、验收、违约安排应保持衔接一致。",
            basis_type="部门规范性文件",
        )
    ],
}


def annotate_risk_hits(risk_hits: list[RiskHit]) -> list[RiskHit]:
    for hit in risk_hits:
        hit.legal_basis = _lookup_basis(hit.rule_name)
    return risk_hits


def annotate_consistency_checks(checks: list[ConsistencyCheck]) -> list[ConsistencyCheck]:
    for check in checks:
        check.legal_basis = _lookup_basis(check.topic)
    return checks


def annotate_findings(findings: list[Finding]) -> list[Finding]:
    for finding in findings:
        if not finding.legal_basis:
            finding.legal_basis = _lookup_basis(finding.title)
    return findings


def _lookup_basis(key: str) -> list[LegalBasis]:
    return [item for item in LEGAL_BASIS_REGISTRY.get(key, [])]
