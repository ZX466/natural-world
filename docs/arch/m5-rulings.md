# 裁决 22（2026-09-27，Claude 主导）——M5 收编轮待裁四项 + M4 宣告条件

> 承裁 21（`bc8962f`）。本轮五单收编（main `973ef02`）带出四项待裁 + 一条关键路径动作。

## A. cline 抓出的派单勘误（采认）

1. **F1/F3 归批次 B**：cline C1 抓出我派单 M5-C1 写「批次 A=F3+0008-a」系错误——
   F1/F3 是数据面分叉前置（G-6 解锁条件），批次 A 是时间刻度+混沌。采认其按证据挂
   批次 B 的改法（m5-plan §2 已注理由）。**勘误记档：派单写批次号前先对 m5-plan §2
   依赖序核对**。
2. **M5-K2 号段冲突**：README 旧台账「M5-K2=anchors 路径参数归一（`5cf58c9`，M2 时点
   已完成）」与新派「M5-K2=D-8 文档订正」撞号。**裁：D-8 保留 M5-K2 号（本轮交付实体），
   旧条目改记 M2-K2b**（归档改号，不追改 git 历史）。cline 下一单顺手改 README 台账行。

## B. codex 报备的 T3 侧同构真空（7 条）

裁 **不同步加固**。理由：codex 已实测 7 条全是 leading_echo 句首反问形态（设计意图），
T4 剥包裹口径套上去后豁免后命中=[] 全合法——T4 口径已是 T3 的严格收紧。T3 门禁
保持现状，**留 codex 一条观察项**：若未来 T3 语料新增非 leading_echo 形态，卫生断言
须按 T4 裸文本口径写（新条目新口径，存量不动）。

## C. cline m5-plan §6 遗留三问

1. **§6-③「断多久算已变」**：定标为「读档分叉落地后，分叉点后的第一个游戏日日切即算
   已变」（日切=世界自转的最小可感单位，与 §10 时间锁定口径同源）。演练级断言按此写，
   不再挂「未定标」。具体 tick 数随批次 E 施工定（在断言里写常量）。
2. **§6-⑤「M5 是否扩 T4 词表」**：**M5 不扩**。T4 词表扩面走既有 CR 流程按需触发
   （本轮 P4-05 已示范），不因里程碑切换而预设扩面。
3. **批次 C 权力牙齿验收判据**（§16/§18 明写不可证伪）：批次 C 开工前补裁，届时由
   codex 出可证伪断言提案（同 T4 预研先例），本裁不预填。

## D. pi 报备的实测缺口（登记）

- §12「快照 ≤5MB/份」至今无人实测（只测到 pos-only 447B 代理）——**批次 E 真快照
  落地时补测**，否则 2GB 体积预算无依据。记 opencode 批次 E 交付清单一行。
- baseline.json 无 RETRIEVAL_* 行（用例晚于 baseline commit）——pi before=本机实测
  存照已落 memory ⑤节；**after 复跑**：F3 已在 main（本轮收编），pi 立即可跑。

## E. M4 宣告

T4 判定校准（S8）已收编，重跑条件齐（T4_RUN=1 + key + 零重试，46 条出齐）。
**绿即宣告 M4 收官**——本文件不预写宣告辞，宣告辞随 T4 正式判读回执落 memory。

---

# 裁决 24（2026-09-28，Claude 主导）——D3 范围确认+切分批准+S1 复核采认

## A. opencode D3 范围确认（答复其回执第 1 条）

**0008 四件确认无误**：a（npc_profiles 复合主键）+ d（evidence_branch_id）+
parent_branch_id（裁 3）+ protected（裁 9）。b（UNIQUE 索引改复合）/ c（global_seq）
确按裁 10 (i)/裁 2 作废——我 D3 卡写「0008 四件」即此意，口径对齐。
**D3 切 a/b/c 三单：采。** a 纯迁移先行（G-6 解锁）；b/c 等 S1 复核件已收编
（本裁即收编），口径已定死：(c) async 直写维持 + R-1/R-2/R-3 三红线随附。
**顺手 bug 采认**：npc_store.py:625 跨分支写缺口随 0008-a 一并封（你稿 §5-C1 应用面）。

## B. codex S1 复核采认

