"""实现程度复检脚本（2026-10-20 建立）——逐项跑代码取证，不采信文档自述。

用法（仓库根目录）：
    uv run python tools/check_implementation_status.py

检查项（全部只读，不改仓库）：

1. WS 协议三面：**出站**帧是否「有 schema / 服务端发射 / 客户端消费」齐全。
   入站（C→S）消息按 ws.py 的 `_ALLOWED_CLIENT_TYPES` 排除，不计入。
   缺任一面则列出，并区分**豁免登记**（ws-protocol.md 明示预留）与**真缺口**。
2. 协议版本：README 徽章与 `sim/api/ws.py` 的 `_PROTOCOL_VERSION` 必须一致。
3. 幽灵包：只挑「除 __init__.py 外没有任何 .py」的包——那种包的 docstring
   若声称有子模块，就是纯幽灵（如历史上的 sim/combat）。
4. 过时占位注释：`M0 协议暂缺` 等字面量残留（提示性）。

退出码：0 = 未发现阻断性缺口；1 = 有（列在「待处理」区）。
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: 出站帧名（ws.py 实际发出的 type 字面量）与 schema 类名的映射来源
#: 直接从 openapi_ext.py 的 _TYPE_OF 表解析，避免硬编码。
_ = None


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _type_of_map() -> dict[str, str]:
    """解析 openapi_ext.py 的 `_TYPE_OF` 风格映射：类名 -> 帧名。"""
    src = _read("sim/api/openapi_ext.py")
    block = re.search(r"_TYPE_OF[^=]*=\s*\{(.*?)\n\}", src, re.DOTALL)
    if block is None:
        return {}
    return dict(re.findall(r'"(\w+Message)":\s*"([a-z_]+)"', block.group(1)))


def _inbound_names() -> set[str]:
    """服务端接受的 C→S 帧名（ws.py `_ALLOWED_CLIENT_TYPES`）。"""
    src = _read("sim/api/ws.py")
    block = re.search(r"_ALLOWED_CLIENT_TYPES\s*=\s*\{(.*?)\n\}", src, re.DOTALL)
    if block is None:
        return set()
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def _strip_comments(src: str) -> str:
    """剥掉 Python 行注释——否则注释里举例的 JSON（如 `{"type":"hello"}`）
    会被当成真实发射面，产生假缺口（2026-10-20 实测踩到）。"""
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def check_ws_frames() -> list[str]:
    problems: list[str] = []

    type_of = _type_of_map()
    inbound = _inbound_names()

    ws_py = _strip_comments(_read("sim/api/ws.py"))
    emitted = set(re.findall(r'"type":\s*"([a-z_]+)"', ws_py))

    # TypeScript 注释同样要剥：ws.ts 里就有 `// ... 不消费 'xxx'` 这类举例
    ws_ts = "\n".join(line.split("//", 1)[0] for line in _read("client/src/net/ws.ts").splitlines())
    consumed = set(re.findall(r"case '([a-z_]+)':", ws_ts))

    protocol_doc = _read("docs/api/ws-protocol.md")
    exempt = "`perception` 不经 WS 出站" in protocol_doc

    # 双向错配
    for frame in sorted(emitted - consumed):
        problems.append(f"[ws] 服务端发送 '{frame}'，客户端 dispatch 无 case（静默丢弃）")
    for frame in sorted(consumed - emitted):
        problems.append(f"[ws] 客户端消费 '{frame}'，服务端从不发送（幽灵分支）")

    # 逐个 schema 类型归类
    for cls, frame in sorted(type_of.items()):
        if frame in inbound:
            continue  # C→S：本就不该出现在出站/消费面
        if frame in emitted and frame in consumed:
            continue
        missing = []
        if frame not in emitted:
            missing.append("服务端零发射")
        if frame not in consumed:
            missing.append("客户端零消费")
        if frame == "perception" and exempt:
            problems.append(
                f"[ws] {frame}：{'/'.join(missing)}——**豁免**（ws-protocol.md 明示预留，"
                "只进 Agent 侧）"
            )
        else:
            problems.append(f"[ws] {frame}（{cls}）：{'/'.join(missing)}——**疑似真缺口**")
    return problems


def check_protocol_version() -> list[str]:
    problems: list[str] = []
    m = re.search(r'_PROTOCOL_VERSION\s*=\s*"([^"]+)"', _read("sim/api/ws.py"))
    if m is None:
        return ["[protocol] sim/api/ws.py 找不到 _PROTOCOL_VERSION"]
    real = m.group(1)
    readme = _read("README.md")
    badge = re.search(r"badge/protocol-([0-9.]+)-blue", readme)
    if badge is None:
        problems.append("[protocol] README 徽章缺 protocol 版本")
    elif badge.group(1) != real:
        problems.append(f"[protocol] README 徽章 {badge.group(1)} ≠ 代码 {real}（文档漂移）")
    return problems


def check_ghost_packages() -> list[str]:
    """只对「空壳包」报错：除 __init__.py 外无任何 .py 文件。"""
    problems: list[str] = []
    for init in sorted((REPO / "sim").glob("*/__init__.py")):
        pkg = init.parent
        others = [p for p in pkg.glob("*.py") if p.name != "__init__.py"]
        if others:
            continue  # 有实质代码，docstring 的模块清单视为历史划分，不阻断
        doc = init.read_text(encoding="utf-8")[:2000]
        claimed = re.findall(r"^- (\w+)\s{2,}\S", doc, flags=re.MULTILINE)
        if claimed:
            problems.append(
                f"[ghost] sim/{pkg.name}/ 是空壳包（仅 __init__.py），"
                f"docstring 却声称子模块 {claimed}"
            )
    return problems


def check_stale_placeholders() -> list[str]:
    # encoding 显式给 utf-8：Windows 默认 GBK 会在这类中文匹配上解码崩掉
    result = subprocess.run(
        [
            "git",
            "grep",
            "-nI",
            "-E",
            r"M0\s*协议暂缺",
            "--",
            "*.py",
            "*.ts",
            "*.tsx",
            ":!tools/check_implementation_status.py",  # 排除自指（本文件 docstring 提到该词）
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return [f"[stale] {line}" for line in (result.stdout or "").splitlines()[:20]]


def main() -> int:
    # Windows 控制台默认 GBK：强制 UTF-8，避免报告变乱码
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

    sections = [
        ("WS 协议三面（仅出站）", check_ws_frames()),
        ("协议版本", check_protocol_version()),
        ("幽灵包", check_ghost_packages()),
        ("过时占位注释", check_stale_placeholders()),
    ]
    print("=" * 72)
    print("实现程度复检（只读取证）")
    print("=" * 72)
    blocking = 0
    for title, problems in sections:
        print(f"\n## {title}")
        if not problems:
            print("  未发现问题")
            continue
        for p in problems:
            print(f"  - {p}")
            if "豁免" not in p:
                blocking += 1

    print("\n" + "=" * 72)
    if blocking == 0:
        print("结论：未发现新缺口")
        return 0
    print(f"结论：{blocking} 项待处理（豁免项不计）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
