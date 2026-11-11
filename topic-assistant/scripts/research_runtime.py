"""3.0 run contracts: discipline routing, bounded refresh and immutable snapshots."""
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

POLICY_VERSION = '3.0'
MANIFEST_SCHEMA = 6
NETWORK = {'pending', 'online', 'offline', 'disabled', 'source-limited'}
MODES = {'paper-only', 'local-knowledge', 'refreshed-knowledge'}
REFRESH = {'pending', 'completed', 'limited', 'failed', 'skipped-offline', 'skipped-disabled', 'not-required', 'reused'}
INFERENCES = {'text', 'association', 'mechanism', 'effect', 'proof', 'design', 'interpretation', 'normative'}
FORMS = {'document', 'item', 'paired-versions', 'matched-records', 'process-record', 'outcome-measure',
         'proof', 'construction', 'argument', 'interpretive-corpus'}


def kb_module():
    spec = importlib.util.spec_from_file_location('_knowledge_runtime', Path(__file__).with_name('knowledge_base.py'))
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj


def context(c):
    value = getattr(c, '_manifest', None)
    if value is not None:
        return value
    path = c.root / 'manifest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def modern(c):
    return context(c).get('policy_version') == POLICY_VERSION


def public_management(c):
    if not modern(c):
        return True  # historical helper API regression; full check rejects old runs
    return context(c).get('discipline', {}).get('primary') == '公共管理'


def initial(discipline=None, research_type='empirical', network='pending'):
    original = discipline
    primary = discipline
    profile = None
    if discipline:
        try:
            kb = kb_module().KnowledgeBase()
            primary = kb.discipline(discipline)
            profile = kb.profile(primary)
        except (OSError, ValueError, KeyError):
            pass
    refresh = 'skipped-disabled' if network == 'disabled' else 'skipped-offline' if network == 'offline' else 'pending'
    return {'discipline': {'original': original, 'primary': primary, 'auxiliary': [],
                          'research_type': research_type,
                          'profile_version': (profile or {}).get('version'),
                          'hotspot_categories': (profile or {}).get('hotspot_categories', ['academic', 'practice'])},
            'network_status': network, 'knowledge_mode': 'paper-only',
            'theory_selection': {'status': 'not-used', 'reason': '尚未选用适用知识；仅按实际论文证据分析。', 'used_entries': []},
            'theory_refresh': {'status': refresh, 'reason': '按实际网络状态执行；维护及同任务轻量操作复用。',
                               'scope': None, 'gap': False, 'queries': [], 'attempts': [], 'sources': [],
                               'searched_at': None, 'attempted_at': None, 'completed_at': None,
                               'previous_success_at': None, 'window_start': None}}


def snapshot(root, kb=None):
    """Freeze exactly the entries actually selected; a pure-paper run creates nothing."""
    root = Path(root).resolve(); path = root / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('policy_version') != POLICY_VERSION:
        raise ValueError('create a 3.0 run; never relabel historical runs')
    entries = manifest.get('theory_selection', {}).get('used_entries', [])
    if not entries:
        if manifest.get('knowledge_snapshot'):
            raise ValueError('remove selected knowledge explicitly before creating a new run snapshot')
        return {'status': 'not-applicable'}
    mod = kb_module(); kb = kb or mod.KnowledgeBase()
    profile_names = [manifest['discipline']['primary']] + manifest['discipline'].get('auxiliary', [])
    profiles = [kb.profile(name) for name in profile_names]
    cards = []
    for selected in entries:
        obj = kb.entry(selected['id'])
        if selected.get('version') != obj['version'] or not selected.get('fit'):
            raise ValueError('select actual version and explain fit before freezing')
        cards.append(obj)
    applications = []
    catalog = kb.catalog()
    for name in profile_names:
        for card in cards:
            pointer = catalog.get('applications', {}).get(name + '/' + card['id'])
            if pointer:
                application = mod.read_json(kb.path(pointer['path']))
                if mod.digest(application) != pointer['sha256'] or application.get('entry_version') != card['version']:
                    raise ValueError('cross-discipline application is stale or corrupt')
                applications.append({'discipline': name, 'id': card['id'], 'content': application})
    value = {'schema_version': 1, 'version': 1, 'profiles': profiles, 'entries': cards, 'applications': applications}
    destination = root / 'knowledge-snapshot.json'
    if destination.exists() and mod.read_json(destination) != value:
        raise ValueError('knowledge snapshot already frozen; use a new run for a changed knowledge selection')
    mod.atomic_json(destination, value)
    manifest['knowledge_snapshot'] = {'path': destination.name, 'sha256': mod.digest(value)}
    mod.atomic_json(path, manifest)
    return {'status': 'frozen', 'entries': len(cards), 'profiles': len(profiles)}