裁 6/7 维持原判+R-1（clone 后 content 逐字节不变断言）/R-2（superseded_by 零跨分支
悬空）随 opencode D3-b 交付；**R-3 写进交付纪律**（S1 词表活资产，扩面时老分支记忆
残留禁词的系统性缺口——运行期不可判，交付说明留痕）。
**F-4 词面缺口（存个档/开个新档不中）**：钉为已知项采认；批次 C 前若补，单开 CR
不夹带——同意，记批次 C 开工检查单一行。

## C. cline 报 preaudit 两处过期（派 codex 小单收口）

m4-closure-preaudit.md L57-59（env 仍写 claude-sonnet-5 的过期表述）与 L94（44 条
未落）——**派 codex 顺手改**（其域文档，两行级），随 M5-S1b 或独立小提交。

## D. pi after 采认+baseline 建议

F3 SQL 增量 +0.037ms（1.07x）无破线，对账点 5 关闭，**pi↔opencode 交叉对账九点
全部收口**。baseline.json 补 M3-P2/M4 新增 bench 行——登记 CI 域（cline）下一波
nightly 重生成时随带，不单独开单。

---

# 裁决 25（2026-09-28，Claude 主导）——D3-a 收编+两设计决定裁定+批次 B 派发

## A. D3-a 采认（main `aee98c7`，1661 passed）

主树独立复核：0008 往返（upgrade→downgrade→upgrade）scratch DB 实跑通过，
与其门禁一致。16 钉子+跨分支写封口全采认。**G-6 解锁最后一前置就此关闭。**

## B. 两个设计决定裁定

1. **成对 CHECK 写单向**：采。`(NULL, seq)` 是既有行常态，等值会把存量行打成非法——
   与 0005 等值先例的区分理由（天生成对 vs 引用可空）成立。
2. **parent_branch_id 生产侧不在本刀**：采。不破冻结事件基线（裁 7/8 精神）；
   架构域接线（WorldEvent 加字段+工厂填值+感知层透传）**归 Claude 域，随 D3-b
   收编轮同轮落**——存储层已打通（append 读 event 键+validate 校验+钉子），接线面
   只剩事件模型，正好与 fork 编排一次做完。

## C. 派发连锁

- **kilo 批次 B 大单（M5-K3）即刻派**：fast_forward 新 action（D-2）+ session 首帧
  （D-5+D-6 合并）+ GET /api/anchors/current（D-9）+ D-3 暂停批（幂等单值，连带清
  G-1~G-4）——摸底三条（路由顺序坑/纯新增确认/G-1~G-4 位置零漂移）已作施工依据。
- **opencode D3-b 随即派**：fork 事务+克隆（裁 6 (c)+裁 10 (i)）+ R-1/R-2 断言+
  P1 强制 flush+裁 5 append 校验。
- D3-c（R2 三断言+seed 连续）在 b 收编后派；裁 6.3 branches.seed (a)/(b) 随 D3-c 派单裁。

## D. 小项

- codex S1b（preaudit 两行收口）维持待领——不阻塞任何件。
- 本轮 warnings 30（+4）：D3-a 新增文件撞 GBK 控制台编码的既有模式，非回归，
  登 opencode 域观察项。

---

# 裁决 26（2026-09-28，Claude 主导）——D3-b/K3 收编+偏离点裁定+批次 B 合流

## A. opencode D3-b 采认（fork 事务+克隆，22 钉子）

裁 6 (c) async 直写+裁 10 (i) 重映射落地；R-1（content 逐字节不变）/R-2
（superseded_by 零跨分支悬空）断言随附；R-3 交付纪律留痕。**编排缝接口清单**
在 D3-c 收编轮消费（我域 driver 编排+store rebind）。

## B. kilo K3 采认（批次 B 四面，71 钉子，门禁 1724+client 21）

G-1~G-4 逐条核销（含白盒钉）采认；fast_forward 受理静默+叙事化时长
（advance_hours 1..168）+抑制逐帧 delta+终态全量快照（D-7）设计全采；
session_state 零原始数值+notice 戏内口语行采认；D-9 路由顺序坑已防。

## C. 偏离点裁定

1. **kilo 动 main.py 8 行：采**（ws_endpoint 发 session_state 首帧/ControlState/
   frames_of——施工面延伸非越界；原语义零改动）。
2. **两处既有约束收窄：采**（返回 dict|list|None 仅读档两帧；K4 §1.2 栈方案被
   D-3 幂等单值取代——四宗缺陷留档，日期化增补合规）。
3. **既有钉子 6 处随契约更新：采**（协议真变非放宽；WS 鉴权两帧位移是必然）。
4. **protected 无写入方暂不切列：采**——POST/CRUD（Claude 域）落地单再切，
   登记批次 C 检查单。
