from __future__ import annotations

from .models import ConsistencyCheck, Finding, LegalBasis, ReviewPoint, RiskHit


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
    "刚性门槛型专利要求": [
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="采购需求编制相关条款",
            summary="不得将与采购标的相关专利直接设为不必要的刚性门槛，采购需求应与项目实际需要相适应。",
            basis_type="行政法规",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="采购需求和证明材料要求应与项目实际需要一致，不得超出必要限度设置门槛。",
            basis_type="部门规范性文件",
        ),
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
    "需求调查结论与项目复杂度匹配性复核": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求调查相关要求",
            summary="项目复杂度较高时，宜充分论证需求调查是否确有必要，避免程序性判断过于简化。",
            basis_type="部门规范性文件",
        )
    ],
    "专家论证必要性建议复核": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理与专家论证相关要求",
            summary="对复杂项目、长期履约项目或多要素采购项目，宜复核是否需要更充分的专家论证支撑。",
            basis_type="部门规范性文件",
        )
    ],
    "采购方式适用理由不足": [
        LegalBasis(
            source_name="中华人民共和国政府采购法",
            article_hint="公开招标及法定采购方式相关条款",
            summary="采购方式的选择应当符合法定适用条件，非公开招标采购方式应有充分、明确的适用理由。",
        ),
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="采购方式适用相关条款",
            summary="采用竞争性磋商、谈判、询价或单一来源等方式时，应当符合相应法定情形并留存论证依据。",
            basis_type="行政法规",
        ),
    ],
    "混合采购未拆分或包件划分依据不足": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购需求与采购组织方式匹配要求",
            summary="采购组织方式、包件划分和项目拆分应与采购标的构成、履约边界和实际需求相匹配。",
            basis_type="部门规范性文件",
        )
    ],
    "资格条件与评分因素重复设门槛": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="资格条件与评审因素设置相关条款",
            summary="资格条件和评分因素应当各司其职，不宜将已作为资格条件的事项再次通过评分重复放大。",
            basis_type="部门规章",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与评审关联性要求",
            summary="评分因素应与采购需求和履约能力直接相关，不得通过重复门槛影响公平竞争。",
            basis_type="部门规范性文件",
        ),
    ],
    "特定资质或证书要求超必要限度": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="资格条件、资质证书和证明材料要求应与项目实际需要相适应，不得超出必要限度设置门槛。",
            basis_type="部门规范性文件",
        )
    ],
    "资格条件可能超出必要限度": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="资格条件和证明材料要求应与采购需求和履约能力直接相关，不宜以信用等级、企业资质层级或成立年限设置过度门槛。",
            basis_type="部门规范性文件",
        )
    ],
    "资格条件可能限定地域业绩或行业范围过窄": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="业绩要求应与项目履约能力相匹配，不宜通过地域范围、地方资源或过窄口径形成排他性限制。",
            basis_type="部门规范性文件",
        )
    ],
    "技术或服务要求可验证性不足": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="技术、商务要求客观可验要求",
            summary="采购需求、技术参数、服务要求和验收标准应客观明确、可验证、可核验。",
            basis_type="部门规范性文件",
        )
    ],
    "验收与付款/考核/满意度联动不当": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="履约与验收管理相关要求",
            summary="付款、验收、考核和满意度安排应衔接合理、客观量化，不宜形成单方主观控制付款的机制。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平原则",
            summary="合同履行、验收和付款条款应遵循公平和诚实信用原则，不宜由一方以主观评价决定对方主要利益。",
        ),
    ],
    "转包外包边界不清或核心任务转包风险": [
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="采购合同履行管理相关条款",
            summary="分包、外包、转包边界应明确，核心任务不宜被模糊转移或变相转包。",
            basis_type="行政法规",
        )
    ],
    "信用评价规则透明性不足": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素设置相关条款",
            summary="信用评价如进入评分，应明确评价来源、规则和适用口径，不宜使用不透明的地方信用分或模糊标准。",
            basis_type="部门规章",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与评审关联性要求",
            summary="信用评价规则、修复和异议路径应清晰，避免因规则不透明影响供应商公平参与。",
            basis_type="部门规范性文件",
        ),
    ],
    "违约责任与程序保障失衡": [
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平与程序保障原则",
            summary="违约责任、扣款、解约等条款应当明确合理，并保留必要整改、申辩或救济程序。",
        )
    ],
    "货物保修表述与项目实际履约内容不匹配": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="合同与履约条款相关要求",
            summary="采购需求、合同条款和实际履约责任应保持一致，不宜以单一货物质保条款替代持续性服务或作业责任安排。",
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
    "项目属性与合同类型口径疑似不一致": [
        LegalBasis(
            source_name="中华人民共和国政府采购法",
            article_hint="第二条",
            summary="政府采购应按货物、工程、服务的真实采购对象和法律关系进行组织，不宜在项目属性和合同类型上出现明显错配。",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="采购需求、合同类型与项目实际需要应保持一致，避免名义采购属性与实际履约结构脱节。",
            basis_type="部门规范性文件",
        ),
    ],
    "货物采购混入持续性作业服务": [
        LegalBasis(
            source_name="中华人民共和国政府采购法实施条例",
            article_hint="货物和服务区分相关条款",
            summary="采购项目属性应结合实际履约内容判断，持续性作业服务不宜简单按货物采购处理。",
            basis_type="行政法规",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购需求与项目属性匹配要求",
            summary="采购需求应与项目实际履约内容相适应，货物采购混入长期作业服务时应重新核对项目主属性。",
            basis_type="部门规范性文件",
        ),
    ],
    "技术要求 vs 评分标准": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素与采购需求关联性要求",
            summary="评分标准应与采购需求直接对应并量化。",
            basis_type="部门规章",
        )
    ],
    "行业无关证书或财务指标被纳入评分": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与评审关联性要求",
            summary="评分因素应与采购需求和合同履约能力直接相关，不宜纳入与项目标的不匹配的证书或财务偏好指标。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素设置相关条款",
            summary="评审因素和分值设置应反映项目实际需求，不得借无关评分项变相限制竞争。",
            basis_type="部门规章",
        ),
    ],
    "方案评分量化不足": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="技术、商务要求客观量化要求",
            summary="需要供应商提供方案时，应尽可能明确客观、量化指标和相应等次，避免过宽裁量空间。",
            basis_type="部门规范性文件",
        )
    ],
    "评分分档主观性与量化充分性复核": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="技术、商务要求客观量化要求",
            summary="评分分档和方案评审应尽可能明确客观、量化指标，避免仅以宽泛优劣分档或缺陷概念承载过大裁量空间。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素和标准相关条款",
            summary="评审标准应细化量化，减少仅凭主观比较或宽泛分档进行打分的空间。",
            basis_type="部门规章",
        ),
    ],
    "证书检测报告及财务指标权重合理性复核": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="评分材料、检测报告和认证证书要求应与项目实际需要相适应，不得超出必要限度增加投标负担。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素设置相关条款",
            summary="评审因素和分值设置应与采购需求和履约能力直接相关，不宜以证书、检测报告或财务偏好形成变相门槛。",
            basis_type="部门规章",
        ),
    ],
    "投标阶段证书或检测报告负担过重": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="证明材料要求应与采购项目实际需要相适应，不得要求供应商在投标阶段普遍提交超必要限度的检测报告和认证证书。",
            basis_type="部门规范性文件",
        ),
    ],
    "信用评价作为评分因素": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素设置相关条款",
            summary="评分因素应与采购需求和履约能力直接相关，信用评价如单列评分，应核查其关联性和分值适度性。",
            basis_type="部门规章",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求与评审关联性要求",
            summary="信用评价、信用分等材料如作为评分因素，不宜脱离项目实际需要单列过重权重。",
            basis_type="部门规范性文件",
        ),
    ],
    "团队稳定性要求过强": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="技术、商务要求客观量化要求",
            summary="人员或团队稳定性要求应与履约需要直接相关，避免过度限定团队构成或稳定性。",
            basis_type="部门规范性文件",
        ),
    ],
    "人员更换限制较强": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="需求管理一般要求",
            summary="人员更换控制宜限于关键岗位和履约保障，不宜扩展为采购人审批供应商内部任免。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="合同履约约束相关条款",
            summary="人员更换限制应与项目履约责任相适应，避免形成过强的人员控制条款。",
            basis_type="部门规章",
        ),
    ],
    "证书类评分分值偏高": [
        LegalBasis(
            source_name="政府采购货物和服务招标投标管理办法",
            article_hint="评审因素设置相关条款",
            summary="评审因素和分值设置应与项目实际需求和履约能力直接相关，不宜以证书类评分形成过重权重。",
            basis_type="部门规章",
        ),
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="技术、商务要求客观量化要求",
            summary="评分因素应当客观、适度，与采购需求相匹配，避免因证书类评分权重偏高影响中小企业公平参与。",
            basis_type="部门规范性文件",
        ),
    ],
    "预算金额 vs 最高限价": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件编制完整性要求",
            summary="预算金额、最高限价等关键金额信息应完整一致。",
            basis_type="部门规范性文件",
        )
    ],
    "预算金额与面向中小企业采购金额口径异常": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件编制完整性要求",
            summary="预算金额、最高限价及中小企业政策相关金额口径应清晰一致，避免错填、漏填或混用。",
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
    "面向中小企业采购金额与最高限价疑似混用": [
        LegalBasis(
            source_name="政府采购促进中小企业发展管理办法",
            article_hint="中小企业政策执行口径要求",
            summary="中小企业政策金额口径应真实反映政策适用范围，不宜直接以最高限价替代面向中小企业采购金额。",
            basis_type="部门规范性文件",
        )
    ],
    "合同条款出现非本行业成果模板表述": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件与合同文本一致性要求",
            summary="合同条款应与项目行业性质、履约方式和验收要求保持一致，避免沿用其他行业成果交付模板。",
            basis_type="部门规范性文件",
        )
    ],
    "合同文本存在明显模板残留": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="采购文件与合同文本一致性要求",
            summary="采购文件和合同文本应准确、完整、可执行，不应保留空白占位、错行业术语或明显旧模板残留。",
            basis_type="部门规范性文件",
        )
    ],
    "验收标准存在优胜原则或单方弹性判断": [
        LegalBasis(
            source_name="政府采购需求管理办法",
            article_hint="验收与履约管理要求",
            summary="验收标准应客观、明确、事先确定，不宜保留由采购人单方弹性判断的空间。",
            basis_type="部门规范性文件",
        ),
        LegalBasis(
            source_name="中华人民共和国民法典",
            article_hint="合同编公平原则",
            summary="合同履约和验收条款应遵循公平、明确原则，避免一方以模糊标准决定对方主要权利义务。",
        ),
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


def annotate_review_points(review_points: list[ReviewPoint]) -> list[ReviewPoint]:
    for point in review_points:
        if not point.legal_basis:
            point.legal_basis = _lookup_basis(point.title)
    return review_points


def _lookup_basis(key: str) -> list[LegalBasis]:
    return [item for item in LEGAL_BASIS_REGISTRY.get(key, [])]
