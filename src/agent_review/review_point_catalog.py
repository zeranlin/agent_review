from __future__ import annotations

import re

from .models import ExtractedClause, ReviewPoint, ReviewPointCondition, ReviewPointDefinition, Severity


CATALOG: list[ReviewPointDefinition] = [
    ReviewPointDefinition(
        catalog_id="RP-SME-001",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        default_severity=Severity.high,
        scenario_tags=["policy"],
        required_conditions=[
            ReviewPointCondition(
                "项目专门面向中小企业",
                clause_fields=["是否专门面向中小企业"],
                signal_groups=[["专门面向中小企业"]],
            ),
            ReviewPointCondition(
                "文件仍保留价格扣除",
                clause_fields=["是否仍保留价格扣除条款"],
                signal_groups=[["价格扣除"]],
            ),
        ],
        exclusion_conditions=[
            ReviewPointCondition(
                "仅一般性政策说明无具体执行条款",
                signal_groups=[["政策说明"], ["不适用本项目"]],
            ),
        ],
        basis_hint="专门面向中小企业采购项目不再适用价格评审优惠条款。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SME-002",
        title="服务项目声明函类型疑似错用货物模板",
        dimension="中小企业政策风险",
        default_severity=Severity.high,
        scenario_tags=["policy", "service"],
        required_conditions=[
            ReviewPointCondition("项目属性为服务", clause_fields=["项目属性"], signal_groups=[["服务"]]),
            ReviewPointCondition("声明函出现制造商口径", clause_fields=["中小企业声明函类型"], signal_groups=[["制造商"]]),
        ],
        basis_hint="服务项目应使用与承接方口径一致的中小企业声明函。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SME-003",
        title="货物项目声明函类型不完整",
        dimension="中小企业政策风险",
        default_severity=Severity.medium,
        scenario_tags=["policy", "goods"],
        required_conditions=[
            ReviewPointCondition("项目属性为货物", clause_fields=["项目属性"], signal_groups=[["货物"]]),
            ReviewPointCondition("声明函缺少制造商口径", clause_fields=["中小企业声明函类型"], signal_groups=[["承接方"]]),
        ],
        basis_hint="货物项目声明函应能反映制造商相关口径。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SME-004",
        title="预留份额采购但比例信息不明确",
        dimension="中小企业政策风险",
        default_severity=Severity.medium,
        scenario_tags=["policy"],
        required_conditions=[
            ReviewPointCondition("文件涉及预留份额", clause_fields=["是否为预留份额采购"], signal_groups=[["预留份额"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("已明确比例信息", clause_fields=["分包比例"], signal_groups=[["分包比例", "预留比例", "小微企业比例"]]),
        ],
        basis_hint="预留份额采购应明确比例与执行路径。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-REST-001",
        title="指定品牌/原厂限制",
        dimension="A.限制竞争风险",
        default_severity=Severity.high,
        scenario_tags=["goods"],
        required_conditions=[
            ReviewPointCondition(
                "存在品牌或原厂指向",
                clause_fields=["是否指定品牌"],
                signal_groups=[["品牌", "原厂"]],
            ),
        ],
        exclusion_conditions=[
            ReviewPointCondition("仅供应商模板或声明文本", signal_groups=[["声明函"], ["证明书"]]),
        ],
        basis_hint="采购需求不得指向特定供应商或者产品来源。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-REST-002",
        title="产地厂家商标限制",
        dimension="A.限制竞争风险",
        default_severity=Severity.high,
        scenario_tags=["goods"],
        required_conditions=[
            ReviewPointCondition(
                "存在产地厂家商标限制",
                clause_fields=["是否有限制产地厂家商标"],
                signal_groups=[["产地", "厂家", "商标"]],
            ),
        ],
        exclusion_conditions=[
            ReviewPointCondition("仅残联或声明函模板说明", signal_groups=[["残疾人福利性单位"], ["商标"]]),
        ],
        basis_hint="不得以产地、厂家、商标等不合理条件限制竞争。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-REST-003",
        title="专利要求",
        dimension="A.限制竞争风险",
        default_severity=Severity.high,
        scenario_tags=["goods"],
        required_conditions=[ReviewPointCondition("存在专利要求", clause_fields=["是否要求专利"], signal_groups=[["专利"]])],
        basis_hint="专利要求应具备必要性，避免形成不合理门槛。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-001",
        title="主观评分表述",
        dimension="B.评分不规范风险",
        default_severity=Severity.medium,
        scenario_tags=["scoring"],
        required_conditions=[ReviewPointCondition("存在优良中差等主观分档", signal_groups=[["优", "良", "中", "差"]])],
        basis_hint="评分标准应量化，避免主观分档。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-002",
        title="评审方法出现但评分标准不够清晰",
        dimension="评审标准明确性",
        default_severity=Severity.high,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition("文件出现综合评分", clause_fields=["评分方法"], signal_groups=[["综合评分"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("已明确评分标准", signal_groups=[["评分标准"]]),
        ],
        basis_hint="评分方法和评分标准应同时明确。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-003",
        title="样品或演示分值可能过高",
        dimension="B.评分不规范风险",
        default_severity=Severity.high,
        scenario_tags=["scoring", "goods"],
        required_conditions=[
            ReviewPointCondition("存在样品或演示要求", clause_fields=["样品要求", "现场演示要求", "样品分"], signal_groups=[["样品", "演示"]]),
            ReviewPointCondition("存在样品或演示评分", clause_fields=["样品分"], signal_groups=[["样品分", "演示分"]]),
        ],
        basis_hint="样品或演示评分应控制必要范围，避免影响充分竞争。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-004",
        title="财务指标作为评分因素",
        dimension="B.评分不规范风险",
        default_severity=Severity.medium,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition("存在财务指标评分", clause_fields=["财务指标加分"], signal_groups=[["营业收入", "利润率", "注册资本", "资产规模"]]),
        ],
        basis_hint="财务指标评分应与项目履约能力直接相关，避免形成规模偏向。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-005",
        title="行业无关证书或财务指标被纳入评分",
        dimension="B.评分不规范风险",
        default_severity=Severity.high,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition(
                "存在行业相关性存疑评分项",
                clause_fields=["行业相关性存疑评分项"],
                signal_groups=[["软件企业认定证书", "ITSS", "利润率", "财务报告"]],
            ),
        ],
        basis_hint="评分因素应与项目履约能力直接相关，不宜引入行业无关证书或财务偏向指标。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-006",
        title="方案评分量化不足",
        dimension="B.评分不规范风险",
        default_severity=Severity.high,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition(
                "存在方案评分扣分模式",
                clause_fields=["方案评分扣分模式"],
                signal_groups=[["无缺陷得满分", "每缺项扣", "每处缺陷扣"]],
            ),
        ],
        basis_hint="方案评分应尽可能客观量化，避免用宽泛缺陷定义承载过大裁量空间。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-007",
        title="评分分档主观性与量化充分性复核",
        dimension="评审标准明确性",
        default_severity=Severity.high,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition(
                "存在评分分档或方案扣分模式",
                clause_fields=["方案评分扣分模式"],
                signal_groups=[["完全满足", "不完全满足"], ["优于", "缺陷", "扣分"]],
            ),
        ],
        basis_hint="评分分档和扣分规则应尽量客观量化，避免给评委留下过大自由裁量空间。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SCORE-008",
        title="证书检测报告及财务指标权重合理性复核",
        dimension="评审标准明确性",
        default_severity=Severity.high,
        scenario_tags=["scoring"],
        required_conditions=[
            ReviewPointCondition(
                "存在证书报告或财务指标评分信号",
                clause_fields=["行业相关性存疑评分项", "财务指标加分"],
                signal_groups=[["证书", "检测报告"], ["财务", "利润率", "营业收入", "分值"]],
            ),
        ],
        basis_hint="证书、检测报告和财务指标评分应与项目履约能力直接相关，且权重、提交负担不得明显超过必要限度。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-001",
        title="性别限制",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("存在性别限制", clause_fields=["性别限制"], signal_groups=[["性别", "男性", "女性"]])],
        exclusion_conditions=[ReviewPointCondition("仅法定代表人模板字段", signal_groups=[["法定代表人"], ["性别"]])],
        basis_hint="与履职无关的性别限制不宜作为一般条件。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-002",
        title="年龄限制",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("存在年龄限制", clause_fields=["年龄限制"], signal_groups=[["年龄"]])],
        exclusion_conditions=[ReviewPointCondition("仅法定代表人模板字段", signal_groups=[["法定代表人"], ["年龄"]])],
        basis_hint="与履职无关的年龄限制不宜作为一般条件。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-003",
        title="身高限制",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("存在身高限制", clause_fields=["身高限制"], signal_groups=[["身高"]])],
        basis_hint="与履职无关的身高限制不宜作为一般条件。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-004",
        title="容貌体形要求",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("存在容貌体形要求", clause_fields=["容貌体形要求"], signal_groups=[["容貌", "体形", "五官"]])],
        basis_hint="容貌体形要求通常超出一般履职边界。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-005",
        title="采购人审批录用",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("采购人审批录用", clause_fields=["采购人审批录用"], signal_groups=[["审批", "录用"]])],
        basis_hint="采购人不宜过度介入供应商内部录用管理。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-006",
        title="采购人批准更换",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("采购人批准更换", clause_fields=["采购人批准更换"], signal_groups=[["更换", "采购人同意"]])],
        basis_hint="人员更换控制不宜演变为采购人审批内部任免。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-007",
        title="采购人直接指挥",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.high,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("采购人直接指挥", clause_fields=["采购人直接指挥"], signal_groups=[["直接指挥", "服从采购人安排"]])],
        basis_hint="双方应保持合同管理关系，不宜变成直接用工管理。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-PER-008",
        title="人员证明材料负担偏重",
        dimension="人员条件与用工边界风险",
        default_severity=Severity.medium,
        scenario_tags=["service", "personnel"],
        required_conditions=[ReviewPointCondition("人员证明叠加", clause_fields=["人员评分要求", "学历职称要求"], signal_groups=[["社保"], ["学历", "职称"]])],
        basis_hint="叠加证明材料应与履职直接相关并保持必要性。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-001",
        title="采购人单方解释或决定条款",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[ReviewPointCondition("存在单方决定表述", clause_fields=["单方解释权"], signal_groups=[["采购人意见为准", "解释权", "采购人解释", "采购人说了算"]])],
        exclusion_conditions=[ReviewPointCondition("仅程序性定义说明", signal_groups=[["采购代理机构"], ["名词解释"]])],
        basis_hint="不宜设置明显破坏合同公平的单方解释或决定条款。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-002",
        title="考核条款可能控制付款或履约评价",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[ReviewPointCondition("存在考核条款", clause_fields=["考核条款"], signal_groups=[["考核"]])],
        basis_hint="考核条款应量化，避免主观控制付款或履约评价。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-003",
        title="扣款机制可能过度依赖单方考核",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[ReviewPointCondition("存在扣款条款", clause_fields=["扣款条款"], signal_groups=[["扣款", "扣罚", "罚款"]])],
        basis_hint="扣款机制应具备明确公式、条件和程序保障。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-004",
        title="解约条件可能过宽",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[ReviewPointCondition("存在解约条款", clause_fields=["解约条款"], signal_groups=[["解约", "解除合同"]])],
        basis_hint="解约条款应避免宽泛条件并保留程序保障。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-005",
        title="尾款支付与考核条款联动风险",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[
            ReviewPointCondition("存在付款节点", clause_fields=["付款节点"], signal_groups=[["付款", "支付"]]),
            ReviewPointCondition("存在考核条款", clause_fields=["考核条款"], signal_groups=[["考核"]]),
        ],
        basis_hint="大额尾款不宜由单方主观考核决定。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-006",
        title="验收标准可能依赖采购人主观确认",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[
            ReviewPointCondition("存在验收标准", clause_fields=["验收标准"], signal_groups=[["验收"]]),
            ReviewPointCondition("存在主观验收口径", clause_fields=["验收标准"], signal_groups=[["采购人确认", "满意度", "主观验收"]]),
        ],
        basis_hint="验收标准应尽量客观，不宜过度依赖采购人单方主观确认。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-007",
        title="解约条款未见整改或申辩程序",
        dimension="合同与履约风险",
        default_severity=Severity.medium,
        scenario_tags=["contract"],
        required_conditions=[
            ReviewPointCondition("存在解约条款", clause_fields=["解约条款"], signal_groups=[["解约", "解除合同"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("已设置整改或申辩程序", signal_groups=[["整改", "限期改正", "申辩", "陈述意见"]]),
        ],
        basis_hint="解约条款宜保留必要的整改或申辩程序，避免条件过宽。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-008",
        title="合同条款出现非本行业成果模板表述",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract", "template"],
        required_conditions=[
            ReviewPointCondition(
                "存在成果模板术语",
                clause_fields=["合同成果模板术语"],
                signal_groups=[["项目成果", "移作他用", "泄露本项目成果"]],
            ),
        ],
        basis_hint="合同条款中的成果交付、成果保密等表述应与项目行业性质相匹配。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-009",
        title="验收标准存在优胜原则或单方弹性判断",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[
            ReviewPointCondition(
                "存在验收弹性条款",
                clause_fields=["验收弹性条款"],
                signal_groups=[["优胜的原则", "确定验收标准"]],
            ),
        ],
        basis_hint="验收标准应事先明确、客观，不宜保留采购人单方弹性判断空间。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-001",
        title="货物项目混入大量服务履约内容",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure", "goods"],
        required_conditions=[
            ReviewPointCondition("项目属性为货物", clause_fields=["项目属性"], signal_groups=[["货物"]]),
            ReviewPointCondition("存在服务履约术语", signal_groups=[["运维", "实施", "驻场", "服务内容"]]),
        ],
        basis_hint="项目属性、履约内容和合同结构应保持一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-002",
        title="服务项目混入货物化履约口径",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure", "service"],
        required_conditions=[
            ReviewPointCondition("项目属性为服务", clause_fields=["项目属性"], signal_groups=[["服务"]]),
            ReviewPointCondition("存在货物化术语", signal_groups=[["制造商", "规格型号", "质保期"]]),
        ],
        basis_hint="服务项目不宜沿用货物项目履约模板。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-003",
        title="项目属性与所属行业口径疑似不一致",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure"],
        required_conditions=[
            ReviewPointCondition("存在项目属性", clause_fields=["项目属性"]),
            ReviewPointCondition("存在所属行业", clause_fields=["所属行业划分"]),
        ],
        basis_hint="项目属性和所属行业划分应保持一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-004",
        title="家具项目出现非典型结构性术语",
        dimension="项目结构风险",
        default_severity=Severity.medium,
        scenario_tags=["structure", "furniture"],
        required_conditions=[
            ReviewPointCondition("采购标的涉及家具", clause_fields=["采购标的"], signal_groups=[["家具"]]),
            ReviewPointCondition("存在非典型术语", signal_groups=[["设计", "测试"]]),
        ],
        basis_hint="家具项目中的非典型术语需核查是否模板残留。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-005",
        title="项目属性与声明函模板口径冲突",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure", "policy"],
        required_conditions=[
            ReviewPointCondition("存在项目属性", clause_fields=["项目属性"]),
            ReviewPointCondition("存在声明函类型", clause_fields=["中小企业声明函类型"]),
        ],
        basis_hint="项目属性和声明函模板口径应保持一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-006",
        title="项目属性与品目名称口径疑似不一致",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure"],
        required_conditions=[
            ReviewPointCondition("存在项目属性", clause_fields=["项目属性"]),
            ReviewPointCondition("存在品目名称", clause_fields=["品目名称"]),
        ],
        basis_hint="项目属性和品目名称口径应相互印证，避免项目定性错配。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-007",
        title="项目属性与合同类型口径疑似不一致",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure", "contract"],
        required_conditions=[
            ReviewPointCondition("存在项目属性", clause_fields=["项目属性"]),
            ReviewPointCondition("存在合同类型", clause_fields=["合同类型"]),
        ],
        basis_hint="项目属性、采购内容与合同类型应形成一致的法律关系结构。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-STRUCT-008",
        title="货物采购混入持续性作业服务",
        dimension="项目结构风险",
        default_severity=Severity.high,
        scenario_tags=["structure", "goods"],
        required_conditions=[
            ReviewPointCondition("项目属性为货物", clause_fields=["项目属性"], signal_groups=[["货物"]]),
            ReviewPointCondition("存在持续性作业服务", clause_fields=["是否含持续性服务"], signal_groups=[["人工管护", "抚育", "运水"]]),
        ],
        basis_hint="货物采购中如混入持续性作业服务，应重新核对项目主属性和采购组织方式。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-001",
        title="一般模板残留",
        dimension="模板残留与冲突风险",
        default_severity=Severity.low,
        scenario_tags=["template"],
        required_conditions=[ReviewPointCondition("存在模板残留词", signal_groups=[["待定", "空白", "另行通知"]])],
        basis_hint="一般模板残留应清理，避免执行歧义。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-002",
        title="服务项目保留货物类声明函模板",
        dimension="模板残留与冲突风险",
        default_severity=Severity.high,
        scenario_tags=["template", "service"],
        required_conditions=[
            ReviewPointCondition("项目属性为服务", clause_fields=["项目属性"], signal_groups=[["服务"]]),
            ReviewPointCondition("声明函出现制造商口径", clause_fields=["中小企业声明函类型"], signal_groups=[["制造商"]]),
        ],
        basis_hint="服务项目不应继续使用货物类声明函模板。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-003",
        title="专门面向中小企业却保留价格扣除模板",
        dimension="模板残留与冲突风险",
        default_severity=Severity.high,
        scenario_tags=["template", "policy"],
        required_conditions=[
            ReviewPointCondition("项目专门面向中小企业", clause_fields=["是否专门面向中小企业"], signal_groups=[["专门面向中小企业"]]),
            ReviewPointCondition("保留价格扣除模板", clause_fields=["是否仍保留价格扣除条款"], signal_groups=[["价格扣除"]]),
        ],
        basis_hint="专门面向中小企业采购项目不应保留价格扣除模板。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-004",
        title="物业项目出现货物化模板术语",
        dimension="模板残留与冲突风险",
        default_severity=Severity.high,
        scenario_tags=["template", "property"],
        required_conditions=[
            ReviewPointCondition("采购标的涉及物业", clause_fields=["采购标的"], signal_groups=[["物业"]]),
            ReviewPointCondition("出现货物化术语", clause_fields=["质保期"], signal_groups=[["质保期"]]),
        ],
        basis_hint="物业服务项目不宜保留货物化模板术语。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-005",
        title="家具项目出现不相关模板术语",
        dimension="模板残留与冲突风险",
        default_severity=Severity.medium,
        scenario_tags=["template", "furniture"],
        required_conditions=[
            ReviewPointCondition("采购标的涉及家具", clause_fields=["采购标的"], signal_groups=[["家具"]]),
            ReviewPointCondition("出现不相关术语", signal_groups=[["设计", "测试"]]),
        ],
        basis_hint="家具项目中的无关模板术语应清理。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-TPL-006",
        title="禁止联合体或分包却保留相关模板",
        dimension="模板残留与冲突风险",
        default_severity=Severity.high,
        scenario_tags=["template", "consistency"],
        required_conditions=[
            ReviewPointCondition("存在禁止联合体或分包口径", clause_fields=["是否允许联合体", "是否允许分包"], signal_groups=[["不允许", "不接受"]]),
            ReviewPointCondition("仍保留联合体或分包模板", signal_groups=[["联合体共同投标协议书", "联合体形式投标", "接受分包"]]),
        ],
        basis_hint="前文禁止联合体或分包时，不应保留对应模板或说明条款。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-001",
        title="技术要求 vs 评分标准",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency"],
        required_conditions=[
            ReviewPointCondition("存在评分依据", clause_fields=["评分方法"], signal_groups=[["评分", "综合评分"]]),
            ReviewPointCondition("技术要求支撑不足", signal_groups=[["技术要求"], ["未发现", "不足"]]),
        ],
        basis_hint="评分标准应与采购需求直接对应并量化。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-002",
        title="项目属性 vs 履约内容",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "structure"],
        required_conditions=[ReviewPointCondition("存在项目属性与履约口径冲突", clause_fields=["项目属性"], signal_groups=[["货物", "服务", "实施", "运维"]])],
        basis_hint="项目属性与履约内容应保持一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-003",
        title="中小企业政策 vs 价格扣除政策",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "policy"],
        required_conditions=[
            ReviewPointCondition("项目专门面向中小企业", clause_fields=["是否专门面向中小企业"], signal_groups=[["中小企业"]]),
            ReviewPointCondition("存在价格扣除", clause_fields=["是否仍保留价格扣除条款"], signal_groups=[["价格扣除"]]),
        ],
        basis_hint="中小企业政策路径和价格扣除口径应一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-004",
        title="验收标准 vs 付款条件",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "contract"],
        required_conditions=[
            ReviewPointCondition("存在验收标准", clause_fields=["验收标准"], signal_groups=[["验收"]]),
            ReviewPointCondition("存在付款节点", clause_fields=["付款节点"], signal_groups=[["付款", "支付"]]),
        ],
        basis_hint="验收标准与付款条件应客观、衔接并可执行。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-005",
        title="中小企业政策 vs 分包条款",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "policy"],
        required_conditions=[
            ReviewPointCondition("存在中小企业政策", clause_fields=["是否专门面向中小企业"], signal_groups=[["中小企业"]]),
            ReviewPointCondition("存在分包条款", clause_fields=["是否允许分包", "分包比例"], signal_groups=[["分包"]]),
        ],
        basis_hint="分包条款与中小企业政策执行路径应一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-006",
        title="服务要求 vs 人员评分要求",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "personnel"],
        required_conditions=[
            ReviewPointCondition("存在服务项目属性", clause_fields=["项目属性"], signal_groups=[["服务"]]),
            ReviewPointCondition("存在人员评分要求", clause_fields=["人员评分要求"], signal_groups=[["学历", "职称", "人员配置"]]),
        ],
        basis_hint="人员评分要求应与服务履职直接相关。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-007",
        title="联合体/分包条款前后一致性",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency"],
        required_conditions=[
            ReviewPointCondition("存在联合体条款", clause_fields=["是否允许联合体"], signal_groups=[["联合体"]]),
            ReviewPointCondition("存在分包条款", clause_fields=["是否允许分包"], signal_groups=[["分包"]]),
        ],
        basis_hint="联合体与分包条款的允许/禁止口径应保持一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-008",
        title="联合体/分包与中小企业政策执行路径冲突",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "policy"],
        required_conditions=[
            ReviewPointCondition("存在中小企业政策", clause_fields=["是否专门面向中小企业", "分包比例"], signal_groups=[["中小企业", "预留份额"]]),
            ReviewPointCondition("存在联合体或分包口径", clause_fields=["是否允许联合体", "是否允许分包"], signal_groups=[["联合体", "分包"]]),
        ],
        basis_hint="联合体、分包与中小企业政策的执行路径应相互衔接。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-009",
        title="预算金额与面向中小企业采购金额口径异常",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency", "policy"],
        required_conditions=[
            ReviewPointCondition("存在预算金额", clause_fields=["预算金额"]),
            ReviewPointCondition("存在面向中小企业采购金额", clause_fields=["面向中小企业采购金额"]),
            ReviewPointCondition("存在最高限价", clause_fields=["最高限价"]),
        ],
        basis_hint="预算金额、最高限价和面向中小企业采购金额应保持清晰且口径一致。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-SME-005",
        title="面向中小企业采购金额与最高限价疑似混用",
        dimension="中小企业政策风险",
        default_severity=Severity.medium,
        scenario_tags=["policy"],
        required_conditions=[
            ReviewPointCondition("存在面向中小企业采购金额", clause_fields=["面向中小企业采购金额"]),
            ReviewPointCondition("存在最高限价", clause_fields=["最高限价"]),
        ],
        basis_hint="面向中小企业采购金额应与最高限价、预算金额保持口径清晰，不宜直接混填。",
    ),
]


