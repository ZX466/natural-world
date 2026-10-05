# M6-A6 实现复盘 + 内容面数据面四问核对（M6-A7，Claude 域代执行）

> 依据：M6-A7 派单（2026-10-05）·基线 main `b9eb875`·性质：复盘+核对，零代码。
> opencode 域（A7 原执行方）在途——本稿由主树代执行，复核结论供 opencode 确认。

## 1. A6 实现复盘存档（可复用手法清单新增）

**「删除不挂早退分支 = 残留态同治」**（`_project_npc_death` if/else 结构）：

- **为什么重要**：若 profile 行已删（旧库升级后重放、或 profile 删成功而健康删
  失败的半写态）而 health 行还在——挂在「profile 行 None 即 return」之下的话，
  health 删除**永远到不了**，残留态固化。改 if/else 后：profile 无行也继续走
  health 删除 ⇒ 残留态同样被治好；
- **与 A7「命名即哨兵」同族**：把「实现选择」沉淀为可复用手法的价值 = 后续
  施工单（死亡语义再扩展，如 npc_health 之外的新有界表）直接沿用该结构，
  不再踩早退坑；
- **契约一致性**：与 §24「对称删除」同源（profile/health 两表同事务同判据），
  投影幂等（行不存在 no-op）与重放第二遍安全一致。

## 2. 内容面数据面四问核对（对照 A3 预研口径）

| 问 | 核对结论 | 证据 |
| --- | --- | --- |
| ①三事件不入库论证在施工形态下仍成立？ | ✅ 成立：`ecology_phase_at`/`fauna_sightings_at` 均为 tick 纯派生（无状态无 IO），事件只承载相位/节律**跨越信号**（无治理状态、无 entry_id 谱系）——入库即复制「tick 本来就能算出的东西」（第二真相源，撞 §19.3） | `sim/world/ecology.py`/`fauna.py` 模块注+无 SQL 导入 |
| ②speech 事件化后 0015 是否本波触发？ | **否**——本波 `speech.shift` 事件只承载语域**变更信号**（payload=register_word+in_circle 布尔），**没有落 `npc_profiles` 新列**（语域是当下派生读数，不是持久状态）⇒ 0015 不占号（A10 死迁移判例兑现） | `event_validation.py` 四 payload 无 npc_profiles 列变更；迁移链 head 仍 0014 |
| ③fog.py 头注（A4 事件化口径）与实现一致？ | ✅ 一致：A4 头注写「fold=并集、幂等」；实现 `fold_fog_reveal` 逐坐标调 `reveal`（与 reveal 同源=§19.3 两路径铁律）——**新增实现与头注同 commit 对齐** | `sim/world/fog.py` 头注+`fold_fog_reveal` |
| ④soak 交叉：动物不进 entities 如何保证？ | ✅ 结构性保证：`fauna_sightings_at` 返回独立 `FaunaSighting` dataclass 元组，**从不触碰 `WorldState.entities`**（类型层即钉——动物没有 EntityState 形态） | `fauna.py` 无 entities 导入；A12 核实钉（`test_m5_soak_entity_count.py`）继续绿 |

## 3. 结论

四事件全部「走事件流、不入库、不占迁移号」——A3 预研口径在施工形态下**零偏离**；
A6 复盘手法已入档。本稿供 opencode 确认后并入其 §24.4 交接（确认项=四问核对）。