5. **收编缝（Claude 域即做，`321eaea`）**：返回类型放宽后既有测试 153 处 pyright
   错——test_ws_gateway `_reply` 单帧窄化包装（48 点）+两帧场景直用原函数
   （窄化截首帧实测 2 例红，教训入坑单）；**WorldEvent.parent_branch_id 生产侧
   接线**（裁 25-B②兑现：字段+to_store_dict 透传+工厂不收参防误用+4 钉子）。

## D. 派发连锁

- **opencode D3-c 即派**：R2 三断言+断言 D seed 连续+可比字段集白名单；
  branches.seed (a)/(b) 随卡裁。
- **我域批次 B 行为面续件**：driver fork 编排（等 D3-c 收编）+ protected 切列
  （CRUD 单）+ P5 措辞已落（7dac4e7）。
- pi：K3 已注明「可跑红线验证」——fast_forward 红线落 thresholds 提案可启动。

---

# 裁决 27（2026-09-28，Claude 主导）——批次 B 收官+D3-c/K4/S2/P3 采认+种子裁定+soak 定标机触发

## A. opencode D3-c 采认（main `e109d44`，批次 B 收官）

R2 三断言全采——**B 组口径修正采认**（子分支事件流必然少一半，改「父前缀折叠
∘子自身折叠」沿链回放，复用同一批 fold_* 守 C2 单一来源）；C 照妖镜已验牙
（注入单分支回归→精确一红）；断言 D PCG64 状态承接+fail-closed；可比字段集
归一化（evidence_ref=(分支,seq) 二元组防 NULL 语义假红）。**批次 B（双轨存档
分叉重放）正式收官。**

## B. branches.seed 裁定（opencode 建议随裁）

**采 (b2)**：`branches.rng_state`（一支 add_column 的 0009），fork 事务内原子落，
分支自带状态支持连续分叉链；(b1) 快照形态连续分叉祖父状态无处取，否。
**(a) 单独承接实测必跳变**（registry 不含 PCG64 抽签进度）——`fork_from_anchor
(rng_state=...)` 透传位已留好、钉子零改动承诺。0009 随批次 A 开工单落。

## C. kilo K4 采认+待裁序裁定

五条铁律+四候选面+CRUD 契约 v2 全采。**D-10~D-16 裁定**：
- **D-10 = 权力完全不可见（纯 Agent 内部，协议面零改动）**——与裁 21-C② 可砍性
  一致，§18 缩范围序第 5 位；批次 C 机制本体留 codex 判据提案后施工。
- **D-14 = 采 kilo 契约补条款**（/current：protected 优先，无则回退 max(updated_at)
  保底不 404）；**D-15 = 采**（DELETE 同步摘除 _ANCHOR_IDS，新增 unregister_anchor_id
  与 register 成对）。
- D-11/D-12/D-13/D-16：随 D-10=不可见自动闭合（form/sense/广播/branch_id 来源
  无对象）。

## D. codex S2 采认

S1 §3 自我修正（浮现状态纯函数重算无载体）采；R-E1~E5 断言面采（**R-E3 抓到
「fail-closed 是恰好非设计」**——4 条 RED 钉随 D3-c 并单施工）；**F-6 采注册侧
fail-closed 提案**（anchors POST 注册即扫，422 结构化原因同 impulse_gate 体例）——
随 anchors CRUD 落地单施工；notice 定性=C3 界面面非 S1 面采认。

## E. pi P3 采认+soak 触发

两红线（0.90ms 单帧/42.0s 派生量）落 thresholds 观察态起步采；**口径声明关键采认**
（当前快进帧非满 L1 负载，满载上界 ~2.9ms 不覆盖另裁）。
**soak 第 3 轮全量门禁红 → 触发裁 21-D 定标机复测**（本裁即触发）：派 pi 下一波
上定标机复核 soak 均值漂移 2.81x→是否真回归或本机降频污染，结果落 memory ⑤节。

## F. 批次 B 收官宣告+历史点分叉挂接

批次 B（双轨存档分叉重放）：F3✅ 零迁移✅ 0008✅ fork 事务✅ R2 断言✅
协议面四面✅ 编排件✅ RNG 承接✅——**收官**。
**历史点分叉**（回退旧存档）：仍 fail-closed，评估挂接批次 E（anchor 世界态物化
为 opencode 建议 (c)，预研轮再评）——不阻塞批次 A 开工。