def resolve_review_point_definition(title: str, dimension: str, severity: Severity) -> ReviewPointDefinition:
    for item in CATALOG:
        if item.title == title and item.dimension == dimension:
            return item
    slug = _slugify(f"{dimension}-{title}")
    return ReviewPointDefinition(
        catalog_id=f"RP-GEN-{slug[:24].upper()}",
        title=title,
        dimension=dimension,
        default_severity=severity,
        scenario_tags=[],
        required_conditions=[],
        exclusion_conditions=[],
        basis_hint="当前审查点尚未在标准目录中沉淀完整适用要件。",
    )


def snapshot_catalog_for_points(review_points: list[ReviewPoint]) -> list[ReviewPointDefinition]:
    seen: set[str] = set()
    snapshot: list[ReviewPointDefinition] = []
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        if definition.catalog_id in seen:
            continue
        seen.add(definition.catalog_id)
        snapshot.append(definition)
    return snapshot


def select_standard_review_tasks(
    text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPointDefinition]:
    active_tags = _build_active_task_tags(text, extracted_clauses)
    selected: list[ReviewPointDefinition] = []
    seen: set[str] = set()
    for definition in CATALOG:
        if definition.catalog_id in seen:
            continue
        if not definition.scenario_tags or any(tag in active_tags for tag in definition.scenario_tags):
            selected.append(definition)
            seen.add(definition.catalog_id)
    return selected


