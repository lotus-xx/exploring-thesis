#!/usr/bin/env python3
"""Read-only release integrity, migration provenance and document-link audit."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tarfile
import tempfile
from urllib.parse import unquote
from knowledge_base import KnowledgeBase


def load(root, name):
    spec = importlib.util.spec_from_file_location('_audit_' + name, root / 'scripts' / (name + '.py'))
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj


def audit(root, readme=None, readme_base=None):
    root = Path(root).resolve(); errors = []; checks = {}
    def need(ok, message):
        if not ok: errors.append(message)
    entrypoint = (root / 'SKILL.md').read_text(encoding='utf-8')
    match = re.search(r'^  version:\s*"([^"]+)"', entrypoint, re.M)
    version = match[1] if match else None
    vr = load(root, 'validate_run'); rt = load(root, 'research_runtime')
    need(version == vr.POLICY_VERSION == rt.POLICY_VERSION == '3.0', 'release policy/entrypoint version mismatch')
    with tempfile.TemporaryDirectory(prefix='topic-release-') as temp:
        papers = Path(temp) / 'papers'; papers.mkdir()
        run = vr.init(papers.parent, 'read', [papers], '数学', 'proof', 'disabled')
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
        need(manifest['policy_version'] == '3.0' and type(manifest['policy_version']) is str
             and manifest['schema_version'] == 6, 'new manifest version mismatch')
    kb = KnowledgeBase(root); checks['knowledge'] = kb.verify()
    catalog = kb.catalog(); mapping = catalog.get('legacy_ids', {})
    need(len(mapping) == 56, 'legacy map must retain 56 stable IDs')
    archive = kb.path('history/legacy-theories-2.11.3.tar.gz')
    need(archive.is_file(), 'missing recoverable legacy archive')
    if archive.is_file():
        with tarfile.open(archive, 'r:gz') as stream:
            for old_id, ident in mapping.items():
                obj = kb.entry(ident)
                name = 'theories/' + old_id + '.md'
                raw = stream.extractfile(name).read()
                need(obj.get('legacy_markdown', '').encode('utf-8') == raw, 'legacy bytes differ: ' + old_id)
                need(obj.get('legacy_sha256') == hashlib.sha256(raw).hexdigest(), 'legacy checksum differs: ' + old_id)
                legacy_date = re.search(rb'^verified_on:\s*(\S+)', raw, re.M)
                need(legacy_date and obj.get('verified_on') == legacy_date[1].decode(), 'historical verification date changed: ' + old_id)
    need(not (root / 'references/theories').exists(), 'retire old editable runtime theory directory after archiving')
    docs = [root / 'SKILL.md'] + sorted((root / 'references').glob('*.md'))
    if readme:
        readme = Path(readme).resolve(); docs.append(readme)
        manual = readme.read_text(encoding='utf-8')
        need('“选题小助手”3.0' in manual and '“选题发现与可行性论证”1.1.0' in manual,
             'unified README skill versions/boundary mismatch')
        for obsolete in ('侧重公共管理', '仅阅读、文献比较和一般解释不自动联网', '2.11.3；'):
            need(obsolete not in manual, 'obsolete README behavior: ' + obsolete)
    links = 0
    for path in docs:
        text = path.read_text(encoding='utf-8')
        if path.name == 'SKILL.md':
            need(not re.search(r'新运行 schema 5|policy 2\.11\.3|policy_version: 2\.11\.3', text), 'obsolete active entrypoint declaration')
        for raw in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', text):
            target = unquote(raw.strip('<>'))
            if re.match(r'^[a-zA-Z]+:', target) or target.startswith(('〔', '#')):
                continue
            filepart = target.split('#', 1)[0]
            if not filepart: continue
            parent = Path(readme_base).resolve() if readme and path == readme and readme_base else path.parent
            need((parent / filepart).is_file(), str(path) + ': broken local link ' + target)
            links += 1
    checks.update(versions={'entrypoint': version, 'policy': vr.POLICY_VERSION, 'runtime': rt.POLICY_VERSION,
                            'manifest_policy': manifest['policy_version'], 'manifest_schema': manifest['schema_version']},
                  legacy_cards=len(mapping), local_links=links, document_count=len(docs))
    return {'status': 'passed' if not errors else 'failed', 'checks': checks, 'errors': errors,
            'scope': 'deterministic release and document integrity; scholarly source truth requires actual reading'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readme', type=Path); parser.add_argument('--readme-base', type=Path)
    args = parser.parse_args()
    try:
        result = audit(Path(__file__).resolve().parent.parent, args.readme, args.readme_base)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'failed', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
