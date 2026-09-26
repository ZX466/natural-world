"""T5 golden 场景（DESIGN §16 T5：10 种子 × 10 游戏日 · 断言宏观结果）。

脚手架由 M4-C3（配置/文档域=cline）按裁 14-6「D 批担 T5」预置：
- `seeds.py`   种子清单（写死常量，C5 不用 random/time 派生）
- `driver.py`  有界虚拟时钟驱动器（帧序对齐 `sim/api/ws.py::run_world_driver`）
- `test_golden_smoke.py` 1 种子 × 1 游戏日冒烟（**不含断言组**）

**断言组（守恒 / 差事完成率 / 无孤儿变更）不在本包内**——等 D 批行为链落地后按
`docs/arch/t5-golden-scaffold.md` 的脚手架提案填。验收只认 DESIGN §16 分级表，
不认「观感真实」这类不可证伪指标（§16 末、§19）。
"""