def _build_active_task_tags(text: str, extracted_clauses: list[ExtractedClause]) -> set[str]:
    active_tags = {
        "policy",
        "contract",
        "template",
        "consistency",
        "structure",
        "scoring",
    }
    project_type = _first_clause_value(extracted_clauses, "项目属性")
    procurement_target = " ".join(
        filter(
            None,
            [
                _first_clause_value(extracted_clauses, "采购标的"),
                _first_clause_value(extracted_clauses, "品目名称"),
                text,
            ],
        )
    )
    if project_type == "服务":
        active_tags.update({"service", "personnel"})
    if project_type == "货物":
        active_tags.update({"goods"})
    if "家具" in procurement_target:
        active_tags.update({"goods", "furniture"})
    if "物业" in procurement_target:
        active_tags.update({"service", "property"})
    if _first_clause_value(extracted_clauses, "中小企业声明函类型"):
        active_tags.add("policy")
    return active_tags


def _first_clause_value(extracted_clauses: list[ExtractedClause], field_name: str) -> str:
    for clause in extracted_clauses:
        if clause.field_name != field_name:
            continue
        if clause.normalized_value:
            return clause.normalized_value
        if clause.content:
            return clause.content
    return ""


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", text)
    return normalized.strip("-") or "GENERIC"
