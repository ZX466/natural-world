"""LLM 客户端层（DESIGN.md §4、§8、§15；M1 起落地，M0 仅占位）。

模块划分：
- client     OpenAI 协议客户端（OpenAI / DeepSeek / 通义 / Ollama / LM Studio）+ 重试（tenacity）
- profiles   单活跃 profile、手动切换（不自动容灾）；api_key 只在此层与持久层之间流转
- prompts/   prompt 装配规范（顺序固定、前缀缓存命中）+ 出戏禁词过滤
"""
