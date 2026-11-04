"""2.11 research gates. Checks declarations and provenance, not scholarly truth.

No network calls, model calls, directory discovery or automatic approval.
"""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

LIBRARY = Path(__file__).resolve().parent.parent / 'references' / 'theories'
CATEGORIES = ('governance', 'policy', 'academic-cn', 'academic-intl')
QUALIFICATION = ('scope', 'single_problem', 'problem_basis', 'ai_boundary',
                 'theory_fit', 'decision_relevance')
SCOPE = ('region', 'population', 'setting', 'time_window', 'unit', 'basis')
DESIGN = ('fit', 'mechanism', 'observables', 'method_fit', 'alternative',
          'china_context', 'limits')
DECISION = ('actor', 'lever', 'expected_answer', 'evaluation', 'conditions', 'alternative_result')
SAMPLE_FORMS = {'document', 'item', 'paired-versions', 'matched-records',
                'process-record', 'outcome-measure'}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def design_signature(topic):
    """Bind semantic review to this design; hashing never approves its meaning."""
    closure = {k: v for k, v in (topic.get('closure') or {}).items() if k != 'review'}
    value = {k: topic.get(k) for k in ('title', 'question', 'scope', 'theory', 'decision')}
    value['closure'] = closure
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def check_closure(c, tid, topic, final=False):
    scope = topic.get('scope') or {}
    selection = (scope.get('selection') or {}) if isinstance(scope, dict) else {}
    c.need(selection.get('status') == 'fixed', tid + ': actual scope selection must be fixed')
    units = selection.get('units')
    c.need(isinstance(units, list) and bool(units) and all(nonempty(u) for u in units),
           tid + ': name the actually selected scope units')
    c.need(nonempty(selection.get('basis')), tid + ': scope selection requires basis')
    closure = topic.get('closure') or {}
    value = closure.get('research_value')
    if not isinstance(value, dict):
        value = {}
    c.need(value.get('question_status') == 'requires-analysis',
           tid + ': eligible topic needs an unresolved analytical question, not source lookup')
    for key in ('known_answer', 'open_question', 'new_knowledge', 'theory_use'):
        c.need(nonempty(value.get(key)), tid + ': research value missing ' + key)
    for key in ('core_judgment', 'judgment_rule', 'criterion_basis', 'applicability', 'allowed_conclusion', 'limits'):
        c.need(nonempty(closure.get(key)), tid + ': closure missing ' + key)
    level = closure.get('inference_level')
    c.need(level in {'text', 'association', 'mechanism', 'effect'}, tid + ': classify inference level')
    observables = c.indexed(closure.get('observables', []), 'observable_id')
    c.need(bool(observables), tid + ': closure requires core observables')
    for oid, item in observables.items():
        for key in ('variable', 'definition', 'unit'):
            c.need(nonempty(item.get(key)), tid + '/' + oid + ': missing ' + key)
        c.need(item.get('required_form') in SAMPLE_FORMS, tid + '/' + oid + ': invalid sample form')
        fields = item.get('required_fields')
        c.need(isinstance(fields, list) and bool(fields) and all(nonempty(f) for f in fields),
               tid + '/' + oid + ': name required sample fields')
    if level in {'mechanism', 'effect'}:
        needed = 'process-record' if level == 'mechanism' else 'outcome-measure'
        c.need(any(o.get('required_form') == needed for o in observables.values()),
               tid + ': inference requires ' + needed + ' evidence')
    links = closure.get('decision_links', [])
    c.need(isinstance(links, list) and bool(links), tid + ': decision needs conditional evidence links')
    covered = set()
    for link in links if isinstance(links, list) else []:
        ids = link.get('observable_ids', [])
        c.need(isinstance(ids, list) and bool(ids) and all(oid in observables for oid in ids),
               tid + ': decision refers to unknown/missing observables')
        if isinstance(ids, list): covered.update(oid for oid in ids if isinstance(oid, str))
        for key in ('condition', 'action', 'basis', 'applicability'):
            c.need(nonempty(link.get(key)), tid + ': decision link missing ' + key)
    c.need(set(observables) <= covered, tid + ': core observables are disconnected from decisions')
    if final:
        review = closure.get('review') or {}
        c.need(review.get('status') in {'supported', 'limited'}, tid + ': final design needs semantic closure review')
        c.need(nonempty(review.get('reason')), tid + ': closure review needs substantive reason')
        c.need(review.get('design_sha256') == design_signature(topic), tid + ': design changed after closure review')


