#!/usr/bin/env python3
"""Small Markdown helpers shared by report and language-review checks."""
from __future__ import annotations

import html
import re


def inline_tokens(text: str):
    """Yield (kind, visible text, URL) for the supported inline subset."""
    i, plain = 0, []
    while i < len(text):
        token = None
        if text[i] == '[':
            label_end = text.find(']', i + 1)
            if label_end >= 0 and text[label_end:label_end + 2] == '](':
                start, depth, j = label_end + 2, 1, label_end + 2
                while j < len(text) and depth:
                    if text[j] == '\\' and j + 1 < len(text):
                        j += 2
                        continue
                    if text[j] == '(':
                        depth += 1
                    if text[j] == ')':
                        depth -= 1
                    j += 1
                if depth == 0:
                    url = text[start:j - 1]
                    if re.match(r'^(https?://|mailto:)', url) and not re.search(r'\s', url):
                        token = ('link', text[i + 1:label_end], re.sub(r'\\([()])', r'\1', url), j)
        if token is None:
            for mark, kind in [('`', 'code'), ('**', 'bold'), ('*', 'italic')]:
                if text.startswith(mark, i):
                    end = text.find(mark, i + len(mark))
                    if end > i + len(mark):
                        token = (kind, text[i + len(mark):end], None, end + len(mark))
                        break
        if token:
            if plain:
                yield 'text', ''.join(plain), None
                plain = []
            yield token[:3]
            i = token[3]
        else:
            plain.append(text[i])
            i += 1
    if plain:
        yield 'text', ''.join(plain), None


def markdown_links(md: str) -> list[str]:
    urls, in_code = [], False
    for line in re.sub(r'<!--.*?-->', '', md, flags=re.S).splitlines():
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if not in_code:
            urls.extend(html.unescape(url) for kind, _, url in inline_tokens(line) if kind == 'link')
    return urls


def validate_heading_hierarchy(md: str) -> None:
    """Allow one document title, then require consecutive section levels."""
    first_block, title_used, previous, in_code = True, False, 0, False
    for number, line in enumerate(re.sub(r'<!--.*?-->', '', md, flags=re.S).splitlines(), 1):
        if not line.strip():
            continue
        if line.strip().startswith('```'):
            in_code = not in_code
            first_block = False
            continue
        if in_code:
            continue
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            level = len(match[1])
            if first_block and level == 1:
                title_used = True
            else:
                effective = level - 1 if title_used else level
                if effective < 1 or effective > previous + 1:
                    raise ValueError(
                        f'heading hierarchy at line {number}: use consecutive section levels after the document title'
                    )
                previous = effective
        first_block = False


def split_reference_sections(md: str) -> tuple[str, str]:
    """Exclude local and global bibliographies from body-citation detection."""
    body, refs = [], []
    reference_level, in_code = None, False
    for line in re.sub(r'<!--.*?-->', '', md, flags=re.S).splitlines():
        if line.strip().startswith('```'):
            in_code = not in_code
        match = None if in_code else re.match(r'^(#{1,6})[ \t]+(.+?)[ \t]*$', line)
        if match:
            level = len(match[1])
            if reference_level is not None and level <= reference_level:
                reference_level = None
            if re.fullmatch(r'(?:(?:[一二三四五六七八九十]+|\d+)[、.]\s*)?(?:参考文献|References)', match[2], re.I):
                reference_level = level
        (refs if reference_level is not None else body).append(line)
    return '\n'.join(body), '\n'.join(refs)
