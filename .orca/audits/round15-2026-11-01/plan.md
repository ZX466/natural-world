# 第十五轮实施计划

目标：按本树 talking 第十五轮派单完成离线推进、程序化音效，以及 T5/soak 取证。
基线：5a48f7c；第十四轮已由主树收编，不同步 main、不重复主树 ensure_schema 修复。
执行：Codex 在既有工作树逐项执行；Claude 负责收编复核；沟通仅本树 talking。

## 全局约束

协议保持 1.14；不改冻结 DESIGN；不动真实 world.db、npm 依赖、阈值常量和迷雾登记。
所有行为先 RED 后 GREEN；Python 使用 uv；不用浏览器、付费模型或新音频依赖。
每个提交附 Co-Authored-By: Claude Code <noreply@anthropic.com>。

## 1. 离线推进（当前执行）

选择：墙钟只在 lifespan 边界采样一次，以当前分支最新检查点时间为水位；没有检查点时
取本分支创建时间。引擎仅接受显式 offline_seconds，不读墙钟。先装好全部确定性钩子，
补跑成功才创建两个后台任务。维持既有 1x 时间尺：普通 60 tick/真实秒，战斗 1 tick/秒；
离线固定 1x，最多 86400 tick，每批不超过 4 秒且不超过 240 tick，之后恢复原倍速。
不采用在裸 restore_world 中补跑：那里尚无 NPC/火灾/建造钩子。

文件与接口：
- 新增 sim/world/offline.py：advance_offline(loop, *, offline_seconds, flush, max_ticks=86400)
  -> OfflineResult；flush(events, consumed_seconds, final) 负责同事务写入与控制水位。
- 新增 sim/core/persistence/offline_store.py：读取/解析当前分支的墙钟水位，兼容 epoch 与 ISO；
  零墙钟采集、零玩家档写入。
- 修改 world_restore.flush_world：可注入 checkpoint_at 与 force_checkpoint；空事件末批也
  保存完整游标，不编造事件、不反复补同一段时间。中间水位按已处理时长推进，末批水位置为
  本次启动采样时刻；超上限部分丢弃并记录 offline.capped。
- 修改 main：在钩子装配之后补跑、在 LLM/世界后台任务之前完成；普通 on_flush 行为不变。
- 测试 sim/tests/test_offline_progress.py：分钟补跑、cap、暂停/倍速/战斗、无事件末批、
  事务回滚、重复启动、参数/时钟偏移、分支隔离、两遍重放与玩家档不变。

- [x] RED 单测及启动集成测试，记录与派单事实差异（ffe590f）。
- [x] 实现纯推进/持久化水位，目标/E-1/快照 41P，全量 3056P。
- [x] 文档与数字证据归档，独立提交 4769418。

## 2. 音效（依次执行）

选择：已有 Phaser WebAudio 上合成确定性短音，默认静音、默认音量 0.25；用户在设置
明确开启后，首次游戏点击/按键才解锁。事件适配与音频后端分离，断开/切页/场景销毁即停。
不制造音频帧；只消费已有 voxel、combat、actors/tile/fire 表现信息，按主角听觉范围过滤，
不对首次快照、内心活动、任务提示或隐藏状态发声。不合成人声/BGM。

- [x] CodeGraph 定位 scene/runtime/store/settings；确认帧能提供的音源。
- [x] RED：voxel/fire/footstep/combat 映射、首快照静默、静音/解锁/范围/销毁、假 AudioContext。
- [x] 实现 client/src/game/audio 下的适配与合成，接场景和设置；不加依赖。
- [x] docs/arch/audio.md 已说明默认行为/亲听入口；客户端 337P、类型/Lint/格式/协议全绿。

Ruling（用户明确答复）：服务端 lights=[] 且无 fire.ignited 出站；本轮只交付脚步/挖放/
战斗，火声客户端映射做好，真实火场另列缺口。不得为火声改后端或协议。

## 3. T5 取证

- [ ] 检查十种子全量实际运行成本；先跑一个种子并重跑验证确定性。
- [ ] 可在交付前完成才跑十种子；否则交付单种子 {cases,passed,rate}、耗时和完整估算，
  明确未完成十种子，不开启会阻塞交付的 1.5 小时任务。
- [ ] baseline.json 记录种子与汇总中位/最差值，更新过时注释，不定线。

## 4. soak 取证

- [ ] 复核死亡移出 WorldState.entities 的阶段 B 前提；更正注释，不改 0 常量。
- [ ] 构造确定性真实 npc.death 场景，跑 N 游戏日并重跑，归档死亡/净流失/天数推导。
- [ ] 只报告悬空 perf 文档，不修复；不把观察值写成断言阈值。

## 交付与复核

所有变更自审、全门禁通过后回写 talking 与仅本树 memory §7；只提交本地。
门禁：pytest -m "not bench"、ruff check/format、pyright；client 协议生成/typecheck/lint/
prettier/vitest；两资产 --check、实现程度检查、uv lock --check。
重点：非法墙钟/分支、离线中断与无事件尾部、无模型调用、初次进场静默、资源释放。
主观音效验收必须用户亲听，交付只能声明技术测试结果。
