"""感知层 — Agent 与世界的唯一出口（C2，M1 落地，M0 仅占位）。

模块划分：
- senses        感官通道：视/听/触/内感受（M1 全开；嗅觉与语言判定 M2）
- propagation   传播引擎（通道无关：衰减 + 阻断 + 修正三要素）
- language      语言判定（识字率/行话/阶层用语，M2）
- salience      显著性（只报告值得注意的）
- impulse       念头注入
- profiles/     物种级 profile（不是角色级）：human(M1) | cat·dog·raven(M6 前仅占位）
"""
