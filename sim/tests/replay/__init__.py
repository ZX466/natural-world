"""T2 回放确定性测试（DESIGN.md §16、docs/arch/m0-core.md §9）。

骨架（M0）：
1. 创世（固定 seed）→ 跑 N tick（含若干熵注入与移动）→ 记录状态哈希。
2. 从事件日志重放同 N tick → 状态哈希逐位相等。
3. 静态扫描断言：无 `import random`、无 handler 之外的 WorldState 写入、RNG 调用顺序确定。
"""
