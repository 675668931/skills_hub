#!/usr/bin/env python3
"""章节质量闸门：格式、正文出戏、长段/空行、重复段落、批量公式化检查。"""

from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from collections import Counter
from pathlib import Path

REQUIRED_PREFIXES = ["第", "【本章概要】", "【情绪曲线】", "【涉及角色】", "【涉及地点】"]
BODY_FORBIDDEN_PATTERNS = [
    (re.compile(r"(?m)^\s*正文：\s*$"), "正文残留格式标签：正文："),
    (re.compile(r"本章|下一章|后文|剧情|读者|作者|伏笔"), "正文含作者视角/写作备注/元叙事词"),
    (re.compile(r"第\s*\d+\s*章|第\s*[一二三四五六七八九十百千万零〇两]+\s*章"), "正文直接提章节号"),
]
GLOBAL_FORBIDDEN_PATTERNS = [
    (re.compile(r"^\s*---\s*$", re.M), "禁止 markdown 分隔线 ---"),
    (re.compile(r"＊＊"), "禁止全角星号 ＊＊"),
    (re.compile(r"西楚之魂"), "禁止西楚之魂式机制"),
    (re.compile(r"自愈|自我修复|自动恢复|自行恢复|自我恢复"), "禁止自愈/自动恢复机制"),
]
MAX_PARAGRAPH_CHARS = 180
MAX_LINE_CHARS = 80
MAX_BLANK_RUN = 2
TAIL_WINDOW = 8
SIMILARITY_THRESHOLD = 0.55
MIN_SIMILAR_BODY_CHARS = 900
SHORT_SOUND_PATTERN = re.compile(r"^[咔砰轰叮嗤滋啪咚当噗嗖铛疼][。！]?$")

ABSTRACT_TAIL_PATTERNS = [
    re.compile(r"意识到|明白|觉得|确认|重新评估|震惊|敬畏|沉默|终于理解|足以|真正可怕"),
    re.compile(r"对.*来说|这一幕|这个变化|这种感觉|那种|意义|结果|本身"),
]
ACTION_TAIL_PATTERNS = [
    re.compile(r"走|跑|跃|抬|按|抓|扔|砸|斩|挡|救|搬|扶|喊|问|说|递|落|飞|燃|碎|响|冲|追|转身|低头|抬头"),
]
TAIL_CLICHE_PATTERNS = [
    re.compile(r"系统提示.*浮现"),
    re.compile(r"远处|遥远|黑暗|暗处"),
    re.compile(r"捏碎|摔碎|杯子|茶杯"),
    re.compile(r"问.*饭|早饭|热饭|请饭"),
    re.compile(r"众人|所有人.*(震惊|沉默|安静)"),
]


def strip_space(s: str) -> str:
    return re.sub(r"\s+", "", s)


def chapter_no(path: Path) -> int:
    m = re.search(r"第(\d+)章", path.name)
    return int(m.group(1)) if m else 10**9


def extract_body(lines: list[str]) -> list[tuple[int, str]]:
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("【涉及地点】"):
            start = i + 1
            break
    if start is None:
        return []
    while start < len(lines) and not lines[start].strip():
        start += 1
    body = []
    for idx in range(start, len(lines)):
        line = lines[idx]
        if line.strip().startswith(("【章末钩子】", "【下章预告】")):
            break
        body.append((idx + 1, line))
    return body


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"文件不存在: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or not lines[0].startswith("第") or "章" not in lines[0]:
        errors.append("首行必须是章节标题：第XX章 章节名")
    for prefix in REQUIRED_PREFIXES[1:]:
        if not any(line.startswith(prefix) for line in lines[:12]):
            errors.append(f"缺少元数据行：{prefix}")
    if not any(line.startswith("【章末钩子】") for line in lines[-8:]):
        errors.append("末尾缺少【章末钩子】")
    if not any(line.startswith("【下章预告】") for line in lines[-8:]):
        errors.append("末尾缺少【下章预告】")

    for pattern, msg in GLOBAL_FORBIDDEN_PATTERNS:
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            errors.append(f"第{line_no}行：{msg}")

    body = extract_body(lines)
    if not body:
        errors.append("无法提取正文：缺少【涉及地点】或正文为空")
        return errors

    body_text = "\n".join(line for _, line in body)
    for pattern, msg in BODY_FORBIDDEN_PATTERNS:
        for m in pattern.finditer(body_text):
            line_no = body_text[: m.start()].count("\n") + (body[0][0] if body else 1)
            errors.append(f"第{line_no}行：{msg}")

    paragraphs = [(ln, line.strip()) for ln, line in body if line.strip()]
    for ln, para in paragraphs:
        compact = strip_space(para)
        if len(compact) > MAX_PARAGRAPH_CHARS:
            errors.append(f"第{ln}行：段落过长（>{MAX_PARAGRAPH_CHARS}字），需拆分")
        if len(compact) > MAX_LINE_CHARS:
            errors.append(f"第{ln}行：单行过长（>{MAX_LINE_CHARS}字），需拆分")

    blank_start = None
    blank_count = 0
    for ln, raw_line in body:
        if not raw_line.strip():
            if blank_count == 0:
                blank_start = ln
            blank_count += 1
        else:
            if blank_count > MAX_BLANK_RUN:
                errors.append(f"第{blank_start}行：连续空行过多（{blank_count}行），最多保留{MAX_BLANK_RUN}行")
            blank_count = 0
            blank_start = None
    if blank_count > MAX_BLANK_RUN:
        errors.append(f"第{blank_start}行：连续空行过多（{blank_count}行），最多保留{MAX_BLANK_RUN}行")

    normalized = [strip_space(p) for _, p in paragraphs if len(strip_space(p)) >= 20]
    counts = Counter(normalized)
    for para, count in counts.items():
        if count > 1:
            first_ln = next(ln for ln, p in paragraphs if strip_space(p) == para)
            errors.append(f"第{first_ln}行：疑似重复段落出现 {count} 次")

    short_sounds = [(ln, para) for ln, para in paragraphs if SHORT_SOUND_PATTERN.fullmatch(para)]
    for i in range(len(short_sounds) - 2):
        a, b, c = short_sounds[i : i + 3]
        if a[1] == b[1] == c[1] and c[0] - a[0] <= 6:
            errors.append(f"第{a[0]}行起：连续短拟声词堆叠“{a[1]}”，需改为具体动作/结果描写")
            break

    tail = paragraphs[-TAIL_WINDOW:]
    if len(tail) >= TAIL_WINDOW:
        abstract_count = sum(any(p.search(text) for p in ABSTRACT_TAIL_PATTERNS) for _, text in tail)
        action_count = sum(any(p.search(text) for p in ACTION_TAIL_PATTERNS) for _, text in tail)
        avg_len = sum(len(strip_space(text)) for _, text in tail) / len(tail)
        if abstract_count >= 5 and action_count <= 3 and avg_len > 45:
            errors.append(f"第{tail[0][0]}行起：章尾疑似公式化总结/感慨堆叠，需改为具体场景推进")

    return errors


