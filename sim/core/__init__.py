"""确定性内核 — M0 交付主体（docs/arch/m0-core.md）。

模块划分：
- clock       游戏时钟：tick 唯一权威、倍速、战斗时间尺切换、昼夜/集市日纯函数派生
- rng         分流 RNG（PCG64）：按 subsystem 派生流，禁全局实例（m0-core §2）
- entropy     混合熵注入：熵源只出现在 EntropyMixer 内部，注入必须走 apply 落日志（C5）
- events      WorldEvent（frozen）+ EventBus.apply(event) 唯一写路径（C4）
- calendar    历法/节气派生（纯函数，不落状态，减少快照体积）
- persistence EventStore Protocol（append / read_range / snapshot）；表结构归 opencode TASK-001
"""
