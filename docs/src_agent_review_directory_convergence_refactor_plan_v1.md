# 《src/agent_review 目录收敛重构方案 v1》

## 1. 背景

当前 `src/agent_review` 已形成较完整主链，但目录结构仍保留快速迭代时期特征：

- 根目录平铺过多大文件
- 新旧链路模块并存但未分层
- compliance / adjudication / app 入口职责分散
- 法律依据相关模块未聚拢
- `__pycache__`、`.DS_Store` 等杂物进入源码树

这会导致：

- 新成员难以快速理解主链
- 模块边界不清，后续继续开发时容易重复造轮子
- “新主链 / 旧兼容链 / 辅助链”关系不明确

## 2. 本轮目标

本轮只做“目录收口”，不做主链语义重写。

目标：

1. 清理源码树杂物
2. 建立 `app / compliance / adjudication_core` 三个一级包
3. 将入口层、合规桥接层、裁决层模块迁入对应包
4. 在旧路径保留兼容导出，保证现有 import 与 CLI 不断裂
5. 用测试验证重构未破坏主链

## 3. 收口原则

### 3.1 目录服务主链，不服务历史命名

目录要能反映“收到文件之后系统怎么跑”，而不是单纯按技术名词堆放模块。

### 3.2 低风险优先

优先移动职责明确、边界稳定的模块：

- app 入口
- compliance bridge / embedded engine / legal basis
- adjudication / applicability / quality gate

暂不拆：

- `pipeline.py`
- `review_point_catalog.py`
- `fact_collectors.py`
- `reporting.py`

### 3.3 兼容优先于纯净

旧模块路径继续保留轻量兼容层，避免：

- 测试 monkeypatch 路径失效
- 外部脚本调用失败
- `python -m agent_review.cli` / `python -m agent_review.web` 失效

## 4. 目标结构

```text
src/agent_review/
  app/
    cli.py
    web.py

  compliance/
    authorities.py
    bridge.py
    embedded_engine.py
    external_data.py
    legal_basis.py

  adjudication_core/
    applicability.py
    authority_bindings.py
    core.py
    merge.py
    quality.py
    review_quality_gate.py

  ... 其余 parser / planning / rules / llm 主链模块暂保留原位
```

## 5. 兼容策略

在旧路径保留兼容文件：

- `agent_review.cli`
- `agent_review.web`
- `agent_review.agent_compliance_bridge`
- `agent_review.embedded_compliance_engine`
- `agent_review.embedded_compliance_authorities`
- `agent_review.external_data`
- `agent_review.legal_basis`
- `agent_review.adjudication`
- `agent_review.applicability`
- `agent_review.review_quality_gate`
- `agent_review.quality`
- `agent_review.merge`
- `agent_review.authority_bindings`

兼容文件只做两件事：

1. 从新包 re-export
2. 保留 `main()` 执行入口

## 6. 本轮不处理的问题

- 不拆分 `pipeline.py`
- 不改审查点模型
- 不改 parser 主链命名
- 不调整报告结构
- 不清理旧 review catalog 的业务语义

## 7. 验证方式

至少验证：

1. CLI 入口测试
2. Web 入口测试
3. compliance bridge 测试
4. adjudication / applicability / quality gate 测试
5. 若干核心 pipeline / engine 回归

## 8. 后续建议

完成本轮后，再进入第二轮收口：

1. 把 parser 子系统明确收成 `load -> structure -> extract`
2. 把 `review_point_catalog` 标记为 legacy 或迁入 planning/legacy
3. 拆分 `pipeline.py` 与 `reporting.py`
4. 将法规与 authority 进一步统一成单一 legal/authority 语义层
