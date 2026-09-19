"""世界层（DESIGN.md §5）。

模块划分：
- map          瓦片地图 / chunk 化（可变地图底座）
- pathfinding  A* + chunk 增量失效
- economy      经济与守恒（T1 经济守恒断言）
- matter       物质熵增
- chaos        混沌事件
- authority    权力牙齿（M5）
"""
