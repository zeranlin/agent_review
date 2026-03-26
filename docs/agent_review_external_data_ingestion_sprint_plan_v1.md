# 《agent_review 外部数据接入实施 Sprint 清单 v1》

## 目标

把以下 5 份外部数据接入 `agent_review` 主链，形成“法规索引底座 + 品目画像底座 + review point 映射桥”：

1. `authorities.json`
2. `clause-index.json`
3. `review-point-authority-map.json`
4. `review-domain-map.json`
5. `catalog-knowledge-profiles.json`

接入原则：

- 先做离线可读、可回退的数据层
- 再做 `legal_basis / DocumentProfile / DomainProfile` 的最小接线
- 不把外部知识直接当审查结论，只作为法理、路由和风险画像增强
- 法律解释边界不清时保留 `manual_review_required`

## Sprint 1：数据落盘与运行时 Loader

目标：让 `agent_review` 可以稳定读取外部数据，不影响现有主链。

任务包：

- 在仓库内建立 `data/legal-authorities/index`
- 在仓库内建立 `data/procurement-catalog`
- 复制 `authorities.json`
- 复制 `clause-index.json`
- 复制 `review-domain-map.json`
- 复制 `catalog-knowledge-profiles.json`
- 复制 `catalogs-full.json`
- 补 `review-point-authority-map.json` 的 `agent_review` 版本
- 新增统一 loader 模块
- 新增基础测试：数据文件可加载、关键字段存在

完成标准：

- 主程序可在隔离环境下读取这些 JSON
- 文件缺失时不报错，自动回退到当前内置逻辑

## Sprint 2：法规索引接入 legal_basis

目标：让 `legal_basis` 从“纯手写 registry”升级为“内置 registry + 外部法规索引 fallback”。

任务包：

- 将 `review-point-authority-map` 接入 `legal_basis`
- 将 `catalog_id -> clause_ids -> clause-index` 做成可查询链
- 将 `clause-index` 转换成 `LegalBasis`
- 保留当前 `LEGAL_BASIS_REGISTRY` 为第一优先级
- 对外部映射增加去重与回退
- 将 `requires_human_review_when` 暂存为边界提示接口
- 新增测试：`RP-SCORE-005`、`RP-QUAL-003` 等能命中外部法规条文

完成标准：

- review point 在内置 basis 缺失或不足时，可自动补外部法规依据
- 不改变现有已稳定通过的基础测试行为

## Sprint 3：品目画像接入 DocumentProfile / DomainProfile

目标：让 `DocumentProfile` 在陌生招标文件场景下，能利用官方品目映射和外部画像产生更稳定的 domain candidate。

任务包：

- 将 `catalog-knowledge-profiles.json` 转换成 `agent_review` 可用画像 seed
- 新增 `external domain profile candidate matcher`
- 将 `review-domain-map.json` 接入官方品目到审查领域映射
- 把外部候选并入 `DocumentProfile.domain_profile_candidates`
- 把外部候选并入 `profile_activation_tags`
- 对家具、医疗设备、农林绿化等高频样本补回归测试

完成标准：

- 未知文件或陌生品目下，`domain_profile_candidates` 不再只依赖本地硬编码 profile
- 不把外部品目结果当唯一真相，保留 `confidence` 和回退

## Sprint 4：主链利用与评测闭环

目标：把外部数据真正用于审查点激活、抽取需求和回归评测。

任务包：

- 将外部画像带来的 routing tags 接入 review planning
- 将高价值 profile marker 接入 extraction demand 扩展
- 将 `requires_human_review_when` 接入 formal/manual 边界提示
- 在 unknown sample regression 中增加外部数据是否命中的统计
- 增加“升级前后 baseline diff”对比项：
  - 法规依据命中数
  - domain profile candidate 稳定度
  - manual/filter rate

完成标准：

- 外部数据接入后，不只是“能读”，而是能提升陌生文件处理稳定性
- regression 报告能看见提升或退化

## 本轮直接执行范围

本轮先执行 Sprint 1 和 Sprint 2 的主干，并落 Sprint 3 的最小入口：

- 数据落盘
- loader
- `legal_basis` 外部 fallback
- `DocumentProfile` 外部品目画像候选最小接入

Sprint 4 先只保留任务清单，不在本轮深入实现。
