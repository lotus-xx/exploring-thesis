#!/usr/bin/env python3
"""Local, versioned knowledge store. No network, paper discovery or scholarly approval.

The catalog is the only commit pointer. Immutable objects are prepared before
one atomic catalog replacement; derived indexes may always be rebuilt.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

SCHEMA_VERSION = 1
SKILL_ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r'[a-z][a-z0-9-]{1,63}\Z')
KINDS = {'theory', 'framework', 'model', 'mechanism', 'concept', 'approach', 'perspective', 'family'}


def now():
    return datetime.now().astimezone().isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '-')
    tmp = Path(raw)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def safe_name(name):
    if not isinstance(name, str) or not name.strip() or name in {'.', '..'} or any(
            x in name for x in ('/', '\\', '\x00')):
        raise ValueError('invalid discipline name')
    return name


class KnowledgeBase:
    def __init__(self, skill_root=None):
        self.skill_root = Path(skill_root or SKILL_ROOT).resolve()
        raw = self.skill_root / 'knowledge-base'
        self.root = raw.resolve()
        if self.root != raw:
            raise ValueError('knowledge-base must be inside the actual skill root, not a symlink')

    def path(self, relative):
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('relative knowledge path required')
        value = (self.root / relative).resolve()
        if self.root not in value.parents:
            raise ValueError('knowledge path escapes root')
        return value

    def writable(self):
        marker = self.path('runtime.json')
        if marker.exists() and read_json(marker).get('writer_root') != str(self.skill_root):
            raise PermissionError('this copy is not the writable knowledge authority')

    @contextmanager
    def lock(self):
        self.writable()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path('.writer.lock')
        # O_EXCL makes a lock conflict a finite failure, never a retry loop.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(json.dumps({'pid': os.getpid(), 'started_at': now()}))
            yield
        finally:
            path.unlink(missing_ok=True)

    def catalog(self):
        value = read_json(self.path('catalog.json'))
        if value.get('schema_version') != SCHEMA_VERSION:
            raise ValueError('incompatible knowledge schema')
        if not isinstance(value.get('entries'), dict) or not isinstance(value.get('disciplines'), dict):
            raise ValueError('corrupt knowledge catalog')
        return value

    def initialize(self):
        with self.lock():
            if not self.path('catalog.json').exists():
                atomic_json(self.path('catalog.json'), {'schema_version': SCHEMA_VERSION,
                            'generation': 0, 'entries': {}, 'disciplines': {}, 'aliases': {},
                            'legacy_ids': {}, 'refresh': {}})
            if not self.path('runtime.json').exists():
                atomic_json(self.path('runtime.json'), {'writer_root': str(self.skill_root)})
        return self.catalog()

    def _commit(self, old, new, reason):
        atomic_json(self.path('history/catalog-' + str(old['generation']) + '.json'), old)
        new['generation'] = old['generation'] + 1
        new['updated_at'] = now()
        new['change_reason'] = reason
        atomic_json(self.path('catalog.json'), new)

    def discipline(self, name):
        catalog = self.catalog()
        return catalog.get('aliases', {}).get(name.casefold(), name)

    def add_profile(self, profile, expected=None):
        allowed = {'schema_version', 'name', 'aliases', 'version', 'paradigms', 'source_portals',
                   'hotspot_categories', 'qualification', 'scope_fields', 'research_types',
                   'public_management', 'notes'}
        if set(profile) - allowed:
            raise ValueError('profile contains unsupported fields; permissions are not data')
        name = safe_name(profile.get('name'))
        if profile.get('schema_version') != 1 or type(profile.get('version')) is not int:
            raise ValueError('profile schema/version required')
        for key in ('aliases', 'paradigms', 'source_portals', 'hotspot_categories', 'scope_fields', 'research_types'):
            if not isinstance(profile.get(key), list):
                raise ValueError('profile needs list ' + key)
        if not profile['paradigms'] or not profile['hotspot_categories']:
            raise ValueError('minimal paradigm and source categories required')
        with self.lock():
            old = self.catalog(); new = json.loads(json.dumps(old))
            current = old['disciplines'].get(name)
            if (current or {}).get('version') != expected:
                raise ValueError('profile expected version conflict')
            if current and digest(self.profile(name)) == digest(profile):
                return current
            if profile['version'] != (expected or 0) + 1:
                raise ValueError('profile version must advance once')
            for alias in [name] + profile['aliases']:
                safe_name(alias)
                owner = old.get('aliases', {}).get(alias.casefold())
                if owner and owner != name:
                    raise ValueError('discipline alias conflict')
                new['aliases'][alias.casefold()] = name
            relative = 'disciplines/' + name + '/profiles/v' + str(profile['version']) + '.json'
            if self.path(relative).exists() and read_json(self.path(relative)) != profile:
                raise ValueError('immutable profile version already exists')
            atomic_json(self.path(relative), profile)
            new['disciplines'][name] = {'path': relative, 'version': profile['version'], 'sha256': digest(profile)}
            self._commit(old, new, 'profile ' + name)
        try:
            self.rebuild_indexes()
        except OSError:
            pass  # Committed profile remains valid; rebuild the disposable cache later.
        return new['disciplines'][name]

    def profile(self, name):
        name = self.discipline(name)
        pointer = self.catalog()['disciplines'][name]
        obj = read_json(self.path(pointer['path']))
        if digest(obj) != pointer['sha256']:
            raise ValueError('profile digest mismatch')
        return obj

    def entry(self, ident, pointer=None):
        if not isinstance(ident, str) or not ID.fullmatch(ident):
            raise ValueError('invalid knowledge ID')
        catalog = self.catalog() if pointer is None else None
        if catalog:
            ident = catalog.get('legacy_ids', {}).get(ident, ident)
            pointer = catalog['entries'][ident]
        obj = read_json(self.path(pointer['path']))
        if obj.get('id') != ident or obj.get('version') != pointer['version'] or digest(obj) != pointer['sha256']:
            raise ValueError('knowledge pointer/version/digest mismatch')
        return obj

    def validate_candidate(self, obj, catalog=None):
        if not isinstance(obj, dict) or obj.get('schema_version') != 1 or not ID.fullmatch(str(obj.get('id', ''))):
            raise ValueError('invalid candidate schema/ID')
        if type(obj.get('version')) is not int or obj['version'] < 1 or obj.get('kind') not in KINDS:
            raise ValueError('invalid candidate version/kind')
        for key in ('name_zh', 'name_en', 'concepts_and_propositions', 'analysis_level', 'conditions',
                    'applicable', 'inapplicable', 'competing_explanations', 'author_claims',
                    'assistant_guidance', 'maturity', 'verification_status', 'change_basis'):
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                raise ValueError('candidate missing ' + key)
        for key in ('aliases', 'disciplines', 'sources'):
            if not isinstance(obj.get(key), list):
                raise ValueError('candidate missing list ' + key)
        if not obj['disciplines'] or not obj['sources']:
            raise ValueError('candidate requires disciplines and public sources')
        catalog = catalog if catalog is not None else self.catalog()
        for discipline in obj['disciplines']:
            if discipline not in catalog['disciplines']:
                raise ValueError('create minimal discipline profile first')
        for source in obj['sources']:
            for key in ('title', 'url', 'access_level', 'read_locator', 'support', 'verified_on'):
                if not isinstance(source.get(key), str) or not source[key].strip():
                    raise ValueError('source missing ' + key)
            if not re.match(r'^https?://', source['url']):
                raise ValueError('only public HTTP(S) knowledge sources allowed')
            if source['access_level'] not in {'metadata', 'abstract', 'partial', 'fulltext'}:
                raise ValueError('invalid source reading depth')
            if source.get('support_level') not in {'metadata-only', 'limited', 'direct'}:
                raise ValueError('source support strength required independently of depth')
            try:
                date.fromisoformat(source['verified_on'])
                if 'published_at' not in source or 'accessed_at' not in source:
                    raise ValueError('separate publication and access dates required; unknown is null')
                if source['published_at'] is not None:
                    date.fromisoformat(source['published_at'])
                if source['accessed_at'] is not None:
                    if datetime.fromisoformat(source['accessed_at']).utcoffset() is None:
                        raise ValueError('access time requires timezone')
                elif not obj.get('legacy_sha256'):
                    raise ValueError('new source needs actual access timestamp')
            except (ValueError, TypeError):
                raise ValueError('invalid or missing source verification/publication/access dates')
            if source['access_level'] in {'metadata', 'abstract'} and source.get('support_level') == 'direct':
                raise ValueError('shallow reading supports limited claims only')
        # This declaration must follow actual source reading; the script does not certify it.
        review = obj.get('review') or {}
        if obj.get('verification_status') != 'verified' or review.get('status') != 'reviewed':
            raise ValueError('unreviewed knowledge remains in staging')
        for key in ('reviewer', 'source_check', 'dedup_check', 'conflicts'):
            if not isinstance(review.get(key), str) or not review[key].strip():
                raise ValueError('candidate review missing ' + key)
        if obj.get('private_material') is not False:
            raise ValueError('private material must not be persisted')

    def stage(self, obj):
        self.writable()
        relative = 'staging/' + uuid.uuid4().hex + '.json'
        atomic_json(self.path(relative), obj)
        return relative

    def publish(self, obj, expected=None):
        self.writable()
        self.validate_candidate(obj)
        with self.lock():
            old = self.catalog(); new = json.loads(json.dumps(old))
            ident = obj['id']; current = old['entries'].get(ident)
            if (current or {}).get('version') != expected:
                raise ValueError('expected knowledge version conflict')
            if current and digest(self.entry(ident)) == digest(obj):
                return {'status': 'unchanged', 'entry': current}
            if current:
                def content(value):
                    return {key: item for key, item in value.items() if key not in {'version', 'change_basis', 'review'}}
                if digest(content(self.entry(ident))) == digest(content(obj)):
                    return {'status': 'unchanged', 'entry': current}
            if obj['version'] != (expected or 0) + 1:
                raise ValueError('knowledge revision must advance exactly once')
            # Same title with different meaning is permitted only after an explicit review.
            for other in old['entries']:
                entry = self.entry(other)
                shared = {obj['name_zh'].casefold(), obj['name_en'].casefold()} & {
                    entry['name_zh'].casefold(), entry['name_en'].casefold()}
                if other != ident and shared and not obj.get('homonym_distinction'):
                    raise ValueError('duplicate name; reuse stable ID or document homonym distinction')
                if other != ident and obj.get('identity_key') and obj.get('identity_key') == entry.get('identity_key'):
                    raise ValueError('duplicate stable source/concept identity; use existing ID')
            owner = obj['disciplines'][0]
            if current:
                owner = self.entry(ident)['disciplines'][0]
            relative = 'disciplines/' + owner + '/entries/' + ident + '/v' + str(obj['version']) + '.json'
            if self.path(relative).exists() and read_json(self.path(relative)) != obj:
                raise ValueError('immutable entry version already exists; recover orphan first')
            atomic_json(self.path(relative), obj)
            new['entries'][ident] = {'path': relative, 'version': obj['version'], 'sha256': digest(obj)}
            self._commit(old, new, 'publish ' + ident + ': ' + obj['change_basis'])
        # A crash here leaves a complete committed catalog; indexes are disposable.
        try:
            self.rebuild_indexes()
            index_state = 'current'
        except OSError:
            index_state = 'rebuild-needed'
        return {'status': 'published', 'entry': new['entries'][ident], 'indexes': index_state}

    def rebuild_indexes(self):
        with self.lock():
            catalog = self.catalog()
            for name in catalog['disciplines']:
                entries = []
                for ident in catalog['entries']:
                    obj = self.entry(ident)
                    linked = name + '/' + ident in catalog.get('applications', {})
                    if name in obj['disciplines'] or linked:
                        entries.append({'id': ident, 'name_zh': obj['name_zh'], 'name_en': obj['name_en'],
                                        'aliases': obj['aliases'], 'kind': obj['kind'],
                                        **catalog['entries'][ident]})
                atomic_json(self.path('disciplines/' + name + '/index.json'),
                            {'schema_version': 1, 'generation': catalog['generation'], 'entries': entries})
                atomic_json(self.path('disciplines/' + name + '/profile.json'), self.profile(name))

    def search(self, query, discipline=None, limit=4):
        catalog = self.catalog()
        name = self.discipline(discipline) if discipline else None
        if name and name not in catalog['disciplines']:
            return []
        # Read only the selected discipline index. Repair stays inside this store.
        if name:
            try:
                index = read_json(self.path('disciplines/' + name + '/index.json'))
                if index.get('generation') != catalog['generation']:
                    raise ValueError('stale index')
                expected = {ident for ident in catalog['entries'] if name in self.entry(ident)['disciplines']
                            or name + '/' + ident in catalog.get('applications', {})}
                rows = index.get('entries')
                if not isinstance(rows, list) or len(rows) != len(expected) or {r['id'] for r in rows} != expected:
                    raise ValueError('incomplete index')
                for row in rows:
                    obj = self.entry(row['id']); pointer = catalog['entries'][row['id']]
                    if any(row.get(key) != pointer[key] for key in ('path', 'version', 'sha256')) or any(
                            row.get(key) != obj[key] for key in ('name_zh', 'name_en', 'aliases', 'kind')):
                        raise ValueError('corrupt index row')
            except (OSError, ValueError, KeyError, TypeError):
                self.rebuild_indexes()
                index = read_json(self.path('disciplines/' + name + '/index.json'))
            rows = index['entries']
        else:
            rows = [{'id': key} for key in catalog['entries']]
        terms = [t.casefold() for t in query.split()]
        scored = []
        for row in rows:
            # An index is only a locator; check each selected pointer against catalog.
            ident = row['id']
            pointer = catalog['entries'].get(ident)
            if not pointer:
                continue
            if len(row) > 1:
                if any(row.get(key) != pointer.get(key) for key in ('path', 'version', 'sha256')):
                    raise ValueError('index pointer differs from authoritative catalog')
                hay = json.dumps(row, ensure_ascii=False).casefold()
            else:
                hay = json.dumps(self.entry(ident), ensure_ascii=False).casefold()
            score = sum(term in hay for term in terms)
            if score or not terms:
                scored.append((score, ident))
        return [dict(id=ident, **catalog['entries'][ident]) for _, ident in
                sorted(scored, key=lambda pair: (-pair[0], pair[1]))[:max(0, min(limit, 10))]]

    def add_application(self, discipline, ident, application, expected=None):
        name = self.discipline(discipline); safe_name(name)
        obj = self.entry(ident)
        if name not in self.catalog()['disciplines']:
            raise ValueError('unknown discipline')
        for key in ('fit', 'level', 'conditions', 'limits', 'basis'):
            if not isinstance(application.get(key), str) or not application[key].strip():
                raise ValueError('application missing ' + key)
        if application.get('entry_version') != obj['version']:
            raise ValueError('application must bind the actual core version')
        with self.lock():
            old = self.catalog(); new = json.loads(json.dumps(old))
            key = name + '/' + ident
            previous = old.get('applications', {}).get(key)
            if (previous or {}).get('version') != expected:
                raise ValueError('application expected version conflict')
            if application.get('version') != (expected or 0) + 1:
                raise ValueError('application version must advance once')
            relative = 'disciplines/' + name + '/applications/' + ident + '/v' + str(application['version']) + '.json'
            if self.path(relative).exists() and read_json(self.path(relative)) != application:
                raise ValueError('immutable application version already exists')
            atomic_json(self.path(relative), application)
            new.setdefault('applications', {})[key] = {'path': relative, 'version': application['version'],
                                                     'sha256': digest(application)}
            self._commit(old, new, 'application ' + key)
        try:
            self.rebuild_indexes()
        except OSError:
            pass
        return new['applications'][key]

    def record_refresh(self, discipline, scope, record):
        """Failed attempts never advance last_success_at; scope keys keep gaps distinct."""
        name = self.discipline(discipline)
        if name not in self.catalog()['disciplines']:
            raise ValueError('unknown discipline')
        if record.get('status') not in {'completed', 'limited', 'failed'}:
            raise ValueError('refresh result required')
        stamp = datetime.fromisoformat(record['attempted_at'])
        if stamp.utcoffset() is None:
            raise ValueError('refresh timestamp needs timezone')
        with self.lock():
            old = self.catalog(); new = json.loads(json.dumps(old))
            key = digest([name, scope])
            previous = old.get('refresh', {}).get(key, {})
            last_success = previous.get('last_success_at')
            if record['status'] == 'completed':
                last_success = record['completed_at']
                done = datetime.fromisoformat(last_success)
                if done.utcoffset() is None or done < stamp:
                    raise ValueError('invalid refresh completion time')
            new['refresh'][key] = {'discipline': name, 'scope': scope, 'last_attempt': record,
                                   'last_success_at': last_success}
            self._commit(old, new, 'refresh ' + name)
        return new['refresh'][key]

    def refresh_window(self, discipline, scope, overlap_days=30):
        key = digest([self.discipline(discipline), scope])
        previous = self.catalog().get('refresh', {}).get(key, {})
        stamp = previous.get('last_success_at')
        return (datetime.fromisoformat(stamp) - timedelta(days=overlap_days)).date().isoformat() if stamp else None

    def verify_catalog(self, catalog):
        if catalog.get('schema_version') != SCHEMA_VERSION:
            raise ValueError('incompatible catalog schema')
        for name, pointer in catalog['disciplines'].items():
            safe_name(name)
            obj = read_json(self.path(pointer['path']))
            if digest(obj) != pointer['sha256'] or obj.get('name') != name or obj.get('version') != pointer['version']:
                raise ValueError('profile digest/version mismatch')
        for ident, pointer in catalog['entries'].items():
            self.validate_candidate(self.entry(ident, pointer), catalog)
        for alias, name in catalog.get('aliases', {}).items():
            if name not in catalog['disciplines']:
                raise ValueError('broken discipline alias')
        for old_id, ident in catalog.get('legacy_ids', {}).items():
            if ident not in catalog['entries'] or not ID.fullmatch(old_id):
                raise ValueError('broken legacy mapping')
        for key, pointer in catalog.get('applications', {}).items():
            application = read_json(self.path(pointer['path']))
            name, ident = key.split('/', 1)
            core = catalog['entries'].get(ident)
            if digest(application) != pointer['sha256'] or application.get('version') != pointer['version']:
                raise ValueError('application digest mismatch ' + key)
            if name not in catalog['disciplines'] or not core or type(application.get('entry_version')) is not int or not 1 <= application['entry_version'] <= core['version']:
                raise ValueError('application core version reference mismatch ' + key)
            for field in ('fit', 'level', 'conditions', 'limits', 'basis'):
                if not application.get(field):
                    raise ValueError('application missing ' + field)
        return True

    def verify(self):
        catalog = self.catalog()
        self.verify_catalog(catalog)
        return {'entries': len(catalog['entries']), 'disciplines': len(catalog['disciplines']),
                'generation': catalog['generation'], 'status': 'valid'}

    def recover(self, generation, expected_generation):
        """Explicit restore: validate archived pointers, then commit as a new generation."""
        with self.lock():
            old = self.catalog()
            if old['generation'] != expected_generation:
                raise ValueError('recovery generation conflict')
            new = read_json(self.path('history/catalog-' + str(int(generation)) + '.json'))
            # Validate every historical reference before touching the active pointer.
            self.verify_catalog(new)
            self._commit(old, new, 'explicit recovery from ' + str(generation))
        self.rebuild_indexes()
        return self.verify()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init'); sub.add_parser('verify'); sub.add_parser('reindex')
    p = sub.add_parser('search'); p.add_argument('query'); p.add_argument('--discipline'); p.add_argument('--limit', type=int, default=4)
    p = sub.add_parser('show'); p.add_argument('id'); p.add_argument('--full', action='store_true', help='include lossless migration/audit fields')
    p = sub.add_parser('stage'); p.add_argument('file', type=Path)
    p = sub.add_parser('publish'); p.add_argument('candidate', help='staging-relative path'); p.add_argument('--expected', type=int)
    p = sub.add_parser('profile'); p.add_argument('file', type=Path); p.add_argument('--expected', type=int)
    p = sub.add_parser('application'); p.add_argument('discipline'); p.add_argument('id'); p.add_argument('file', type=Path); p.add_argument('--expected', type=int)
    p = sub.add_parser('refresh'); p.add_argument('discipline'); p.add_argument('scope'); p.add_argument('file', type=Path)
    p = sub.add_parser('window'); p.add_argument('discipline'); p.add_argument('scope')
    p = sub.add_parser('recover'); p.add_argument('generation', type=int); p.add_argument('--expected-generation', type=int, required=True)
    args = parser.parse_args(argv); kb = KnowledgeBase()
    try:
        if args.command == 'init': result = kb.initialize()
        elif args.command == 'verify': result = kb.verify()
        elif args.command == 'reindex': kb.rebuild_indexes(); result = {'status': 'rebuilt'}
        elif args.command == 'search': result = kb.search(args.query, args.discipline, args.limit)
        elif args.command == 'show':
            result = kb.entry(args.id)
            if not args.full:
                result = {key: value for key, value in result.items() if key not in {
                    'legacy_markdown', 'legacy_sha256', 'legacy_path', 'review', 'change_basis',
                    'origin', 'public_management_conditions'}}
        elif args.command == 'stage': result = kb.stage(read_json(args.file))
        elif args.command == 'publish':
            path = kb.path(args.candidate)
            if kb.path('staging') not in path.parents: raise ValueError('publish requires staged candidate')
            result = kb.publish(read_json(path), args.expected)
        elif args.command == 'profile': result = kb.add_profile(read_json(args.file), args.expected)
        elif args.command == 'application': result = kb.add_application(args.discipline, args.id, read_json(args.file), args.expected)
        elif args.command == 'refresh': result = kb.record_refresh(args.discipline, args.scope, read_json(args.file))
        elif args.command == 'window': result = kb.refresh_window(args.discipline, args.scope)
        else: result = kb.recover(args.generation, args.expected_generation)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc), 'persisted': False, 'action': 'continue paper analysis; retain candidate in run directory'}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
