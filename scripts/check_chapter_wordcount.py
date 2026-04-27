#!/usr/bin/env python3
"""章节字数检查脚本 - 每章字数必须控制在 2000-3000 字"""

import re
import sys
from pathlib import Path

MIN_WORDS, MAX_WORDS = 2000, 3000


def count_chinese_words(text: str) -> int:
    """统计正文字数（不含换行、空格和尾部空白）"""
    return len(text.replace('\n', '').replace(' ', '').strip())


def extract_content(path: Path) -> str:
    """提取正文：跳过元数据行和章末提示"""
    lines = path.read_text(encoding='utf-8').split('\n')

    # 找到【涉及地点】那一行，正文从下一行开始
    line_index = 0
    found_meta = False
    for i, line in enumerate(lines):
        if line.strip().startswith('【涉及地点】'):
            line_index = i + 1
            found_meta = True
            break

    # 兜底：如果没找到元数据，跳过前5行（标题+空行+4个元数据行）
    if not found_meta:
        line_index = 0
        while line_index < len(lines) and not lines[line_index].strip():
            line_index += 1
        if line_index < len(lines) and re.match(r'第\d+章', lines[line_index].strip()):
            line_index += 1
        while line_index < len(lines) and lines[line_index].strip():
            line_index += 1
        while line_index < len(lines) and not lines[line_index].strip():
            line_index += 1

    # 跳过空行
    while line_index < len(lines) and not lines[line_index].strip():
        line_index += 1

    # 提取正文直到章末钩子
    content_lines = []
    for line in lines[line_index:]:
        if line.strip().startswith(('【章末钩子】', '【下章预告】')):
            break
        content_lines.append(line)

    return '\n'.join(content_lines)


def check_chapter(path: Path) -> dict:
    """检查单章字数"""
    if not path.exists():
        return {'file': str(path), 'exists': False, 'word_count': 0, 'status': 'error', 'message': f'文件不存在'}

    word_count = count_chinese_words(extract_content(path))

    if word_count < MIN_WORDS:
        status, icon, msg = 'fail', '❌', f'不足，需要至少 {MIN_WORDS} 字'
    elif word_count > MAX_WORDS:
        status, icon, msg = 'fail', '❌', f'超过 {MAX_WORDS} 字，需精简'
    else:
        status, icon, msg = 'pass', '✅', '达标'

    return {'file': str(path), 'exists': True, 'word_count': word_count, 'status': status, 'icon': icon, 'message': msg}


def main():
    if len(sys.argv) < 2:
        print('用法:')
        print('  检查单章: python check_chapter_wordcount.py <文件路径>')
        print('  检查全部: python check_chapter_wordcount.py --all')
        return

    results = []
    if sys.argv[1] == '--all':
        results = [check_chapter(p) for p in sorted(Path('output').glob('第*.md'))]
    else:
        results = [check_chapter(Path(sys.argv[1]))]

    if not results:
        print('没有找到章节文件')
        return

    total, passed, failed = 0, 0, 0
    print('\n' + '=' * 50)
    print('章节字数检查报告')
    print('=' * 50)
    for r in results:
        total += r['word_count']
        if r['status'] == 'pass':
            passed += 1
        else:
            failed += 1
        if not r['exists']:
            print(f"\n❌ {Path(r['file']).name}")
            print(f"   {r['message']}")
            continue
        print(f"\n{r['icon']} {Path(r['file']).name}")
        print(f"   字数: {r['word_count']} ({r['message']})")

    print('\n' + '-' * 50)
    print(f'总计: {len(results)} 章 | {passed} 达标 | {failed} 需调整 | 总字数: {total:,}')
    print('-' * 50)


if __name__ == '__main__':
    main()