def check_data_evidence(c, tid, topic, result, hot, report, final):
    """Validate declared sample coverage/provenance, never infer source contents."""
    observables = c.indexed((topic.get('closure') or {}).get('observables', []), 'observable_id')
    checks = c.indexed(result.get('data_checks', []), 'observable_id')
    c.need(bool(observables), tid + ': data gate requires closure observables')
    c.need(set(checks) == set(observables), tid + ': core data check coverage mismatch')
    sources = {}
    reused = {i.get('web_id') for i in result.get('reused_hotspot_sources', [])}
    for source in (hot or {}).get('sources', []):
        if source.get('web_id') in reused: sources[('hotspot', source['web_id'])] = source
    for search in result.get('searches', []):
        for source in search.get('sources', []): sources[('web', source.get('url'))] = source
    refs = c.load('references.json') if (c.root / 'references.json').is_file() else {}
    for source in refs.get('sources', []): sources[('local', source.get('source_id'))] = source
    local_evidence = getattr(c, '_checked_evidence', None)
    manifest = None
    all_verified = bool(checks) and set(checks) == set(observables)
    for oid, check in checks.items():
        label = tid + '/' + oid
        state = check.get('status')
        c.need(state in {'verified', 'unverified', 'unavailable'}, label + ': invalid core data state')
        c.need(nonempty(check.get('reason')), label + ': core data needs reason')
        samples = check.get('samples', [])
        c.need(isinstance(samples, list), label + ': samples must be an array')
        if not isinstance(samples, list): samples = []
        all_verified = all_verified and state == 'verified'
        if state == 'unavailable' and final:
            c.need(False, label + ': proven unavailable core data excludes this final design')
        if state != 'verified': continue
        c.need(bool(samples), label + ': verified core data needs an actual sample')
        observable = observables.get(oid, {})
        required = observable.get('required_fields', [])
        pairs = {}
        for sample in samples:
            ref = sample.get('source') or {}
            source = sources.get((ref.get('kind'), ref.get('ref')))
            c.need(source is not None, label + ': sample source was not actually registered/read for this topic')
            if source:
                if ref.get('kind') == 'local':
                    if manifest is None:
                        manifest = c.load('manifest.json') if (c.root / 'manifest.json').is_file() else {}
                    c.need(any(i.get('source_id') == ref.get('ref') for i in manifest.get('inputs', [])),
                           label + ': local sample must be a registered input paper')
                    if local_evidence is None:
                        evidence_items = list(refs.get('evidence', []))
                        for item in manifest.get('inputs', []):
                            if item.get('card_path') and c.path(item['card_path']).is_file():
                                evidence_items.extend(c.load(item['card_path']).get('evidence', []))
                        local_evidence = c.indexed(evidence_items, 'evidence_id')
                    ids = sample.get('evidence_ids', [])
                    c.need(isinstance(ids, list) and bool(ids) and all(
                        eid in local_evidence and local_evidence[eid].get('source_id') == ref.get('ref')
                        and local_evidence[eid].get('access_level') == 'fulltext' for eid in ids),
                        label + ': local sample needs actual fulltext evidence positions')
                    c.need(source.get('access_level') == 'fulltext', label + ': local metadata/abstract cannot verify core data')
                else:
                    c.need(source.get('access_level') in {'document', 'partial', 'fulltext'},
                           label + ': landing page/metadata/abstract cannot verify core data')
            for key in ('locator', 'observed', 'unit_key'):
                c.need(nonempty(sample.get(key)), label + ': sample missing ' + key)
            c.need(sample.get('form') == observable.get('required_form'), label + ': sample form does not answer the design')
            fields = sample.get('fields', [])
            c.need(isinstance(fields, list) and all(f in fields for f in required),
                   label + ': actual sample lacks required fields')
            if observable.get('required_form') == 'paired-versions':
                c.need(nonempty(sample.get('version_key')), label + ': paired sample needs version key')
                pairs.setdefault(sample.get('unit_key'), set()).add(sample.get('version_key'))
        if observable.get('required_form') == 'paired-versions':
            c.need(any(len(v) >= 2 for v in pairs.values()), label + ': historical comparison needs matched units and distinct versions')
    if not all_verified:
        c.need(result.get('status') != 'confirmed' and result.get('effect_on_verdict') != '建议做',
               tid + ': unverified core data cannot be confirmed/recommended without conditions')
        if final:
            c.need(report.get('status') == 'draft', tid + ': unverified core data requires draft delivery')
    review = (topic.get('closure') or {}).get('review') or {}
    if final and review.get('status') == 'limited':
        c.need(report.get('status') == 'draft', tid + ': limited closure review requires draft delivery')
        c.need(result.get('status') != 'confirmed' and result.get('effect_on_verdict') != '建议做',
               tid + ': limited closure review cannot receive unconditional confirmation')


