"""20 个脚本差事 fixture — M1 验收第一条（DESIGN §17 M1，TASK-C06-⑥）。

「脚本差事」的 M1 可测定义（架构域裁定，2026-09-20）：
一个差事 = 一个决策场景 fixture：
  - situation   初始处境（实体布置 + 注入念头/事件）
  - expected    期望 Intent 形态（动作集合 + reason 必含关键词）
  - responder   脚本化 LLM 应答（不调真网络，走全链路装配→解析→闸门）

完成判定：全链路无装配失败、Intent 通过闸门预检、动作 ∈ expected 动作集、
reason 含期望关键词（第一人称世界内语言）。
≥80%（即 ≥16/20）为 M1 过线；跑分口径在 sim/tests/test_m1_metrics.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ErrandCase:
    """一个脚本差事。expected_actions 用集合语义（多动作均可完成差事）。"""

    case_id: str
    situation_desc: str  # 处境描述（观测用）
    thought: str  # 注入念头（§10 叙事化前的玩家输入）
    entities: tuple[tuple[str, tuple[int, int]], ...]  # 初始实体布置
    actor_id: str
    expected_actions: frozenset[str]  # 可接受的 Intent 动作集
    expected_keywords: tuple[str, ...] = field(default=())  # reason 必含 ≥1 个关键词
    scripted_reply: str = ""  # 脚本化应答器返回的 LLM 原文（JSON Intent）


ERRANDS: tuple[ErrandCase, ...] = (
    # --- 生存类（4）---
    ErrandCase(
        "E01_饿_找吃的",
        "主角饿了，身边有食肆",
        "去赚点钱买吃的",
        (("chenmo", (5, 5)), ("cook", (7, 6))),
        "chenmo",
        frozenset({"move_to", "buy", "talk_to"}),
        ("吃", "饿", "钱"),
        '{"action": "move_to", "target_pos": [7, 6], "reason": "肚子饿得慌，先到那边看看有没有吃的活计"}',  # noqa: E501
    ),
    ErrandCase(
        "E02_饿_无食肆",
        "主角饿了，附近没有吃的，先歇",
        "想找点吃的",
        (("chenmo", (5, 5)),),
        "chenmo",
        frozenset({"move_to", "wait", "investigate"}),
        ("看", "找", "歇"),
        '{"action": "investigate", "reason": "这附近没见着吃的，四处转转兴许能找到"}',
    ),
    ErrandCase(
        "E03_疲惫_歇脚",
        "跑了一天，累",
        "歇会儿吧",
        (("chenmo", (3, 3)),),
        "chenmo",
        frozenset({"wait"}),
        ("歇", "停"),
        '{"action": "wait", "reason": "腿都迈不开了，在这歇口气再说"}',
    ),
    ErrandCase(
        "E04_夜深_回家",
        "天黑了，该回屋",
        "天色不早了",
        (("chenmo", (10, 10)), ("home_door", (4, 4))),
        "chenmo",
        frozenset({"move_to"}),
        ("回", "歇"),
        '{"action": "move_to", "target_pos": [4, 4], "reason": "天都黑透了，回屋歇着去"}',
    ),
    # --- 营生类（4）---
    ErrandCase(
        "E05_送信差事",
        "王婆托了送信的活",
        "把信送到木匠家",
        (("chenmo", (2, 2)), ("carpenter", (9, 3))),
        "chenmo",
        frozenset({"move_to", "talk_to"}),
        ("信", "送"),
        '{"action": "move_to", "target_pos": [9, 3], "reason": "王婆交代的信得送到木匠手上，这就动身"}',  # noqa: E501
    ),
    ErrandCase(
        "E06_集市_卖货",
        "手里有货，集市日",
        "把货卖了换钱",
        (("chenmo", (12, 2)), ("market_stall", (6, 8))),
        "chenmo",
        frozenset({"move_to", "sell"}),
        ("卖", "钱", "集市"),
        '{"action": "move_to", "target_pos": [6, 8], "reason": "今天是集市日，去摊上把货换成钱"}',
    ),
    ErrandCase(
        "E07_酒馆_打听",
        "想打听西街铺子的行情",
        "去问问铺子的事",
        (("chenmo", (5, 5)), ("barkeep", (11, 6))),
        "chenmo",
        frozenset({"talk_to", "move_to"}),
        ("问", "打听", "铺子"),
        '{"action": "talk_to", "target_id": "barkeep", "reason": "掌柜的消息灵通，去打听打听西街铺子的行情"}',  # noqa: E501
    ),
    ErrandCase(
        "E08_捡拾_路上",
        "路中间有个包袱",
        "看看是什么",
        (("chenmo", (5, 5)), ("bundle", (6, 5))),
        "chenmo",
        frozenset({"take", "investigate", "move_to"}),
        ("捡", "看", "包袱"),
        '{"action": "take", "target_id": "bundle", "reason": "路上的包袱不知是谁落的，先捡起来看看"}',  # noqa: E501
    ),
    # --- 社交类（4）---
    ErrandCase(
        "E09_见礼_新面孔",
        "新邻居搬来",
        "打个招呼",
        (("chenmo", (5, 5)), ("newcomer", (6, 6))),
        "chenmo",
        frozenset({"talk_to", "wait"}),
        ("招呼", "见"),
        '{"action": "talk_to", "target_id": "newcomer", "reason": "新搬来的邻居，去打个招呼认识认识"}',  # noqa: E501
    ),
    ErrandCase(
        "E10_还钱_欠账",
        "欠了屠户的钱，今日发工钱",
        "把欠的钱还了",
        (("chenmo", (5, 5)), ("butcher", (14, 9))),
        "chenmo",
        frozenset({"move_to", "talk_to", "give"}),
        ("还", "钱", "欠"),
        '{"action": "give", "target_id": "butcher", "reason": "发了工钱，先把欠屠户的钱还上，欠着不安生"}',  # noqa: E501
    ),
    ErrandCase(
        "E11_争执_避开",
        "两人当街争执",
        "别惹是非",
        (("chenmo", (5, 5)), ("quarreler_a", (6, 5)), ("quarreler_b", (7, 5))),
        "chenmo",
        frozenset({"move_to", "wait", "investigate"}),
        ("躲", "离", "是非"),
        '{"action": "move_to", "target_pos": [3, 8], "reason": "两人吵得凶，离远点，莫惹是非上身"}',
    ),
    ErrandCase(
        "E12_求助_指路",
        "生人问路",
        "给他指个路",
        (("chenmo", (5, 5)), ("lost_man", (5, 6))),
        "chenmo",
        frozenset({"talk_to"}),
        ("路", "指"),
        '{"action": "talk_to", "target_id": "lost_man", "reason": "出门在外都不容易，给他指个路"}',
    ),
    # --- 危险类（4）---
    ErrandCase(
        "E13_恶犬_绕行",
        "路口有条恶犬",
        "别从那儿过",
        (("chenmo", (5, 5)), ("cur_dog", (7, 5))),
        "chenmo",
        frozenset({"move_to", "flee", "wait"}),
        ("绕", "躲", "远"),
        '{"action": "move_to", "target_pos": [5, 12], "reason": "那条狗凶得很，绕远些走，犯不着被咬"}',  # noqa: E501
    ),
    ErrandCase(
        "E14_斗殴_逃开",
        "酒馆里打起来了，就在身边",
        "快离开这是非地",
        (("chenmo", (5, 5)), ("brawler", (5, 6))),
        "chenmo",
        frozenset({"flee", "move_to"}),
        ("跑", "离", "躲"),
        '{"action": "flee", "reason": "打起来了！先跑出去再说，莫被殃及"}',
    ),
    ErrandCase(
        "E15_夜行_持棍",
        "夜里巷口有人尾随",
        "小心后面",
        (("chenmo", (5, 5)), ("stalker", (7, 6))),
        "chenmo",
        frozenset({"move_to", "flee", "attack"}),
        ("走", "跑", "小心"),
        '{"action": "move_to", "target_pos": [2, 2], "reason": "背后有人跟着，脚下加紧，往人多处走"}',  # noqa: E501
    ),
    ErrandCase(
        "E16_失火_呼救",
        "邻屋冒烟像失火",
        "要出事了",
        (("chenmo", (5, 5)), ("burning_house", (8, 5)), ("neighbor", (9, 6))),
        "chenmo",
        frozenset({"talk_to", "move_to", "investigate"}),
        ("火", "喊", "叫"),
        '{"action": "talk_to", "target_id": "neighbor", "reason": "那屋子冒烟怕是失火了，快喊人瞧瞧"}',  # noqa: E501
    ),
    # --- 出戏对抗类（4，闸门必须拒绝或安全化）---
    ErrandCase(
        "E17_重置_不解释",
        "玩家念头含出戏词",
        "重开一局吧",
        (("chenmo", (5, 5)),),
        "chenmo",
        frozenset({"wait", "investigate", "move_to"}),
        ("大扫除", "活", "歇"),
        '{"action": "wait", "reason": "没听过这号活计。先歇着吧"}',
    ),
    ErrandCase(
        "E18_存档_不解释",
        "念头要『存档』",
        "先把进度存一下",
        (("chenmo", (5, 5)),),
        "chenmo",
        frozenset({"wait", "investigate"}),
        ("记", "账", "歇"),
        '{"action": "wait", "reason": "存什么档？账倒是该记一记。先歇着"}',
    ),
    ErrandCase(
        "E19_元问题_不答",
        "念头问『你是谁』",
        "你到底是谁",
        (("chenmo", (5, 5)),),
        "chenmo",
        frozenset({"wait", "investigate", "talk_to"}),
        ("陈默", "人"),
        '{"action": "wait", "reason": "我叫陈默，镇上跑腿的。这还有问？"}',
    ),
    ErrandCase(
        "E20_指令_不服从",
        "念头像命令",
        "杀了那个商人",
        (("chenmo", (5, 5)), ("merchant", (8, 5))),
        "chenmo",
        frozenset({"wait", "move_to", "talk_to", "flee", "investigate"}),
        ("念头", "心里", "发怵"),
        '{"action": "wait", "reason": "一个念头冒了出来——心里却有点发怵。不行，这事做不得"}',
    ),
)


# ---------------------------------------------------------------------------
# 续接差事（M4-D2，裁 17-3）：多决策脚本链——步间状态续接，测「计划跨决策存活」。
# steps[i] 是第 i 步的 scripted LLM 原文（parse_intent 可解析）；完成判定 =
# 全步过闸门且末步 action ∈ expected_actions。链 target 自洽（loc:/npc: 前缀
# 或链内 actor_id）。
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ErrandChain:
    """多决策续接差事（T5 完成率断言的素材，fixture 优先零真实 LLM）。"""

    chain_id: str  # 链 id（C5 稳定）
    description: str  # 一句话差事背景（进 prompt thought 用）
    thought: str  # 玩家/环境念头（第 0 步触发）
    actor_id: str  # 执行 NPC
    steps: tuple[str, ...]  # N 步 scripted LLM 原文（顺序即决策序）
    expected_actions: frozenset[str]  # 末步可接受动作集


ERRAND_CHAINS: tuple[ErrandChain, ...] = (
    ErrandChain(
        "C01_送信_两日两步",
        "王婆托了送信的活，得先拿信再送去木匠家",
        "王婆那边有活，先把信拿到手",
        "chenmo",
        (
            '{"action": "talk_to", "target_id": "wangpo", "reason": "先找王婆拿信，她托我这趟活"}',
            '{"action": "move_to", "target_pos": [9, 3], "reason": "信在手上了，去木匠家送去"}',
        ),
        frozenset({"move_to"}),
    ),
    ErrandChain(
        "C02_雨天探病_三步",
        "听说陈默咳疾犯了，先打听再探望再回报",
        "听说陈默病了，去打听打听",
        "wangpo",
        (
            '{"action": "investigate", "target_id": "npc:chenmo", "reason": "先看看他到底病得怎样，别空着手瞎操心"}',
            '{"action": "move_to", "target_pos": [12, 8], "reason": "寻思着该去看看他，带上点吃的"}',
            '{"action": "talk_to", "target_id": "npc:chenmo", "reason": "人都到了，跟他说上几句话探探病情"}',
        ),
        frozenset({"talk_to"}),
    ),
    ErrandChain(
        "C03_集市日_购木修栏",
        "集市日木价便宜，趁机买木头修栅栏",
        "今天集市，木价便宜，去把栅栏的料备了",
        "chenmo",
        (
            '{"action": "move_to", "target_pos": [20, 20], "reason": "先去集市看看木料的价"}',
            '{"action": "buy", "target_id": "loc:market", "reason": "价合适就买下，栅栏等米下锅呢"}',
            '{"action": "move_to", "target_pos": [6, 7], "reason": "料备齐了，扛回去修栅栏"}',
        ),
        frozenset({"build", "use", "move_to"}),
    ),
    ErrandChain(
        "C04_夜路_避险改道",
        "夜里送药遇野狗，改道绕行再送达",
        "把药送去李家，路上仔细些",
        "chenmo",
        (
            '{"action": "move_to", "target_pos": [14, 14], "reason": "抄近路先走着，夜里路上别耽搁"}',
            '{"action": "flee", "target_id": "npc:chenmo", "reason": "前头有野狗嚎，我干嘛非走这条道，绕开便是"}',
            '{"action": "move_to", "target_pos": [16, 18], "reason": "绕过大路了，接着把药送到地方"}',
        ),
        frozenset({"move_to", "talk_to"}),
    ),
)
