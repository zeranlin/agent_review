from pathlib import Path
import json

from docx import Document
from PIL import Image

from agent_review.engine import TenderReviewEngine
from agent_review.llm import QwenReviewEnhancer
from agent_review.models import (
    AdoptionStatus,
    ClauseRole,
    ConclusionLevel,
    FileType,
    FindingType,
    Recommendation,
    ReviewMode,
    ReviewPointStatus,
)
from agent_review.outputs import write_review_artifacts
from agent_review.parsers import load_document, load_documents
from agent_review.parsers.ocr import run_ocr
from agent_review.parsers.vision_ocr import VisionOcrResult
from agent_review.reporting import (
    render_formal_review_opinion,
    render_markdown,
    render_opinion_letter,
)


def test_detects_manual_review_for_attachment_markers() -> None:
    text = """
    项目概况
    采购需求详见附件。
    供应商资格要求：具有相关资质。
    评分标准见附表。
    提交截止时间：2026年4月1日。
    付款方式：以正式合同为准。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert any(
        item.finding_type == FindingType.manual_review_required for item in report.findings
    )
    assert report.manual_review_queue
    assert report.scope_statement
    assert report.file_info.file_type in {
        FileType.complete_tender,
        FileType.procurement_requirement,
        FileType.mixed_document,
    }
    point_map = {(item.dimension, item.title): item for item in report.review_points}
    point = point_map[("采购范围清晰度", "采购范围清晰度依赖附件或外部材料")]
    assert any(source.startswith("finding:manual_review_required:") for source in point.source_findings)
    assert point.status == ReviewPointStatus.manual_confirmation


def test_detects_restrictive_terms_warning() -> None:
    text = """
    采购需求
    本项目要求原厂服务团队，本地注册地供应商优先。
    资格要求
    供应商应具备相关资质。
    评分标准
    采用综合评分法。
    提交截止时间：2026年4月1日。
    付款方式：按合同执行。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert any(item.title == "发现潜在限制性竞争表述" for item in report.findings)
    assert any(item.rule_name == "指定品牌/原厂限制" for item in report.risk_hits)
    assert any(item.legal_basis for item in report.risk_hits if item.rule_name == "指定品牌/原厂限制")
    assert not any(item.rule_name == "主观评分表述" for item in report.risk_hits)
    assert report.overall_conclusion in {ConclusionLevel.revise, ConclusionLevel.reject}


def test_detects_sme_personnel_and_contract_risks() -> None:
    text = """
    项目名称：某服务项目
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下，限女性，身高160以上。
    人员更换须经采购人同意，采购人有权直接指挥现场人员。
    采购人拥有最终解释权。
    尾款根据采购人满意度考核后支付。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    titles = {item.title for item in report.findings}

    assert "专门面向中小企业却仍保留价格扣除" in titles
    assert "服务项目声明函类型疑似错用货物模板" in titles
    assert "性别限制" in titles
    assert "采购人直接指挥" in titles
    assert "采购人单方解释或决定条款" in titles
    assert "尾款支付与考核条款联动风险" in titles


def test_detects_project_structure_and_template_conflicts() -> None:
    text = """
    项目名称：某物业服务项目
    采购标的：物业管理服务
    品目名称：办公家具
    项目属性：服务
    所属行业：工业
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    合同条款中写明质保期2年。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    titles = {item.title for item in report.findings}

    assert "项目属性与所属行业口径疑似不一致" in titles
    assert "项目属性与声明函模板口径冲突" in titles
    assert "服务项目保留货物类声明函模板" in titles
    assert "专门面向中小企业却保留价格扣除模板" in titles
    assert "项目属性 vs 品目名称" in titles
    assert "项目属性 vs 所属行业" in titles
    assert "项目属性 vs 中小企业声明函" in titles
    assert "baseline_risk_rules" in report.rule_selection.core_modules
    assert "sme_policy" in report.rule_selection.core_modules
    assert "template_conflicts" in report.rule_selection.core_modules
    assert "project_structure" in report.rule_selection.enhancement_modules
    assert "service" in report.rule_selection.scenario_tags