def theory_path(theory_id):
    if not isinstance(theory_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', theory_id):
        raise ValueError('invalid theory ID')
    path = (LIBRARY / (theory_id + '.md')).resolve()
    if path.parent != LIBRARY.resolve():
        raise ValueError('theory path escapes library')
    return path


def theory_metadata(theory_id):
    text = theory_path(theory_id).read_text(encoding='utf-8')
    head = text.split('---', 2)
    if len(head) != 3 or head[0].strip():
        raise ValueError('theory card requires frontmatter')
    fields = dict(re.findall(r'^([a-z_]+):\s*(.*?)\s*$', head[1], re.M))
    if fields.get('theory_id') != theory_id:
        raise ValueError('theory card ID mismatch')
    return fields


def used_theories(root, artifact_path):
    """Only selected design cards invalidate design/report, never reading cards."""
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    report = manifest.get('report') or {}
    if artifact_path not in {'topics.json', 'feasibility.json', 'web-feasibility.json', 'final.md'}:
        if artifact_path != (manifest.get('report') or {}).get('markdown'):
            return {}
    path = root / 'topics.json'
    if not path.is_file():
        return {}
    ids = set()
    for topic in json.loads(path.read_text(encoding='utf-8')).get('topics', []):
        if artifact_path == report.get('markdown') and topic.get('topic_id') not in report.get('topic_ids', []):
            continue
        theory = topic.get('theory') or {}
        if theory.get('primary'):
            ids.add(theory['primary'])
        if theory.get('secondary'):
            ids.add(theory['secondary'])
    return {key: hashlib.sha256(theory_path(key).read_bytes()).hexdigest() for key in sorted(ids)}


def time_value(c, value, label):
    try:
        stamp = datetime.fromisoformat(value)
        c.need(stamp.utcoffset() is not None, label + ': timezone required')
        return stamp if stamp.utcoffset() is not None else None
    except (TypeError, ValueError):
        c.need(False, label + ': invalid timestamp')
        return None


def external_source(c, source, label, cutoff=None):
    for key in ('title', 'url', 'source_type', 'accessed_at', 'observed', 'limitations'):
        c.need(nonempty(source.get(key)), label + ': missing ' + key)
    c.need(bool(re.match(r'^https?://', str(source.get('url', '')))), label + ': HTTP(S) URL required')
    c.need('source_id' not in source and 'evidence_ids' not in source,
           label + ': external source cannot enter local paper registry')
    access = time_value(c, source.get('accessed_at'), label)
    if source.get('source_type') == 'academic':
        for key in ('journal', 'article_version', 'read_locator'):
            c.need(nonempty(source.get(key)), label + ': academic source needs ' + key)
        c.need(source.get('access_level') in {'metadata', 'abstract', 'partial', 'fulltext'},
               label + ': invalid academic reading depth')
        for key in ('fulltext_available', 'fulltext_opened', 'complete_text'):
            c.need(type(source.get(key)) is bool, label + ': declare ' + key)
        if source.get('fulltext_opened') is True:
            c.need(source.get('fulltext_available') is True,
                   label + ': cannot open an unavailable full text')
        if source.get('access_level') == 'fulltext':
            c.need(source.get('fulltext_available') is True and source.get('fulltext_opened') is True,
                   label + ': fulltext reading cannot exceed actual availability')
            c.need(source.get('complete_text') is True,
                   label + ': fulltext reading requires complete body and reference apparatus')
    else:
        c.need(source.get('access_level') in {'landing-page', 'metadata', 'abstract', 'document', 'partial', 'fulltext'},
               label + ': invalid access level')
    published = source.get('published_at')
    c.need('published_at' in source and source.get('date_basis') in {'publication', 'online-first', 'unknown'},
           label + ': separate publication date from access/issue date')
    if published:
        try:
            day = date.fromisoformat(published)
            if cutoff:
                c.need(day <= cutoff, label + ': source published after cutoff')
            if access:
                c.need(day <= access.date(), label + ': publication follows claimed access')
            c.need(source.get('date_basis') != 'unknown', label + ': date basis missing')
        except (TypeError, ValueError):
            c.need(False, label + ': invalid publication date')
    else:
        c.need(source.get('date_basis') == 'unknown', label + ': unknown date must be explicit')
    if source.get('cache_path'):
        cache = c.path(source['cache_path'])
        c.need(cache.is_file(), label + ': missing run-local external cache')


def check_hotspots(c, manifest, required):
    path = c.root / 'hotspots.json'
    if required:
        c.need(path.is_file(), 'final selection requires hotspots.json before candidate formation')
    if not path.is_file():
        return None
    hot = c.load('hotspots.json')
    c.need(hot.get('purpose') == 'shared-preselection', 'hotspot purpose must be shared-preselection')
    c.need(hot.get('status') in {'complete', 'limited', 'unavailable'}, 'invalid hotspot status')
    if hot.get('status') != 'complete':
        c.need(nonempty(hot.get('reason')), 'limited hotspot scan requires a reason')
    try:
        cutoff = date.fromisoformat(hot.get('cutoff_date'))
    except (TypeError, ValueError):
        c.need(False, 'hotspots: cutoff_date required'); cutoff = None
    start = time_value(c, hot.get('started_at'), 'hotspots started_at')
    end = time_value(c, hot.get('checked_at'), 'hotspots checked_at')
    if start and end:
        c.need(0 <= (end - start).total_seconds() <= 720, 'hotspot scan exceeds twelve-minute limit or reversed time')
        if cutoff:
            c.need(end.date() == cutoff, 'hotspot cutoff must match actual execution date')
    queries = hot.get('queries', [])
    c.need(isinstance(queries, list) and len(queries) <= 6, 'hotspots: at most six literal queries')
    if not isinstance(queries, list): queries = []
    categories_seen = set()
    for item in queries:
        c.need(item.get('category') in CATEGORIES, 'hotspot query: invalid category')
        categories_seen.add(item.get('category'))
        for key in ('query', 'reviewed_scope'):
            c.need(nonempty(item.get(key)), 'hotspot query: missing ' + key)
        stamp = time_value(c, item.get('searched_at'), 'hotspot query')
        if start and end and stamp:
            c.need(start <= stamp <= end, 'hotspot query outside scan interval')
    attempts = hot.get('attempts', [])
    c.need(isinstance(attempts, list) and len(attempts) <= 12, 'hotspots: at most twelve direct source targets including failures')
    if not isinstance(attempts, list): attempts = []
    for item in attempts:
        c.need(bool(re.match(r'^https?://', str(item.get('url', '')))), 'hotspot attempt needs URL')
        c.need(item.get('outcome') in {'read', 'failed', 'partial'}, 'hotspot attempt needs outcome')
        stamp = time_value(c, item.get('accessed_at'), 'hotspot attempt')
        if start and end and stamp:
            c.need(start <= stamp <= end, 'hotspot attempt outside scan interval')
    categories = hot.get('categories', {})
    for key in CATEGORIES:
        item = categories.get(key, {})
        c.need(item.get('status') in {'checked', 'limited', 'unavailable'}, 'hotspots: category state missing: ' + key)
        c.need(nonempty(item.get('finding')), 'hotspots: category finding required: ' + key)
        if item.get('status') == 'checked':
            c.need(key in categories_seen, 'checked category lacks executed query: ' + key)
        if hot.get('status') == 'complete':
            c.need(item.get('status') == 'checked', 'complete hotspots must cover all four query categories')
    sources = c.indexed(hot.get('sources', []), 'web_id')
    read_urls = {item.get('url') for item in attempts if item.get('outcome') in {'read', 'partial'}}
    complete_urls = {item.get('url') for item in attempts if item.get('outcome') == 'read'}
    for key, source in sources.items():
        external_source(c, source, key, cutoff)
        c.need(source.get('url') in read_urls, key + ': source has no recorded successful/partial visit')
        if source.get('access_level') == 'fulltext':
            c.need(source.get('url') in complete_urls, key + ': fulltext claim conflicts with incomplete visit')
        accessed = time_value(c, source.get('accessed_at'), key)
        if start and end and accessed:
            c.need(start <= accessed <= end, key + ': access outside shared scan interval')
    fulltext = hot.get('academic_fulltext')
    c.need(fulltext in {'complete', 'limited', 'unavailable'}, 'declare academic_fulltext status')
    if fulltext == 'complete':
        c.need(any(s.get('source_type') == 'academic' and s.get('access_level') == 'fulltext' for s in sources.values()),
               'academic fulltext complete requires a relevant actually read full paper')
    else:
        c.need(nonempty(hot.get('academic_reason')), 'academic fulltext limitation requires a reason')
    signals = c.indexed(hot.get('signals', []), 'hotspot_id')
    for key, signal in signals.items():
        for field in ('claim', 'relevance'):
            c.need(nonempty(signal.get(field)), key + ': missing ' + field)
        ids = signal.get('web_ids', [])
        c.need(isinstance(ids, list) and bool(ids) and all(sid in sources for sid in ids), key + ': signal needs read sources')
        if not isinstance(ids, list): ids = []
        c.need(signal.get('time_role') in {'recent', 'background', 'unknown'}, key + ': time role required')
        if signal.get('time_role') == 'recent':
            c.need(all(sources.get(sid, {}).get('published_at') for sid in ids), key + ': unknown date cannot establish recency')
    report = manifest.get('report') or {}
    if required and report:
        c.need(report.get('hotspot_verification') == hot.get('status'), 'report hotspot state differs from scan')
        c.need(report.get('academic_fulltext') == fulltext, 'report academic fulltext state differs from scan')
        if hot.get('status') != 'complete' or fulltext != 'complete':
            c.need(report.get('status') == 'draft', 'limited hotspot/fulltext verification requires draft report')
    return hot


def check_topics(c, topics, hot, final_ids):
    signals = {s['hotspot_id'] for s in (hot or {}).get('signals', [])}
    final_cards = set()
    for tid, topic in topics.items():
        qualification = topic.get('qualification') or {}
        c.need(qualification.get('status') in {'eligible', 'ineligible'}, tid + ': explicit eligibility required')
        c.need(nonempty(qualification.get('reason')), tid + ': qualification needs reason')
        if qualification.get('status') != 'eligible':
            c.need(tid not in final_ids, tid + ': ineligible topic cannot enter output')
            continue
        for key in QUALIFICATION:
            c.need(qualification.get('checks', {}).get(key) is True, tid + ': unreviewed qualification ' + key)
        scope = topic.get('scope')
        c.need(isinstance(scope, dict), tid + ': scope must identify real region and population')
        if isinstance(scope, dict):
            for key in SCOPE:
                c.need(nonempty(scope.get(key)), tid + ': scope missing ' + key)
            c.need(scope.get('basis_type') in {'user', 'local-evidence', 'verified-public', 'anonymized'}, tid + ': scope provenance required')
        check_closure(c, tid, topic, tid in final_ids)
        problem = topic.get('problem_basis') or {}
        c.need(problem.get('type') in {'reported', 'policy-risk', 'user-stated', 'hypothesis'}, tid + ': classify actual problem evidence')
        c.need(nonempty(problem.get('basis')), tid + ': problem basis missing')
        ai = topic.get('ai_boundary') or {}
        c.need(ai.get('status') in {'not-ai', 'specific-governance-problem'}, tid + ': generic AI-human impact is out of scope')
        c.need(nonempty(ai.get('reason')), tid + ': AI boundary needs a substantive explanation')
        if ai.get('status') == 'specific-governance-problem':
            c.need(nonempty(ai.get('function')), tid + ': identify the actual AI task')
        ids = topic.get('hotspot_ids', [])
        c.need(isinstance(ids, list) and all(key in signals for key in ids), tid + ': unknown hotspot linkage')
        if not ids:
            c.need(nonempty(topic.get('hotspot_limitation')), tid + ': explain absent hotspot linkage')
        theory = topic.get('theory') or {}
        primary, secondary = theory.get('primary'), theory.get('secondary')
        c.need(nonempty(primary), tid + ': one primary theory required')
        c.need(secondary is None or (nonempty(secondary) and secondary != primary), tid + ': at most one distinct secondary theory')
        if secondary:
            c.need(nonempty(theory.get('division')), tid + ': explain complementary theory roles')
        for key in (primary, secondary):
            if not key:
                continue
            try:
                c.need(theory_metadata(key).get('status') == 'verified', tid + ': unverified theory card')
            except (ValueError, OSError):
                c.need(False, tid + ': missing/invalid theory card ' + str(key))
        c.need(nonempty(theory.get('fit')), tid + ': theoretical fit must be explained')
        if tid in final_ids:
            final_cards.update(key for key in (primary, secondary) if key)
            for key in DESIGN:
                c.need(nonempty(theory.get(key)), tid + ': final theory design missing ' + key)
        decision = topic.get('decision') or {}
        for key in DECISION:
            c.need(nonempty(decision.get(key)), tid + ': missing decision ' + key)
    c.need(len(final_cards) <= 10, 'final design cannot use more than ten distinct theory cards')


def external_fulltexts(hot, web):
    sources = list((hot or {}).get('sources', []))
    for result in (web or {}).get('results', []):
        for search in result.get('searches', []):
            sources.extend(search.get('sources', []))
    def identity(source):
        doi = source.get('doi')
        if doi:
            return re.sub(r'^https?://(?:dx\.)?doi\.org/', '', str(doi).strip(), flags=re.I).lower()
        return source.get('url')
    return {identity(s) for s in sources
            if s.get('source_type') == 'academic' and s.get('fulltext_opened') is True}
