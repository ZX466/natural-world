"""Agent 认知层（DESIGN.md §5、§8；M1 起落地，M0 仅占位）。

模块划分：
- loop        Agent 主循环（异步，LLM 延迟不阻塞世界）
- planner     规划与重规划
- intents     Intent 契约与校验（LLM 唯一能输出的东西）
- cognition   非理性框架（M2 默认开启：确认偏误/沉没成本/习惯/创伤/情绪一致性/醉酒）
- will        意愿系统
- identity    身份锚（prompt 前缀缓存的最大头）
- monologue   独白叙事化管线（永不直接渲染 LLM 原始输出）
"""
