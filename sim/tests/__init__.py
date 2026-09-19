"""测试分级 T1-T5（DESIGN.md §16）。M0 只跑 T1/T2，两者都不需要 LLM。

- invariants/  T1 六类不变量断言（因果溯源/信息边界/经济守恒/幻觉隔离/历史不可销毁/材料守恒）
- replay/      T2 回放确定性（seed + 事件日志 → 状态逐位一致）+ 静态扫描断言
- fixtures/    T3 用录制 LLM 输出（真模型测试进 nightly 不进 CI）
- golden/      T5 golden 场景（10 种子 × 10 游戏日，断言宏观结果）
"""