def body_fingerprint(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    body = [line.strip() for _, line in extract_body(lines) if line.strip()]
    # 去掉章节元信息和空白，保留正文顺序，用于抓“复制上一章只换角色名/末尾补几段”。
    text = "".join(strip_space(line) for line in body)
    # 轻度归一化常见替换，避免“富冈义勇→隐部队队长”这种换皮逃过检查。
    text = re.sub(r"[，。！？、；：‘’“”《》（）()\[\]【】]", "", text)
    text = re.sub(r"富冈义勇|隐部队队长|炭治郎|祢豆子|林彻", "角色", text)
    return text


def body_similarity(prev: Path, cur: Path) -> float:
    prev_text = body_fingerprint(prev)
    cur_text = body_fingerprint(cur)
    if min(len(prev_text), len(cur_text)) < MIN_SIMILAR_BODY_CHARS:
        return 0.0
    return SequenceMatcher(None, prev_text, cur_text).ratio()


def tail_signature(path: Path) -> tuple[int, tuple[str, ...]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    paragraphs = [(ln, line.strip()) for ln, line in extract_body(lines) if line.strip()]
    tail_text = "\n".join(text for _, text in paragraphs[-TAIL_WINDOW:])
    sig = []
    for i, pat in enumerate(TAIL_CLICHE_PATTERNS):
        if pat.search(tail_text):
            sig.append(str(i))
    return chapter_no(path), tuple(sig)


def check_batch(paths: list[Path]) -> list[tuple[Path, str]]:
    batch_errors: list[tuple[Path, str]] = []
    ordered = sorted(paths, key=chapter_no)
    for prev, cur in zip(ordered, ordered[1:]):
        prev_no, prev_sig = tail_signature(prev)
        cur_no, cur_sig = tail_signature(cur)
        if cur_no == prev_no + 1 and len(prev_sig) >= 2 and prev_sig == cur_sig:
            batch_errors.append((cur, f"与上一章章尾模式重复 {cur_sig}，需重写尾部骨架"))
        if cur_no == prev_no + 1:
            similarity = body_similarity(prev, cur)
            if similarity >= SIMILARITY_THRESHOLD:
                batch_errors.append((cur, f"与上一章正文相似度过高 {similarity:.2%}，疑似复制换皮；必须按本章事件目标整章重写"))
    return batch_errors


def main() -> int:
    if len(sys.argv) < 2:
        print("用法:")
        print("  检查单章: python check_chapter_quality.py <文件路径> [更多文件]")
        print("  检查全部: python check_chapter_quality.py --all")
        return 2

    if sys.argv[1] == "--all":
        paths = sorted(Path("output").glob("第*.md"), key=chapter_no)
    else:
        paths = [Path(arg) for arg in sys.argv[1:]]

    if not paths:
        print("没有找到章节文件")
        return 1

    failed = 0
    results: dict[Path, list[str]] = {}
    for path in paths:
        results[path] = check_file(path)
    for path, msg in check_batch(paths):
        results.setdefault(path, []).append(msg)

    for path in paths:
        errors = results[path]
        if errors:
            failed += 1
            print(f"\n❌ {path}")
            for e in errors:
                print(f"   - {e}")
        else:
            print(f"\n✅ {path}")
            print("   质量闸门通过")

    print(f"\n总计: {len(paths)} 章 | 通过: {len(paths) - failed} | 失败: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
