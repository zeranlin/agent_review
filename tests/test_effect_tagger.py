from agent_review.models import DocumentNode, SemanticZone
from agent_review.ontology import EffectTag, NodeType, SemanticZoneType
from agent_review.structure.effect_tagger import tag_effects


def _effect_map(nodes: list[DocumentNode], zones: list[SemanticZone]):
    return {item.node_id: item for item in tag_effects(nodes, zones)}


def test_effect_tagger_marks_template_example_optional_and_reference() -> None:
    nodes = [
        DocumentNode(
            node_id="n1",
            node_type=NodeType.paragraph,
            title="中小企业声明函（格式）",
            text="以下为示例文本，可选填写，详见附件。",
            path="第四章 投标文件格式、附件",
        )
    ]
    zones = [SemanticZone(node_id="n1", zone_type=SemanticZoneType.template)]
    effects = _effect_map(nodes, zones)

    tags = effects["n1"].effect_tags
    assert EffectTag.template in tags
    assert EffectTag.example in tags
    assert EffectTag.optional in tags
    assert EffectTag.reference_only in tags
    assert EffectTag.binding not in tags


def test_effect_tagger_marks_catalog_and_binding() -> None:
    nodes = [
        DocumentNode(
            node_id="catalog",
            node_type=NodeType.catalog_entry,
            title="第一章 招标公告",
            text="第一章 招标公告",
        ),
        DocumentNode(
            node_id="binding",
            node_type=NodeType.paragraph,
            title="投标人资格要求",
            text="投标人须具备相关资质。",
        ),
    ]
    zones = [
        SemanticZone(node_id="catalog", zone_type=SemanticZoneType.catalog_or_navigation),
        SemanticZone(node_id="binding", zone_type=SemanticZoneType.qualification),
    ]
    effects = _effect_map(nodes, zones)

    assert effects["catalog"].effect_tags == [EffectTag.catalog]
    assert effects["binding"].effect_tags == [EffectTag.binding]


def test_effect_tagger_distinguishes_policy_background_reference_and_public_noise() -> None:
    nodes = [
        DocumentNode(
            node_id="noise",
            node_type=NodeType.paragraph,
            title="页眉",
            text="深圳政府采购网 公开信息",
        ),
        DocumentNode(
            node_id="policy",
            node_type=NodeType.paragraph,
            title="政策说明",
            text="根据《政府采购促进中小企业发展管理办法》执行。",
        ),
        DocumentNode(
            node_id="reference",
            node_type=NodeType.paragraph,
            title="资格要求",
            text="投标人资格要求：投标人须具备相关资质，详见附件1。",
        ),
        DocumentNode(
            node_id="appendix_ref",
            node_type=NodeType.paragraph,
            title="附件引用",
            text="采购需求详见附件1。",
        ),
        DocumentNode(
            node_id="scoring",
            node_type=NodeType.table_row,
            title="检测报告",
            text="检测报告 | 5 | 提供得分",
        ),
    ]
    zones = [
        SemanticZone(node_id="noise", zone_type=SemanticZoneType.public_copy_or_noise),
        SemanticZone(node_id="policy", zone_type=SemanticZoneType.policy_explanation),
        SemanticZone(node_id="reference", zone_type=SemanticZoneType.qualification),
        SemanticZone(node_id="appendix_ref", zone_type=SemanticZoneType.appendix_reference),
        SemanticZone(node_id="scoring", zone_type=SemanticZoneType.scoring),
    ]
    effects = _effect_map(nodes, zones)

    assert effects["noise"].effect_tags == [EffectTag.public_copy_noise]
    assert effects["policy"].effect_tags == [EffectTag.policy_background]
    assert effects["reference"].effect_tags == [EffectTag.binding]
    assert effects["appendix_ref"].effect_tags == [EffectTag.reference_only]
    assert effects["scoring"].effect_tags == [EffectTag.binding]
