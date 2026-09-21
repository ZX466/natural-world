"""NPC 层（DESIGN.md §5；M2 起落地，M0 仅占位）。

模块划分：
- model       NPC 数据模型与持久人格
- needs       需求系统（触发门控的输入之一）
- schedule    日程/作息
- utility     L1 效用 AI（兼 LLM 断线兜底）
- memory      记忆检索打分缝（读侧；M2 标量，M3 接向量检索）
- body        身体状态（内感受叙事化的数据源）
- society     社会关系（有向、不对称）
- demography  人口学（L0 千人级统计模拟）
"""
