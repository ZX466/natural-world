"""prompt 装配规范包（sim/llm/prompts/）。

禁词单一数据源在本包 `banned_words` 模块：prompt 装配出口扫描（M1-B）、
reason 闸门扫描（M1-D）、记忆写入扫描（sim/llm/memory_scan.py）共用同一份
常量与扫描器，禁止他处复制词表（memory-scan.md §2 铁律）。
"""
