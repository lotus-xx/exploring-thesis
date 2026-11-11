#!/usr/bin/env python3
"""Controlled local deployment; runtime knowledge is preserved, seeds merge by ID.

Use --check to preview. Actual writes follow host filesystem approval rules.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
from knowledge_base import KnowledgeBase, atomic_json, digest


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_release(root):
    text = (root / 'SKILL.md').read_text(encoding='utf-8')
    if 'version: "3.0"' not in text:
        raise ValueError('source must be release 3.0')
    for name in ('validate_run.py', 'research_runtime.py'):
        spec = importlib.util.spec_from_file_location('_deploy_' + Path(name).stem, root / 'scripts' / name)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        if module.POLICY_VERSION != '3.0':
            raise ValueError('policy version mismatch')
    return KnowledgeBase(root).verify()


def code_files(root):
    files = [root / 'SKILL.md']
    for directory in ('references', 'scripts', 'tests'):
        files += [p for p in (root / directory).rglob('*') if p.is_file()
                  and p.suffix in {'.md', '.py', '.m', '.json'} and '__pycache__' not in p.parts]
    return files


def deploy(source, target, readme_source=None, readme_target=None, backup_dir=None, check=False):
    if Path(target).is_symlink() or (readme_target and Path(readme_target).is_symlink()):
        raise ValueError('deployment destinations must not be symlinks')
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or source in target.parents or target in source.parents or target.name != 'topic-assistant':
        raise ValueError('source/target must be separate topic-assistant copies')
    if target.is_symlink() or not target.parent.is_dir():
        raise ValueError('target must have a real existing parent')
    verify_release(source)
    if bool(readme_source) != bool(readme_target):
        raise ValueError('both readme paths required')
    readme_source = Path(readme_source).resolve() if readme_source else None
    readme_target = Path(readme_target).resolve() if readme_target else None
    if readme_source:
        text = readme_source.read_text(encoding='utf-8')
        if '3.0' not in text or '1.1.0' not in text or readme_source == readme_target:
            raise ValueError('review staged unified README before deployment')
    preserved = (target / 'knowledge-base/catalog.json').exists()
    if preserved:
        KnowledgeBase(target).verify()
    # Check all rule destinations before any backup or mutation, including nested links.
    for path in code_files(source):
        if source not in path.resolve().parents:
            raise ValueError('source code path escapes skill root')
        destination = target / path.relative_to(source)
        if target not in destination.resolve().parents:
            raise ValueError('deployment code path escapes target skill root')
    plan = {'source': str(source), 'target': str(target), 'knowledge': 'merge-seeds-preserve-existing' if preserved else 'initial-controlled-copy',
            'code_files': len(code_files(source)), 'readme': str(readme_target) if readme_target else None}
    if check:
        return dict(plan, status='preview-only')
    if backup_dir is None:
        raise ValueError('explicit backup directory required')
    backups = Path(backup_dir).resolve()
    if backups in {source, target} or source in backups.parents or target in backups.parents:
        raise ValueError('backup directory must be outside both skill copies')
    backups.mkdir(parents=True, exist_ok=True)
    label = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')
    backup = backups / ('topic-assistant-before-' + label + '.tar.gz')
    with tarfile.open(backup, 'x:gz') as archive:
        if target.exists(): archive.add(target, arcname='topic-assistant', filter=lambda item: None if '__pycache__' in item.name else item)
        if readme_target and readme_target.is_file(): archive.add(readme_target, arcname='README.md')
    target.mkdir(parents=True, exist_ok=True)
    source_kb = KnowledgeBase(source)
    before = KnowledgeBase(target).catalog() if preserved else None
    if not preserved:
        if (target / 'knowledge-base').exists():
            raise ValueError('target has incomplete knowledge store; recover explicitly before deployment')
        shutil.copytree(source_kb.root, target / 'knowledge-base')
        atomic_json(target / 'knowledge-base/runtime.json', {'writer_root': str(target)})
    else:
        target_kb = KnowledgeBase(target)
        conflicts = []
        for name in source_kb.catalog()['disciplines']:
            if name not in target_kb.catalog()['disciplines']:
                profile = source_kb.profile(name)
                if profile['version'] != 1:
                    raise ValueError('new seed profile needs explicit revision migration: ' + name)
                target_kb.add_profile(profile)
        for ident in source_kb.catalog()['entries']:
            card = source_kb.entry(ident)
            if ident in target_kb.catalog()['entries']:
                if digest(card) != digest(target_kb.entry(ident)):
                    conflicts.append(ident)  # Preserve accumulated revisions; no silent downgrade.
            else:
                if card['version'] != 1:
                    raise ValueError('new seed entry needs explicit revision migration: ' + ident)
                target_kb.publish(card)
        for ident, pointer in before['entries'].items():
            if target_kb.catalog()['entries'].get(ident) != pointer:
                raise ValueError('deployment changed an existing knowledge pointer')
        plan['preserved_seed_differences'] = conflicts
    for path in code_files(source):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if hash_file(destination) != hash_file(path):
            raise ValueError('deployed code checksum mismatch')
    old = target / 'references/theories'
    if old.is_dir():
        # The complete pre-deployment archive is already durable; keep loose recovery too.
        shutil.move(str(old), str(backups / ('retired-theories-' + label)))
    verify_release(target)
    if readme_source:
        readme_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(readme_source, readme_target)
        if hash_file(readme_source) != hash_file(readme_target):
            raise ValueError('README checksum mismatch')
    atomic_json(source_kb.path('runtime.json'), {'writer_root': str(target)})
    plan.update(status='deployed', backup=str(backup), writable_authority=str(target))
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--readme-source', type=Path)
    parser.add_argument('--readme-target', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = deploy(args.source, args.target, args.readme_source, args.readme_target, args.backup_dir, args.check)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc), 'status': 'deployment-incomplete; inspect backup and actual files'}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
