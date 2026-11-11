#!/usr/bin/env python3
"""Lossless local migration of the 2.11.3 cards; never a fresh source verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
from knowledge_base import KnowledgeBase, atomic_json, digest


def section(text, title):
    match = re.search(r'^## ' + re.escape(title) + r'\s*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    return match[1].strip() if match else '原卡未单独说明；不得据此补造。'


def convert(path):
    raw = path.read_bytes(); text = raw.decode('utf-8')
    fields = dict(re.findall(r'^([a-z_]+):\s*(.*?)\s*$', text.split('---', 2)[1], re.M))
    basis = section(text, '核对依据')
    sources = []
    locator = basis.split('读取范围：', 1)[-1].strip()
    depth = 'abstract' if '摘要' in locator and not any(t in locator for t in ('论述', '部分', '框架', '正文', '分析')) else 'partial'
    if '书介' in locator or '介绍' in locator:
        depth = 'metadata'
    for title, url in re.findall(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', basis):
        sources.append({'title': title, 'url': url, 'access_level': depth,
                        'read_locator': locator, 'support': '仅支持原卡基础命题；精确原始范围见 legacy_markdown。',
                        'support_level': 'metadata-only' if depth == 'metadata' else 'limited',
                        'verified_on': fields['verified_on'], 'published_at': None,
                        'accessed_at': None, 'migration_note': '沿用历史核验日期，迁移未重新访问。'})
    guidance = section(text, '研究设计建议')
    def bullet(label):
        found = re.search(r'^- ' + label + r'：(.*)$', guidance, re.M)
        return found[1] if found else '原卡未单列；仅按已有命题限缩使用。'
    return {'schema_version': 1, 'id': fields['theory_id'], 'version': 1,
            'name_zh': fields['name'], 'name_en': '英文正式名称未在旧卡单列（' + fields['theory_id'] + '）',
            'aliases': [fields['theory_id']], 'kind': fields['kind'], 'disciplines': ['公共管理'],
            'origin': fields['origin'], 'concepts_and_propositions': section(text, '基础命题'),
            'analysis_level': section(text, '概念与分析层级'),
            'conditions': bullet('适用与中国情境'), 'applicable': bullet('适用与中国情境'),
            'public_management_conditions': bullet('适用与中国情境'),
            'inapplicable': bullet('边界与竞争解释'), 'competing_explanations': bullet('边界与竞争解释'),
            'author_claims': section(text, '基础命题'), 'assistant_guidance': guidance,
            'sources': sources, 'maturity': '沿用历史卡；成熟程度未另行评定，不因迁移提升。',
            'verification_status': fields['status'], 'verified_on': fields['verified_on'],
            'change_basis': '无损迁移 2.11.3；不代表重新核验或学科适配已获证实。',
            'review': {'status': 'reviewed', 'reviewer': 'local-lossless-migration',
                       'source_check': '完整保留历史来源、日期与原始读取位置，未联网。',
                       'dedup_check': '旧稳定 ID 一对一迁移。', 'conflicts': '历史争议和边界原样保留。'},
            'private_material': False, 'legacy_path': 'references/theories/' + path.name,
            'legacy_sha256': hashlib.sha256(raw).hexdigest(), 'legacy_markdown': text}


def migrate(skill_root, retire=False):
    skill_root = Path(skill_root).resolve(); kb = KnowledgeBase(skill_root)
    old_dir = skill_root / 'references/theories'
    if not old_dir.exists():
        result = kb.verify()
        if len(kb.catalog().get('legacy_ids', {})) != 56:
            raise ValueError('legacy map must cover 56 cards')
        return dict(result, migration='already-migrated')
    paths = sorted(old_dir.glob('*.md'))
    if len(paths) != 56:
        raise ValueError('expected exactly 56 source cards; stop before migration')
    objects = [convert(path) for path in paths]
    if len({obj['id'] for obj in objects}) != 56:
        raise ValueError('duplicate legacy ID')
    kb.initialize()
    if '公共管理' not in kb.catalog()['disciplines']:
        kb.add_profile({'schema_version': 1, 'version': 1, 'name': '公共管理',
            'aliases': ['公共行政', '行政管理', 'public administration', 'public management', 'MPA'],
            'paradigms': ['经验解释', '制度比较', '规范论证', '历史研究'],
            'source_portals': ['references/journal-sources.md'],
            'hotspot_categories': ['governance', 'policy', 'academic-cn', 'academic-intl'],
            'scope_fields': ['region', 'population', 'setting', 'time_window', 'unit', 'basis'],
            'research_types': ['empirical', 'text', 'normative', 'historical'],
            'public_management': True, 'qualification': ['scope', 'single_problem', 'problem_basis',
                'ai_boundary', 'theory_fit', 'decision_relevance'],
            'notes': '治理决策、AI政务边界和中国制度条件仅在相关公共管理问题适用；缺理论允许纯论文。'})
    for obj in objects:
        if obj['id'] in kb.catalog()['entries']:
            if kb.entry(obj['id']).get('legacy_sha256') != obj['legacy_sha256']:
                raise ValueError('legacy content changed; requires manual merge: ' + obj['id'])
        else:
            kb.publish(obj)
    with kb.lock():
        old = kb.catalog(); new = json.loads(json.dumps(old))
        new['legacy_ids'] = {obj['id']: obj['id'] for obj in objects}
        kb._commit(old, new, 'complete 56-card legacy ID mapping')
    for path, obj in zip(paths, objects):
        restored = kb.entry(obj['id'])
        if restored['legacy_markdown'].encode('utf-8') != path.read_bytes():
            raise ValueError('lossless comparison failed')
    kb.rebuild_indexes(); result = kb.verify()
    if retire:
        archive = kb.path('history/legacy-theories-2.11.3.tar.gz')
        if not archive.exists():
            with tarfile.open(archive, 'x:gz') as stream:
                for path in paths:
                    stream.add(path, arcname='theories/' + path.name)
        with tarfile.open(archive, 'r:gz') as stream:
            for path in paths:
                if stream.extractfile('theories/' + path.name).read() != path.read_bytes():
                    raise ValueError('recovery archive verification failed')
        # Exact validated source targets only; the archive and legacy_markdown remain recoverable.
        for path in paths:
            path.unlink()
        old_dir.rmdir()
    return dict(result, lossless_cards=56, retired=retire, fresh_verification=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retire', action='store_true', help='archive and retire validated old runtime directory')
    args = parser.parse_args()
    print(json.dumps(migrate(Path(__file__).resolve().parent.parent, args.retire), ensure_ascii=False, indent=2))