def test_missing_dimension_generates_missing_evidence() -> None:
    text = "这是一份极短的文本，只提到项目概况。"
    report = TenderReviewEngine().review_text(text, document_name="short.txt")

    assert any(item.finding_type == FindingType.missing_evidence for item in report.findings)
    assert report.section_index
    assert isinstance(report.relative_strengths, list)
    assert [item.stage_name for item in report.stage_records] == [
        "document_structure",
        "clause_extraction",
        "clause_role_classification",
        "dimension_review",
        "rule_evaluation",
        "consistency_review",
        "review_point_assembly",
        "applicability_check",
        "review_quality_gate",
        "formal_adjudication",
        "finalize_report",
    ]
    assert all(isinstance(item.clause_role, ClauseRole) for item in report.extracted_clauses)
    assert report.review_points
    assert report.review_point_catalog
    assert report.applicability_checks
    assert report.quality_gates
    assert report.formal_adjudication


def test_load_document_supports_docx(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("项目概况")
    document.add_paragraph("采购需求：提供运维服务。")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "预算金额"
    table.rows[0].cells[1].text = "100000"
    document.save(file_path)

    document_name, parse_result = load_document(file_path)
    assert document_name == "sample.docx"
    assert parse_result.source_format == "docx"
    assert "项目概况" in parse_result.text
    assert parse_result.tables


def test_load_document_supports_image_ocr_with_warning_when_tesseract_missing(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image = Image.new("RGB", (120, 40), color="white")
    image.save(image_path)
    monkeypatch.setattr(
        "agent_review.parsers.ocr.run_vision_ocr",
        lambda **kwargs: VisionOcrResult(
            doc_type="image",
            summary="",
            extracted_text="",
            fields={},
            confidence=None,
            warnings=["视觉 OCR 未生效: mocked"],
        ),
    )

    document_name, parse_result = load_document(image_path)
    assert document_name == "sample.png"
    assert parse_result.source_format == "png"
    assert parse_result.page_count == 1
    assert isinstance(parse_result.warnings, list)


def test_run_ocr_can_extract_table_like_rows(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "table.png"
    image = Image.new("RGB", (200, 120), color="white")
    image.save(image_path)

    def fake_image_to_string(_image, lang=None):
        return "预算金额 100000\n最高限价 90000"

    def fake_image_to_data(_image, lang=None, output_type=None):
        return {
            "text": ["预算金额", "100000", "最高限价", "90000", "备注"],
            "conf": ["90", "88", "92", "87", "86"],
            "block_num": [1, 1, 1, 1, 2],
            "par_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 2, 2, 1],
            "left": [10, 120, 10, 120, 10],
        }

    monkeypatch.setattr("agent_review.parsers.ocr.pytesseract.image_to_string", fake_image_to_string)
    monkeypatch.setattr("agent_review.parsers.ocr.pytesseract.image_to_data", fake_image_to_data)
    monkeypatch.setattr(
        "agent_review.parsers.ocr.run_vision_ocr",
        lambda **kwargs: VisionOcrResult(
            doc_type="报价表",
            summary="图片为报价表截图",
            extracted_text="",
            fields={"table_headers": ["字段", "数值"]},
            confidence=0.9,
            warnings=[],
        ),
    )

    result = run_ocr(image_path)

    assert "预算金额" in result.text
    assert result.tables
    assert result.tables[0].source == "ocr_table"
    assert result.tables[0].row_count == 2
    assert "视觉OCR摘要" in result.text


def test_load_documents_can_merge_multiple_sources(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("项目属性：服务\n采购需求：物业服务。", encoding="utf-8")
    second.write_text("合同条款\n付款方式：按月支付。", encoding="utf-8")

    document_name, parse_result, source_documents = load_documents([first, second])

    assert "等2个文件" in document_name
    assert parse_result.source_format == "multi"
    assert len(source_documents) == 2
    assert "## 文档：a.txt" in parse_result.text
    assert "## 文档：b.txt" in parse_result.text


class FakeEnhancer:
    def enhance(self, report):
        report.summary = "这是经过LLM增强的结论摘要。"
        report.llm_enhanced = True
        report.specialist_tables.summaries["sme_policy"] = "这是经过LLM增强的中小企业政策专项摘要。"
        report.recommendations = [
            Recommendation(related_issue="测试问题", suggestion="这是经过LLM增强的建议。")
        ]
        return report


class FakeClient:
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        if "补充可能遗漏但有文本依据的条款事实" in system_prompt:
            return json.dumps(
                {
                    "clause_supplements": [
                        {
                            "category": "政策条款",
                            "field_name": "分包比例",
                            "content": "文件疑似提及分包落实中小企业政策，但比例未在现有抽取结果中单列。",
                            "source_anchor": "line:8",
                            "adoption_status": "需人工确认",
                            "review_note": "分包比例出现在模糊表述中，需结合原表格确认。",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "条款角色判断做复核" in system_prompt:
            return json.dumps(
                {
                    "role_review_notes": [
                        "部分审查点证据接近模板或定义说明边界，formal 前仍应结合条款角色过滤。"
                    ]
                },
                ensure_ascii=False,
            )
        if "证据包做复核" in system_prompt:
            return json.dumps(
                {
                    "evidence_review_notes": [
                        "中小企业政策冲突审查点证据较强，但付款与满意度联动类问题仍需补充合同原文。"
                    ]
                },
                ensure_ascii=False,
            )
        if "适法性判断做复核" in system_prompt:
            return json.dumps(
                {
                    "applicability_review_notes": [
                        "专门面向中小企业且保留价格扣除的要件基本满足，可直接进入 formal 审查意见。"
                    ]
                },
                ensure_ascii=False,
            )
        if "补充近似但未命中的专项风险" in system_prompt:
            return json.dumps(
                {
                    "specialist_findings": [
                        {
                            "dimension": "专项语义复核",
                            "title": "评分因素与履约考核存在隐性耦合",
                            "severity": "high",
                            "rationale": "评分承诺与后续考核扣款口径疑似共用同一表述，可能导致重复约束。",
                            "source_anchor": "line:12",
                            "next_action": "拆分投标评分承诺与履约考核口径。",
                            "confidence": 0.88,
                            "adoption_status": "可直接采用",
                        }
                    ],
                    "specialist_summaries": {
                        "sme_policy": "中小企业政策专项仍存在模板与执行口径混杂问题。"
                    },
                    "recommendations": [
                        {
                            "related_issue": "评分因素与履约考核存在隐性耦合",
                            "suggestion": "拆分评审承诺与履约考核条款，避免形成双重约束。",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        if "补充跨章节、跨表格、跨措辞的深层冲突" in system_prompt:
            return json.dumps(
                {
                    "consistency_findings": [
                        {
                            "dimension": "深层一致性复核",
                            "title": "付款条件与满意度表述存在隐性冲突",
                            "severity": "medium",
                            "rationale": "付款条款虽未直接写考核，但满意度表述可能实际控制尾款支付。",
                            "source_anchor": "line:15",
                            "next_action": "将付款条件改为客观验收节点。",
                            "confidence": 0.66,
                            "adoption_status": "需人工确认",
                            "review_note": "需结合合同完整上下文确认付款触发机制。",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "summary": "这是经过LLM语义复核增强后的总体结论摘要。",
                "verdict_review": "基于现有事实，除已命中规则外，仍存在评分、考核、付款联动的隐性实质性风险，建议人工重点复核。",
            },
            ensure_ascii=False,
        )


def test_engine_can_apply_llm_enhancer() -> None:
    text = """
    项目概况
    采购需求详见附件。
    评分标准见附表。
    """
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    report = engine.review_text(text, document_name="demo.txt")

    assert report.llm_enhanced is True
    assert report.summary == "这是经过LLM增强的结论摘要。"
    assert report.recommendations[0].suggestion == "这是经过LLM增强的建议。"
    assert report.specialist_tables.summaries["sme_policy"] == "这是经过LLM增强的中小企业政策专项摘要。"


def test_qwen_enhancer_can_merge_semantic_review_outputs() -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    供应商需承诺服务满意度，尾款支付与履约评价挂钩。
    """
    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(
        text, document_name="demo.txt"
    )
    enhancer = QwenReviewEnhancer(client=FakeClient())
    enhanced_report = enhancer.enhance(base_report)

    assert enhanced_report.llm_enhanced is True
    assert enhanced_report.llm_semantic_review.clause_supplements
    assert enhanced_report.llm_semantic_review.clause_supplements[0].adoption_status == AdoptionStatus.manual
    assert any(item.title == "评分因素与履约考核存在隐性耦合" for item in enhanced_report.findings)
    assert any(item.title == "付款条件与满意度表述存在隐性冲突" for item in enhanced_report.findings)
    assert any(item.adoption_status == AdoptionStatus.direct for item in enhanced_report.llm_semantic_review.specialist_findings)
    assert any(item.adoption_status == AdoptionStatus.manual for item in enhanced_report.llm_semantic_review.consistency_findings)
    assert enhanced_report.llm_semantic_review.verdict_review
    assert enhanced_report.llm_semantic_review.role_review_notes
    assert enhanced_report.llm_semantic_review.evidence_review_notes
    assert enhanced_report.llm_semantic_review.applicability_review_notes
    assert enhanced_report.pending_confirmation_items
    assert any(item.stage_name == "llm_semantic_review" for item in enhanced_report.stage_records)
    llm_tasks = {item.task_name: item.status.value for item in enhanced_report.task_records if item.task_name.startswith("llm_")}
    assert llm_tasks == {
        "llm_clause_supplement": "completed",
        "llm_role_review": "completed",
        "llm_evidence_review": "completed",
        "llm_applicability_review": "completed",
        "llm_specialist_review": "completed",
        "llm_consistency_review": "completed",
        "llm_verdict_review": "completed",
    }
    markdown = render_markdown(enhanced_report)
    assert "## LLM补充条款" in markdown
    assert "## LLM裁决复核" in markdown
    assert "## LLM角色复核" in markdown
    assert "## LLM证据复核" in markdown
    assert "## LLM适法性复核" in markdown
    assert "## 待确认问题单" in markdown


def test_engine_can_review_multiple_files(tmp_path: Path) -> None:
    main_file = tmp_path / "main.txt"
    contract_file = tmp_path / "contract.txt"
    main_file.write_text("项目属性：服务\n采购需求：物业服务。", encoding="utf-8")
    contract_file.write_text("合同条款\n付款方式：按月支付。", encoding="utf-8")
    engine = TenderReviewEngine(review_mode=ReviewMode.fast)
    report = engine.review_files(
        [
            main_file,
            contract_file,
        ]
    )
    assert report.source_documents
    assert len(report.source_documents) == 2
    markdown = render_markdown(report)
    assert "## 联合审查文件" in markdown


def test_multi_file_review_detects_cross_document_consistency_issues(tmp_path: Path) -> None:
    tender = tmp_path / "tender.txt"
    scoring = tmp_path / "scoring.txt"
    contract = tmp_path / "contract.txt"
    tender.write_text(
        "\n".join(
            [
                "投标邀请",
                "采购需求",
                "项目属性：服务",
                "本项目专门面向中小企业采购。",
            ]
        ),
        encoding="utf-8",
    )
    scoring.write_text(
        "\n".join(
            [
                "评分标准",
                "综合评分",
                "价格扣除按10%执行。",
            ]
        ),
        encoding="utf-8",
    )
    contract.write_text(
        "\n".join(
            [
                "合同条款",
                "付款方式：尾款支付以采购人满意度考核为准。",
                "验收条款：按合同约定执行。",
            ]
        ),
        encoding="utf-8",
    )

    report = TenderReviewEngine(review_mode=ReviewMode.fast).review_files(
        [tender, scoring, contract]
    )

    titles = {item.title for item in report.findings}
    assert "正文 vs 评分细则跨文件一致性" in titles
    assert "正文 vs 合同草案跨文件一致性" in titles
    markdown = render_markdown(report)
    assert "## 跨文件一致性专项" in markdown


def test_fast_mode_skips_enhancer() -> None:
    text = "项目概况\n采购需求详见附件。"
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.fast)
    report = engine.review_text(text, document_name="demo.txt")

    assert report.review_mode == ReviewMode.fast
    assert report.llm_enhanced is False


def test_write_review_artifacts_outputs_base_and_final(tmp_path: Path) -> None:
    text = "项目概况\n采购需求详见附件。"
    base_engine = TenderReviewEngine(review_mode=ReviewMode.fast)
    base_report = base_engine.review_text(text, document_name="demo.txt")

    enhanced_engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    enhanced_report = enhanced_engine.review_text(text, document_name="demo.txt")

    bundle = write_review_artifacts(enhanced_report, base_report, tmp_path)

    assert Path(bundle.base_json_path).exists()
    assert Path(bundle.base_markdown_path).exists()
    assert Path(bundle.final_json_path).exists()
    assert Path(bundle.final_markdown_path).exists()
    assert Path(bundle.opinion_letter_path).exists()
    assert Path(bundle.formal_review_opinion_path).exists()
    assert Path(bundle.manifest_path).exists()
    assert Path(bundle.llm_tasks_path).exists()
    assert Path(bundle.high_risk_review_path).exists()
    assert Path(bundle.pending_confirmation_path).exists()
    assert Path(bundle.specialist_table_paths["sme_policy"]["base"]).exists()
    assert Path(bundle.specialist_table_paths["sme_policy"]["final"]).exists()

    manifest = json.loads(Path(bundle.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_paths"]["base_report"]["json"] == bundle.base_json_path
    assert manifest["artifact_paths"]["final_report"]["json"] == bundle.final_json_path
    assert manifest["artifact_paths"]["opinion_letter"] == bundle.opinion_letter_path
    assert manifest["artifact_paths"]["formal_review_opinion"] == bundle.formal_review_opinion_path
    assert manifest["stage_records"]
    assert "core_modules" in manifest["rule_selection"]
    assert "enhancement_modules" in manifest["rule_selection"]
    llm_tasks_payload = json.loads(Path(bundle.llm_tasks_path).read_text(encoding="utf-8"))
    assert all(item["task_name"].startswith("llm_") for item in llm_tasks_payload["tasks"])
    pending_payload = json.loads(Path(bundle.pending_confirmation_path).read_text(encoding="utf-8"))
    assert "items" in pending_payload


def test_write_review_artifacts_outputs_specialist_table_files(tmp_path: Path) -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(text, document_name="demo.txt")
    enhanced_report = TenderReviewEngine(
        review_enhancer=FakeEnhancer(),
        review_mode=ReviewMode.enhanced,
    ).review_text(text, document_name="demo.txt")

    bundle = write_review_artifacts(enhanced_report, base_report, tmp_path)

    for table_name in [
        "project_structure",
        "sme_policy",
        "personnel_boundary",
        "contract_performance",
        "template_conflicts",
    ]:
        assert Path(bundle.specialist_table_paths[table_name]["base"]).exists()
        assert Path(bundle.specialist_table_paths[table_name]["final"]).exists()


def test_markdown_report_uses_v2_sections() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    markdown = render_markdown(report)

    assert "## 高风险问题" in markdown
    assert "## 中风险问题" in markdown
    assert "## 审查边界说明" in markdown
    assert "## 中小企业政策一致性表" in markdown


def test_markdown_can_render_legal_basis() -> None:
    text = """
    采购需求
    本项目要求原厂服务团队。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    markdown = render_markdown(report)

    assert "法规依据" in markdown
    assert "中华人民共和国政府采购法" in markdown


def test_opinion_letter_can_render_formal_sections() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(text, document_name="demo.txt")

    opinion = render_opinion_letter(report)

    assert "# 招标文件审查意见书" in opinion
    assert "## 三、审查结论" in opinion
    assert "## 四、主要审查意见" in opinion
    assert "事实要件：" in opinion
    assert "## 五、修改建议" in opinion
    assert "## 七、审查边界说明" in opinion


def test_formal_review_opinion_can_render_high_risk_fields() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(text, document_name="demo.txt")

    formal = render_formal_review_opinion(report)

    assert "# 招标文件高风险正式审查意见" in formal
    assert "- 问题标题:" in formal
    assert "- 条款位置:" in formal
    assert "- 原文摘录:" in formal
    assert "- 问题类型:" in formal
    assert "- 风险等级:" in formal
    assert "- 合规判断:" in formal
    assert "- 法律/政策依据:" in formal


def test_formal_review_opinion_filters_template_and_weak_hits() -> None:
    text = """
    法定代表人证明书
    附：代表人性别：_____年龄：_________ 身份证号码：__________________
    一、名词解释
    采购代理机构：本项目是指某采购中心，对招标文件拥有最终的解释权。
    本项目属于专门面向中小企业采购的项目。
    对小型、微型企业给予价格扣除。
    """
    report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(text, document_name="demo.txt")

    formal = render_formal_review_opinion(report)

    assert "性别限制" not in formal
    assert "年龄限制" not in formal
    assert "采购人单方解释或决定条款" not in formal
    assert "专门面向中小企业却仍保留价格扣除" in formal
    adjudication_map = {item.title: item for item in report.formal_adjudication}
    assert adjudication_map["专门面向中小企业却仍保留价格扣除"].included_in_formal is True
    assert adjudication_map["专门面向中小企业却仍保留价格扣除"].evidence_sufficient is True
    assert adjudication_map["专门面向中小企业却仍保留价格扣除"].legal_basis_applicable is True


def test_report_contains_specialist_tables() -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert report.specialist_tables.sme_policy
    assert report.specialist_tables.personnel_boundary
    assert report.specialist_tables.contract_performance


def test_report_contains_review_point_and_formal_adjudication_skeleton() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert report.review_points
    assert report.formal_adjudication
    markdown = render_markdown(report)
    assert "## ReviewPoint" in markdown
    assert "## Formal Adjudication" in markdown


def test_rule_and_consistency_layers_prioritize_review_points() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    合同条款：验收合格后付款，但尾款根据采购人满意度考核后支付。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    point_map = {(item.dimension, item.title): item for item in report.review_points}

    rule_point = point_map[("中小企业政策风险", "专门面向中小企业却仍保留价格扣除")]
    assert any(source.startswith("risk_hit:") for source in rule_point.source_findings)
    assert rule_point.status == ReviewPointStatus.confirmed
    assert rule_point.evidence_bundle.direct_evidence

    consistency_point = point_map[("跨条款一致性检查", "验收标准 vs 付款条件")]
    assert any(source.startswith("consistency_check:") for source in consistency_point.source_findings)
    assert consistency_point.status == ReviewPointStatus.suspected
    assert consistency_point.evidence_bundle.missing_evidence_notes

    findings = {(item.dimension, item.title): item for item in report.findings}
    assert findings[("中小企业政策风险", "专门面向中小企业却仍保留价格扣除")].finding_type == FindingType.confirmed_issue
    assert findings[("跨条款一致性检查", "验收标准 vs 付款条件")].finding_type == FindingType.warning


def test_markdown_can_render_specialist_summary() -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    """
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    report = engine.review_text(text, document_name="demo.txt")
    markdown = render_markdown(report)

    assert "中小企业政策一致性表摘要" in markdown
    assert "这是经过LLM增强的中小企业政策专项摘要。" in markdown