def frozen(c):
    manifest = context(c); pointer = manifest.get('knowledge_snapshot')
    if not pointer:
        return {}
    value = c.load(pointer['path'])
    if kb_module().digest(value) != pointer.get('sha256') or value.get('schema_version') != 1:
        raise ValueError('knowledge snapshot digest/schema mismatch')
    return value


def check(c, manifest):
    c._manifest = manifest
    discipline = manifest.get('discipline') or {}
    for key in ('original', 'primary', 'research_type'):
        c.need(isinstance(discipline.get(key), str) and bool(discipline[key].strip()), 'discipline requires ' + key)
    c.need(isinstance(discipline.get('auxiliary'), list), 'discipline auxiliary must be an array')
    c.need(isinstance(discipline.get('hotspot_categories'), list) and bool(discipline.get('hotspot_categories')),
           'discipline hotspot categories required')
    network = manifest.get('network_status'); mode = manifest.get('knowledge_mode')
    c.need(network in NETWORK - {'pending'}, 'record actual network status, not pending')
    c.need(mode in MODES, 'invalid knowledge_mode')
    selection = manifest.get('theory_selection') or {}
    used = selection.get('used_entries')
    c.need(isinstance(used, list), 'theory_selection.used_entries must be an array')
    if not isinstance(used, list): used = []
    c.need(bool(selection.get('reason')), 'theory_selection reason required')
    c.need(selection.get('status') == ('used' if used else 'not-used'), 'theory_selection status conflicts with actual use')
    c.need((mode == 'paper-only') == (not used), 'paper-only requires no external knowledge entries')
    seen = set()
    for item in used:
        c.need(isinstance(item.get('id'), str) and item.get('id') not in seen, 'duplicate/invalid selected knowledge ID')
        seen.add(item.get('id'))
        c.need(type(item.get('version')) is int and item['version'] > 0 and bool(item.get('fit')),
               'used knowledge requires version and fit')
    if used:
        try:
            value = frozen(c)
            entries = {e['id']: e for e in value.get('entries', [])}
            c.need(set(entries) == seen, 'snapshot must cover exactly actually used entries')
            profiles = {p['name']: p for p in value.get('profiles', [])}
            expected = {discipline.get('primary')} | set(discipline.get('auxiliary', []))
            c.need(set(profiles) == expected, 'snapshot must bind main and auxiliary profiles')
            if discipline.get('primary') in profiles:
                c.need(profiles[discipline['primary']]['version'] == discipline.get('profile_version'),
                       'selected discipline profile version differs from snapshot')
            for item in used:
                obj = entries.get(item['id'], {})
                c.need(obj.get('version') == item['version'] and bool(obj.get('sources')) and
                       obj.get('verification_status') == 'verified', 'invalid frozen knowledge version/source/status')
                # A shared core may list disciplines not participating in this run.
                known_disciplines = {name: {} for name in obj.get('disciplines', [])}
                known_disciplines.update(profiles)
                kb_module().KnowledgeBase().validate_candidate(obj, {'disciplines': known_disciplines})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            c.need(False, 'knowledge snapshot required: ' + str(exc))
    else:
        c.need(not manifest.get('knowledge_snapshot'), 'pure-paper mode must not depend on an unused knowledge snapshot')
    refresh = manifest.get('theory_refresh') or {}
    status = refresh.get('status')
    c.need(status in REFRESH - {'pending'}, 'record completed, limited or skipped theory refresh')
    c.need(bool(refresh.get('reason')), 'theory_refresh reason required')
    if network in {'offline', 'disabled'}:
        c.need(status == ('skipped-offline' if network == 'offline' else 'skipped-disabled'), 'network and skipped refresh disagree')
        c.need(refresh.get('searched_at') is None and refresh.get('completed_at') is None,
               'skipped refresh cannot claim a search or successful completion')
    if network in {'online', 'source-limited'}:
        c.need(status in {'completed', 'limited', 'failed', 'not-required', 'reused'}, 'online research must attempt refresh')
    if status in {'not-required', 'reused'}:
        c.need(bool(refresh.get('reuse_basis')), 'light operation or same-task reuse needs actual basis')
    query_limit, target_limit = (4, 8) if refresh.get('gap') else (2, 4)
    for key, maximum in (('queries', query_limit), ('attempts', target_limit)):
        values = refresh.get(key)
        c.need(isinstance(values, list) and len(values) <= maximum, 'theory refresh budget exceeded: ' + key)
        if network in {'offline', 'disabled'}:
            c.need(not values, 'offline/disabled cannot contain executed external ' + key)
    if status in {'completed', 'limited', 'failed'}:
        c.need(bool(refresh.get('scope')), 'refresh needs current discipline/problem scope')
        _time(c, refresh.get('attempted_at'), 'refresh attempted_at')
    if status in {'completed', 'limited'}:
        c.need(bool(refresh.get('queries')), 'executed refresh requires literal queries')
        _time(c, refresh.get('searched_at'), 'refresh searched_at')
    if status == 'completed':
        done = _time(c, refresh.get('completed_at'), 'refresh completed_at')
        attempted = _time(c, refresh.get('attempted_at'), 'refresh attempted_at')
        if done and attempted: c.need(done >= attempted, 'refresh completion precedes attempt')
    else:
        c.need(refresh.get('completed_at') is None or status == 'reused', 'failed/skipped refresh cannot advance successful completion')
    previous = refresh.get('previous_success_at')
    if previous and refresh.get('window_start'):
        try:
            c.need(datetime.fromisoformat(refresh['window_start']).date() <= datetime.fromisoformat(previous).date(),
                   'refresh window must overlap previous successful search')
        except ValueError: c.need(False, 'invalid refresh overlap date')
    for query in refresh.get('queries', []):
        c.need(bool(query.get('query')) and bool(query.get('reviewed_scope')), 'refresh needs actual query and reviewed scope')
        _time(c, query.get('searched_at'), 'theory query')
    read_urls = set()
    for attempt in refresh.get('attempts', []):
        c.need(attempt.get('outcome') in {'read', 'partial', 'failed'}, 'invalid theory source attempt outcome')
        c.need(str(attempt.get('url', '')).startswith(('https://', 'http://')), 'theory attempt requires public URL')
        _time(c, attempt.get('accessed_at'), 'theory source attempt')
        if attempt.get('outcome') in {'read', 'partial'}: read_urls.add(attempt.get('url'))
    sources = refresh.get('sources', [])
    c.need(isinstance(sources, list), 'refresh sources must be an array')
    for source in sources if isinstance(sources, list) else []:
        c.need(source.get('url') in read_urls, 'theory source needs actual successful visit')
        c.need('source_id' not in source and 'evidence_ids' not in source, 'theory sources cannot enter paper registry')
        spec = importlib.util.spec_from_file_location('_runtime_source_design', Path(__file__).with_name('research_design.py'))
        design = importlib.util.module_from_spec(spec); spec.loader.exec_module(design)
        design.external_source(c, source, 'theory refresh source')
    if network in {'offline', 'disabled'}:
        c.need(not sources, 'offline refresh cannot contain newly read web sources')
        for filename in ('hotspots.json', 'web-feasibility.json'):
            if not (c.root / filename).is_file(): continue
            obj = c.load(filename)
            c.need(not obj.get('queries') and not obj.get('attempts') and not obj.get('sources'), 'offline external stage cannot claim executed network activity')
            for result in obj.get('results', []):
                c.need(not result.get('searches') and not result.get('attempts'), 'offline web result cannot claim network searches')


def _time(c, value, label):
    try:
        stamp = datetime.fromisoformat(value)
        c.need(stamp.utcoffset() is not None, label + ' needs timezone')
        return stamp
    except (ValueError, TypeError):
        c.need(False, label + ' needs actual timestamp'); return None
