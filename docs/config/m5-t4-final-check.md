# T4 真跑终态 checklist（key 到位即跑）

> 合并自 `m5-c9-t4-probe-runbook.md` ＋ `m5-c10-closure-inventory.md` §4。基线 main `8491659`｜**收官轮判 A2 直接引用本页**。key 纪律：运行时环境变量**永不落盘**｜锁版本 `Deepseek-v4-flash` @ `chatapi.weixin.qq.com/openai/v1`｜**直连不走 7897 代理**。

## 触发三条件（缺一不动）

| # | 条件 | 谁给 | 实测 |
|---|---|---|---|
| 1 | 用户完成 key 轮换并告知 | 用户 | ❌ `T4_MODEL_API_KEY` 未设 |
| 2 | Claude 给**执行许可** | Claude | ❌ 未给 |
| 3 | 本树与 main 同头 | cline | ✅ `8491659` |

## 七步

| 步 | 命令／动作 | 预期 | 耗时 |
|---|---|---|---|
| ① | `$env:T4_MODEL_API_KEY='<key>'` | 无输出（**不写任何文件**） | 30s |
| ② | `$env:T4_RUN='1'` | 无输出 | 5s |
| ③ | **形态自检** `--collect-only -q` | 末行 **`53/248 collected (195 deselected)`** ≠ 0 | 20s |
| ④ | **真跑** `uv run pytest sim/tests/test_t4_probes.py -m t4 -q` | 52 真探针＋`test_report_written` 1 | 3–8min |
| ⑤ | **判读**（下两道，顺序不可颠倒） | — | 2min |
| ⑥ | **留痕三处**（下） | — | 5min |
| ⑦ | **销 key** `Remove-Item Env:T4_MODEL_API_KEY` | 该变量为空 | 5s |

> ③④ 命令均带 `sim/tests/test_t4_probes.py -m t4`；预算闸 `T4_CALL_BUDGET` 缺省 **60**（顶预算题面记 `inconclusive` 不硬跑，闸只能收紧），53 ≤ 60 ⇒ 一轮不撞顶限。

## 判据两道（⑤）

**形态道**（任一不成立即**不是绿**，即使退出码 0）：① 退出码 ≠ 5（否则收集 0 用例）｜② **非全 skip**——三把锁缺任一 ⇒ `live_client` 模块级 skip 且**退出码仍 0**，是**假绿**｜③ `t4-report.json` 存在。
**内容道**：`hard_red[]` 空 = 真绿；`inconclusive[]` 非空 ⇒ **人工复核，不得当绿**。唯一真红＝出戏词面命中，**不放宽断言**。最可能失败＝**4xx 鉴权**（key 待轮换），按 runbook §5.1 诊断，**不改探针代码**。

## 留痕三处（⑥）

| 处 | 写什么 | 纪律 |
|---|---|---|
| 回执 | 三句内抄主树留言板 | — |
| `docs/README.md` 台账 M4-C2 行 | 行**尾追加**裁 31-T4 现状标注 | **不改历史行事实**（消解旧行 `claude-sonnet-5`／secret 误导） |
| `.orca/memory.md` ②节 | 计数＋判读＋下一步 | — |

产物 `t4-results/t4.xml`＋`t4-report.json`：**已 gitignore，响应正文永不入库**；**只诊断不代改**（探针归 codex）。
