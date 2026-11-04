#!/usr/bin/env python3
"""Initialize a unique run or check deterministic provenance and citation links.

No semantic, novelty, access-rights or writing-quality correctness is inferred.
Python 3.9+, standard library only. check exits 1 on errors, 0 otherwise.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

READING = {'已读完','只读到一部分','未能读取','未读取'}
STATES = {'pending','complete','limited','failed','stale'}
GAPS = {'local_question','candidate','covered','unverified'}
ACCESS = {'metadata','abstract','fulltext'}
WEB_RESULTS = {'confirmed','conditional','not_feasible','unavailable'}
WEB_ACCESS = {'landing-page','metadata','abstract','partial','document','fulltext'}
MISSING = {'原文未说明','当前未读到','识别不清','不适用'}
POLICY_VERSION = '2.11.3'
SOURCE_FIELDS = ('title','authors','year','type','publication','volume','issue',
                 'pages_or_article','doi','url','accessed_at','version_note',
                 'publisher','place','edition','language')


def source_digest(source):
    data = {key:source.get(key) for key in SOURCE_FIELDS}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def reference_entry(source, style='basic'):
    """Readable basic entry, or a target-style entry explicitly tied to metadata.
    Basic output is not claimed to implement every clause of a national standard.
    """
    if style != 'basic':
        custom = source.get('formatted_reference',{})
        if custom.get('style') != style or custom.get('metadata_sha256') != source_digest(source):
            raise ValueError(f"{source.get('source_id')}: target-style reference is absent or metadata changed")
        if not custom.get('text'): raise ValueError('empty formatted reference')
        return custom['text']
    authors = ', '.join(source.get('authors') or [])
    year = source.get('year')
    publication = source.get('publication') or ''
    details = ', '.join(str(v) for v in [publication,year] if v is not None and str(v))
    volume,issue,pages = source.get('volume'),source.get('issue'),source.get('pages_or_article')
    if volume: details += ', '+str(volume)
    if issue: details += '('+str(issue)+')'
    if pages: details += ': '+str(pages)
    parts = [v for v in [authors,source.get('title'),details] if v]
    entry = '. '.join(parts)+'.'
    if source.get('doi'): entry += ' DOI: '+source['doi']+'.'
    if source.get('url'): entry += ' '+source['url']
    if source.get('accessed_at'): entry += ' [访问日期 '+source['accessed_at']+']'
    return entry


def markdown_module():
    spec=importlib.util.spec_from_file_location('_topic_markdown',Path(__file__).with_name('markdown_utils.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def language_module():
    spec=importlib.util.spec_from_file_location('_topic_language',Path(__file__).with_name('review_language.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def design_module():
    spec=importlib.util.spec_from_file_location('_topic_design',Path(__file__).with_name('research_design.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def numeric_citation_order(text, markdown=False):
    """First occurrence of each citation, preserving order inside grouped cites."""
    if markdown:
        visible=[];in_code=False
        markdown=markdown_module()
        for line in re.sub(r'<!--.*?-->','',text,flags=re.S).splitlines():
            if line.strip().startswith('```'):in_code=not in_code;continue
            if not in_code:
                visible.append(''.join(value if kind not in {'link','code'} else ' ' for kind,value,_ in markdown.inline_tokens(line)))
        text='\n'.join(visible)
    labels = []
    for match in re.finditer(r'\[(\d+(?:\s*[-,，]\s*\d+)*)\]', text):
        for piece in re.split('[,，]',match[1]):
            bounds = [int(v) for v in piece.split('-')]
            if bounds[0] > bounds[-1] or bounds[-1]-bounds[0] >= 1000:
                raise ValueError('invalid citation range')
            labels.extend(str(n) for n in range(bounds[0],bounds[-1]+1))
    return list(dict.fromkeys(labels))


def numeric_labels(text, markdown=False):
    return set(numeric_citation_order(text, markdown))


def write_json(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def init(parent: Path, mode: str, source_dirs=None) -> Path:
    if not source_dirs:
        raise ValueError('请指定需要读取的论文文件夹绝对路径。')
    allowed_roots = []
    for raw in source_dirs:
        source_dir = Path(raw).expanduser()
        if not source_dir.is_absolute():
            raise ValueError('论文文件夹必须使用绝对路径: '+str(raw))
        source_dir = source_dir.resolve()
        if not source_dir.is_dir():
            raise ValueError('指定的论文文件夹不存在或不是文件夹: '+str(source_dir))
        value = str(source_dir)
        if value not in allowed_roots:
            allowed_roots.append(value)
    source_parents={str(Path(value).parent) for value in allowed_roots}
    if len(source_parents)!=1:
        raise ValueError('多个论文文件夹不在同一父目录；请确定一个论文文件夹范围。')
    output_root=Path(next(iter(source_parents)))
    requested_parent=Path(parent).expanduser()
    if not requested_parent.is_absolute():
        raise ValueError('输出父目录必须使用绝对路径，并且是论文文件夹的上一级。')
    if requested_parent.resolve()!=output_root:
        raise ValueError('输出父目录必须是论文文件夹的上一级，使运行目录与论文文件夹平级。')
    parent=output_root
    now = datetime.now().astimezone()
    root = Path(tempfile.mkdtemp(prefix=now.strftime('%Y%m%d-%H%M%S-'), dir=parent))
    (root/'cards').mkdir(); (root/'extraction').mkdir()
    (root/'research-direction.md').write_text('# 原始委托与后续变更\n\n尚未登记。保留用户原话，不推断未知条件。\n', encoding='utf-8')
    write_json(root/'manifest.json', {
        'schema_version':5,'policy_version':POLICY_VERSION,
        'run_id':str(uuid.uuid4()),'created_at':now.isoformat(),
        'mode':mode,'constraints':{'direction_original':None,'exclusions':[],
            'degree':None,'deadline':None,'resources':None,'changes':[],
            'source_scope':'provided-only','allowed_input_roots':allowed_roots,
            'output_scope':'source-parent','output_root':str(output_root),
            'literature_review_policy':'required','literature_review_waiver':None,
            'external_feasibility_scope':'final-shortlist-only',
            'external_hotspot_scope':'shared-preselection',
            'formal_trigger':None},
        'rules':[],'capabilities':{},'inputs':[],'artifacts':[], 'report':None})
    write_json(root/'references.json', {'version':1,'sources':[],'evidence':[]})
    return root


def source_dependencies(obj):
    """Directly consumed sources only; stage dependencies carry transitive use."""
    found=set()
    if isinstance(obj,dict):
        for key,value in obj.items():
            if key=='source_id' and isinstance(value,str):found.add(value)
            elif key in {'source_ids','closest_sources','recommended_source_ids'} and isinstance(value,list):found.update(value)
            else:found.update(source_dependencies(value))
    elif isinstance(obj,list):
        for value in obj:found.update(source_dependencies(value))
    return found


def dependency_digest(source):
    # Access dates / target-style punctuation affect the bibliography, not a
    # previous close reading. Canonical report checking still catches that drift.
    data={k:v for k,v in source.items() if k not in {'accessed_at','formatted_reference'}}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def context_digest(manifest,artifact):
    if artifact['path'] not in {'hotspots.json','topics.json','feasibility.json','web-feasibility.json',(manifest.get('report') or {}).get('markdown')}:return None
    return hashlib.sha256(json.dumps({'constraints':manifest['constraints'],'rules':manifest.get('rules',[])},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def consumed_sources(checker,manifest,artifact):
    path=artifact['path']
    if path=='references.json':return set()
    report=manifest.get('report') or {}
    obj=checker.load(path) if path.endswith('.json') else report if path==report.get('markdown') else {}
    return source_dependencies(obj)


def atomic_json(path,obj):
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.'+path.name+'-',delete=False) as f:
        tmp=Path(f.name)
        try:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
        except BaseException:tmp.unlink();raise
    try:os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()


def stamp(root,upgrade=False):
    """Record integrity after coordinator review; never bless a same-version edit."""
    c=Checker(root);m=c.load('manifest.json')
    if m.get('schema_version')!=5 or m.get('policy_version')!=POLICY_VERSION:
        raise ValueError('旧运行须在新目录复用仍合法的阅读成果并补齐 2.11.3 检查；stamp/--upgrade 不会自动升级或批准旧运行')
    sources={s['source_id']:s for s in c.load('references.json')['sources']}
    arts={a['artifact_id']:a for a in m['artifacts']};changed=set();stale=set()
    for aid,a in arts.items():
        if a.get('status') not in {'complete','limited','stale'}:continue
        p=c.path(a['path']);sha=hashlib.sha256(p.read_bytes()).hexdigest()
        if p.suffix=='.json' and c.load(a['path']).get('version')!=a['version']:raise ValueError(aid+': synchronize content version first')
        bumped=a.get('fingerprint_version') is not None and a['version']>a['fingerprint_version']
        if a.get('sha256') and sha!=a['sha256'] and not bumped:raise ValueError(aid+': content changed; review and increase version before stamp')
        expected={sid:dependency_digest(sources[sid]) for sid in consumed_sources(c,m,a)}
        if 'source_dependencies' in a and a['source_dependencies']!=expected and not bumped:
            stale.add(aid)  # Keep old fingerprints until this particular stage is reviewed.
        else:a['source_dependencies']=expected
        context=context_digest(m,a)
        if a.get('context_sha256') is not None and a['context_sha256']!=context and not bumped:stale.add(aid)
        else:a['context_sha256']=context
        theories=design_module().used_theories(c.root,a['path'])
        if 'theory_dependencies' in a and a['theory_dependencies']!=theories and not bumped:stale.add(aid)
        else:a['theory_dependencies']=theories
        if a.get('sha256')!=sha:changed.add(aid)
        a['sha256']=sha;a['fingerprint_version']=a['version']
        if any(dep not in arts or arts[dep]['version']!=v for dep,v in a.get('depends_on',{}).items()):stale.add(aid)
    while True:
        more={aid for aid,a in arts.items() if set(a.get('depends_on',{}))&stale}
        if more<=stale:break
        stale|=more
    for aid in stale:
        arts[aid]['status']='stale';arts[aid]['reason']='Consumed source or stage changed; review affected content only.'
    atomic_json(c.path('manifest.json'),m)
    return {'recorded':sorted(changed),'stale':sorted(stale),'scope':'integrity only; not semantic approval'}


class Checker:
    def __init__(self, root):
        self.root = root.resolve(); self.errors = []; self.warnings = []

    def need(self, condition, message):
        if not condition: self.errors.append(message)

    def path(self, value):
        if not isinstance(value, str) or not value:
            raise ValueError('missing artifact path')
        p = (self.root/value).resolve()
        if Path(value).is_absolute() or self.root not in p.parents:
            raise ValueError(f'artifact path escapes run: {value}')
        return p

    def load(self, value):
        return json.loads(self.path(value).read_text(encoding='utf-8'))

    def indexed(self, items, key):
        self.need(isinstance(items,list), f'{key}: expected array')
        result = {}
        for obj in items:
            ident = obj.get(key)
            self.need(isinstance(ident,str) and bool(ident), f'missing {key}')
            self.need(ident not in result, f'duplicate {key}: {ident}')
            result[ident] = obj
        return result

    def pages(self, values, total, label):
        self.need(isinstance(values,list), label+': pages must be an array')
        self.need(all(type(p) is int and 1 <= p <= total for p in values), label+': page out of range')
        self.need(len(set(values)) == len(values), label+': duplicate pages')

    def require_keys(self, obj, keys, label):
        for key in keys:
            self.need(key in obj, f'{label}: missing {key}')

    def preflight(self):
        """Reuse the design gates before prose; never read input PDFs or stamp files."""
        manifest = self.load('manifest.json')
        self.need(manifest.get('policy_version') == POLICY_VERSION,
                  'preflight requires current policy_version ' + POLICY_VERSION)
        topics = self.indexed(self.load('topics.json').get('topics', []), 'topic_id')
        feasibility = self.load('feasibility.json')
        selection = feasibility.get('selection') or {}
        provisional = selection.get('selected_topic_ids', [])
        web = self.load('web-feasibility.json') if provisional else None
        # This is a projection for the gate, not a second report or an approval.
        report = dict(manifest.get('report') or {})
        report.update(status=report.get('status', 'draft'),
                      topic_ids=(web or {}).get('final_topic_ids', []),
                      feasibility_verification=(web or {}).get('status', 'not-applicable'))
        local_ids={sample.get('source',{}).get('ref')
                   for result in (web or {}).get('results',[])
                   for check in result.get('data_checks',[]) for sample in check.get('samples',[])
                   if sample.get('source',{}).get('kind')=='local'}
        if local_ids:
            evidence=list(self.load('references.json').get('evidence',[]))
            for item in manifest.get('inputs',[]):
                if item.get('source_id') in local_ids and item.get('card_path'):
                    evidence.extend(self.load(item['card_path']).get('evidence',[]))
            self._checked_evidence=self.indexed(evidence,'evidence_id')
        design = design_module()
        hot = design.check_hotspots(self, manifest, True)
        design.check_topics(self, topics, hot, report['topic_ids'])
        formed = design.time_value(self, self.load('topics.json').get('formed_at'), 'topics formed_at')
        checked = design.time_value(self, (hot or {}).get('checked_at'), 'hotspots checked_at')
        if formed and checked:
            self.need(formed >= checked, 'candidates must be formed after shared hotspot scan')
        self.check_web_feasibility(manifest.get('mode'), topics, feasibility, report)
        self.check_topic_selection(topics, feasibility, report, web)
        self.need(len(design.external_fulltexts(hot, web)) <= 4,
                  'all online stages share a four-academic-fulltext limit')
        return {'errors': self.errors, 'warnings': self.warnings,
                'scope': 'design declarations and evidence coverage only; substantive review is still required'}

    def check(self):
        m = self.load('manifest.json')
        self.need(m.get('schema_version')==5, 'current policy requires manifest schema 5; reuse legacy readings in a new run, not a version-only upgrade')
        modern=m.get('schema_version') in {3,4,5}
        self.need(m.get('policy_version')==POLICY_VERSION,
                  'manifest policy_version is missing or outdated; start or explicitly migrate the run under '+POLICY_VERSION)
        self.need(m.get('mode') in {'topic','full','read','compare','evaluate','explore'}, 'invalid mode')
        self.need(bool(m.get('run_id')), 'missing run_id')
        self.need(datetime.fromisoformat(m['created_at']).utcoffset() is not None, 'created_at requires timezone')
        self.need(isinstance(m.get('constraints'),dict) and 'direction_original' in m['constraints'], 'missing original constraints')
        constraints=m.get('constraints') if isinstance(m.get('constraints'),dict) else {}
        self.need(constraints.get('source_scope')=='provided-only',
                  'constraints.source_scope must be provided-only')
        self.need(constraints.get('external_feasibility_scope')=='final-shortlist-only',
                  'constraints.external_feasibility_scope must be final-shortlist-only')
        self.need(constraints.get('external_hotspot_scope')=='shared-preselection',
                  'constraints.external_hotspot_scope must be shared-preselection')
        self.need(constraints.get('output_scope')=='source-parent',
                  'constraints.output_scope must be source-parent')
        review_policy=constraints.get('literature_review_policy')
        review_waiver=constraints.get('literature_review_waiver')
        self.need(review_policy in {'required','waived'},
                  'constraints.literature_review_policy must be required or waived')
        if review_policy=='required':
            self.need(review_waiver is None or review_waiver=='',
                      'required literature review policy must not carry a waiver')
        if review_policy=='waived':
            self.need(isinstance(review_waiver,str) and bool(review_waiver.strip()),
                      'waived literature review policy requires the user\'s exact request')
        allowed_roots = constraints.get('allowed_input_roots')
        self.need(isinstance(allowed_roots,list) and bool(allowed_roots),
                  'constraints.allowed_input_roots must contain at least one user-specified paper folder')
        resolved_roots=[]
        if isinstance(allowed_roots,list):
            for value in allowed_roots:
                root = Path(value).expanduser() if isinstance(value,str) else Path('')
                self.need(isinstance(value,str) and root.is_absolute(),
                          'allowed paper folders must be absolute paths')
                if isinstance(value,str) and root.is_absolute():
                    resolved=root.resolve()
                    self.need(resolved.is_dir(),
                              'allowed paper folder does not exist or is not a directory: '+str(resolved))
                    if resolved.is_dir():resolved_roots.append(resolved)
        output_root_value=constraints.get('output_root')
        output_root=Path(output_root_value).expanduser() if isinstance(output_root_value,str) else Path('')
        self.need(isinstance(output_root_value,str) and output_root.is_absolute(),
                  'constraints.output_root must be an absolute path')
        if isinstance(output_root_value,str) and output_root.is_absolute():
            output_root=output_root.resolve()
            self.need(output_root.is_dir(),'constraints.output_root must be an existing directory')
            self.need(self.root.parent==output_root,
                      'run directory must be directly inside constraints.output_root')
            source_parents={root.parent for root in resolved_roots}
            self.need(len(source_parents)==1 and source_parents=={output_root},
                      'output_root must be the common direct parent of all paper folders')
        if m.get('mode')=='full':
            self.need(isinstance(constraints.get('formal_trigger'),str) and bool(constraints['formal_trigger'].strip()),
                      'full mode requires an explicit user formal-deliverable trigger')
            self.need(review_policy=='required',
                      'full mode cannot waive the literature review; use topic mode for an explicit no-review request')
        direction_path=self.path('research-direction.md')
        self.need(direction_path.is_file(), 'missing original direction record')
        if direction_path.is_file() and m.get('mode') in {'topic','full','evaluate'}:
            direction_text=direction_path.read_text(encoding='utf-8')
            self.need('尚未登记' not in direction_text and len(direction_text.strip())>20,
                      'original request was not recorded; cannot infer scope or delivery format')
        inputs = self.indexed(m['inputs'],'input_id')
        arts = self.indexed(m['artifacts'],'artifact_id')
        refs = self.load('references.json')
        sources = self.indexed(refs['sources'],'source_id')
        input_sources={item.get('source_id') for item in inputs.values()}
        self.need(set(sources)<=input_sources,
                  'provided-only source scope contains a source outside the supplied inputs')
        for pid,item in inputs.items():
            raw_path=item.get('path')
            path=Path(raw_path).expanduser() if isinstance(raw_path,str) else Path('')
            self.need(isinstance(raw_path,str) and path.is_absolute(),
                      f'{pid}: source path must be absolute')
            if isinstance(raw_path,str) and path.is_absolute():
                resolved=path.resolve()
                self.need(any(resolved==root or root in resolved.parents for root in resolved_roots),
                          f'{pid}: source file is outside user-specified paper folders')
        for sid, source in sources.items():
            self.need(source.get('access_level') in ACCESS, f'{sid}: invalid access_level')
            self.need(isinstance(source.get('verified'),bool), f'{sid}: verified must be boolean')
            self.need(bool(source.get('title')), f'{sid}: missing title')
            self.need(isinstance(source.get('authors'),list), f'{sid}: authors must be array')
            self.need(bool(source.get('required_fields')), f'{sid}: missing required_fields')
            self.need(isinstance(source.get('missing_fields'),list), f'{sid}: missing_fields must be array')
            for key in source.get('required_fields',[]):
                self.need(bool(source.get(key)) or key in source.get('missing_fields',[]), f'{sid}: undeclared missing field {key}')
        # Warn about canonical duplicate DOI, do not merge different versions blindly.
        dois = {}
        for sid,s in sources.items():
            doi = re.sub(r'^https?://(?:dx\.)?doi.org/', '', s.get('doi') or '', flags=re.I).lower()
            if doi and doi in dois: self.warnings.append(f'duplicate DOI: {dois[doi]}, {sid}; verify versions')
            if doi: dois[doi] = sid
        for aid,a in arts.items():
            self.need(type(a.get('version')) is int and a['version'] > 0, f'{aid}: invalid version')
            self.need(a.get('status') in STATES, f'{aid}: invalid status')
            if a.get('status') in {'complete','limited'}:
                self.need(self.path(a.get('path')).is_file(), f'{aid}: missing artifact')
                if a['path'].endswith('.json'):
                    self.need(self.load(a['path']).get('version')==a['version'], 'artifact content version missing/mismatch: '+a['path'])
                if modern:
                    self.need(a.get('sha256')==hashlib.sha256(self.path(a['path']).read_bytes()).hexdigest(), f'{aid}: artifact content changed or unstamped')
                    self.need(a.get('fingerprint_version')==a['version'], f'{aid}: fingerprint version mismatch')
                    consumed=consumed_sources(self,m,a)
                    self.need(consumed<=set(sources),f'{aid}: unknown consumed source')
                    expected={sid:dependency_digest(sources[sid]) for sid in consumed if sid in sources}
                    self.need(a.get('source_dependencies')==expected, f'{aid}: consumed source changed or source scope missing')
                    self.need(a.get('context_sha256')==context_digest(m,a),f'{aid}: task constraints/rules changed')
                    self.need(a.get('theory_dependencies')==design_module().used_theories(self.root,a['path']),
                              f'{aid}: used theory cards changed or unstamped')
            if a.get('status') == 'stale': self.errors.append(f'{aid}: stale downstream artifact')
            if a.get('status') in {'limited','failed'}: self.need(bool(a.get('reason')), f'{aid}: missing reason')
            for dep,version in a.get('depends_on',{}).items():
                self.need(dep != aid and dep in arts, f'{aid}: unknown/self dependency {dep}')
                if dep in arts:
                    self.need(arts[dep]['version'] == version, f'{aid}: outdated dependency {dep}')
                    self.need(arts[dep]['status'] in {'complete','limited'}, f'{aid}: unusable dependency {dep}')
        visited = set()
        def cycle(aid, stack):
            if aid in stack: self.errors.append('dependency cycle: '+' -> '.join(stack+[aid])); return
            if aid in visited: return
            for dep in arts[aid].get('depends_on',{}):
                if dep in arts and dep != aid: cycle(dep,stack+[aid])
            visited.add(aid)
        for aid in arts: cycle(aid,[])
        by_path = {}
        for aid,a in arts.items():
            self.need(a.get('path') not in by_path, f'duplicate artifact path: {a.get("path")}')
            by_path[a.get('path')] = aid
        # Required dependency edges are derived from the actual mode and files.
        # An empty depends_on can no longer bypass stale-version detection.
        def require_dependency(path, upstream):
            aid = by_path.get(path)
            self.need(aid is not None, 'unregistered artifact: '+path)
            if aid is None: return
            for previous in upstream:
                dep = by_path.get(previous)
                self.need(dep is not None, 'unregistered upstream artifact: '+previous)
                if dep is not None:
                    self.need(dep in arts[aid].get('depends_on',{}), f'{aid}: missing required dependency {dep}')
        require_dependency('references.json',[])
        self.need(not (self.root/'search-log.json').exists(),
                  'search-log.json is forbidden: this skill may only use files in user-specified paper folders')
        card_paths = [p['card_path'] for p in inputs.values()]
        for path in card_paths: require_dependency(path,[] if modern else ['references.json'])
        if (self.root/'synthesis.json').exists():
            require_dependency('synthesis.json',card_paths+([] if modern else ['references.json']))
        if (self.root/'hotspots.json').exists():
            require_dependency('hotspots.json',[])
            hot_art=arts.get(by_path.get('hotspots.json'),{})
            forbidden={by_path.get(p) for p in ['topics.json','feasibility.json','web-feasibility.json',(m.get('report') or {}).get('markdown')]}
            self.need(not set(hot_art.get('depends_on',{})) & forbidden,
                      'hotspots cannot depend on downstream candidates or report')
        if (self.root/'topics.json').exists():
            previous = [] if modern else ['references.json']
            previous += ['synthesis.json'] if (self.root/'synthesis.json').exists() else card_paths
            previous += ['hotspots.json'] if (self.root/'hotspots.json').exists() else []
            require_dependency('topics.json',previous)
        if (self.root/'feasibility.json').exists():
            require_dependency('feasibility.json',['topics.json']+([] if modern else ['references.json']))
        if (self.root/'web-feasibility.json').exists():
            require_dependency('web-feasibility.json',['feasibility.json'])
        evidence = list(refs.get('evidence',[])); cards = {}
        for pid,p in inputs.items():
            sid = p.get('source_id')
            self.need(sid in sources, f'{pid}: unknown source_id')
            n = p.get('total_pages')
            self.need(type(n) is int and n > 0, f'{pid}: invalid total_pages')
            pdf = Path(p['path']).expanduser()
            self.need(pdf.is_file(), f'{pid}: missing source file')
            if pdf.is_file(): self.need(hashlib.sha256(pdf.read_bytes()).hexdigest() == p['sha256'], f'{pid}: source checksum mismatch')
            if p.get('duplicate_of'):
                other = inputs.get(p['duplicate_of'])
                self.need(other is not None and other['sha256']==p['sha256'] and other is not p, f'{pid}: invalid duplicate_of')
            ex = self.load(p['extraction_path'])
            self.need(ex.get('sha256') == p['sha256'] and ex.get('total_pages') == n, f'{pid}: extraction identity mismatch')
            self.need([v['page'] for v in ex.get('pages',[])] == list(range(1,n+1)), f'{pid}: extraction page coverage mismatch')
            for page in ex.get('pages',[]):
                self.need(page.get('status') in {'text_ready','empty','error','review_required','ocr_review_required'}, f'{pid}: invalid extraction page state')
            card = self.load(p['card_path']); cards[pid] = card
            self.need(card.get('input_id')==pid and card.get('source_id')==sid, f'{pid}: card identity mismatch')
            ca = [a for a in arts.values() if a.get('path')==p['card_path']]
            self.need(len(ca)==1 and ca[0]['version']==card.get('version'), f'{pid}: card artifact/version mismatch')
            state,read = card.get('reading_state'),card.get('read_pages',[])
            self.need(state in READING, f'{pid}: invalid reading_state')
            self.pages(read,n,pid)
            unread = [x for r in card.get('unread',[]) for x in r['pages']]
            self.pages(unread,n,pid+' unread')
            self.need(not set(read)&set(unread) and set(read+unread)==set(range(1,n+1)), f'{pid}: unaccounted or overlapping read/unread pages')
            self.need(all(r.get('reason') for r in card.get('unread',[])), f'{pid}: unread reason missing')
            self.need(bool(card.get('coverage_note')), f'{pid}: missing actual coverage note')
            partial = card.get('partial_pages',[])
            self.pages(partial,n,pid+' partial')
            self.need(set(partial)<=set(read), f'{pid}: partial page was not inspected')
            if state=='已读完': self.need(set(read)==set(range(1,n+1)) and not partial, f'{pid}: full reading lacks coverage')
            if state=='只读到一部分': self.need(bool(read) and (len(read)<n or bool(partial)), f'{pid}: inconsistent partial reading')
            if state in {'未能读取','未读取'}: self.need(not read, f'{pid}: unread state has read pages')
            for e in card.get('evidence',[]):
                if e.get('source_id') == sid:
                    self.need(set(e.get('pages',[]))<=set(read), f'{pid}: evidence refers to unread pages')
                evidence.append(e)
            self.need(all(key in card.get('fields',{}) for key in ['purpose','design','results']), f'{pid}: missing core card fields')
            for key,field in card.get('fields',{}).items():
                if field.get('value') is None:
                    self.need(field.get('missing_reason') in MISSING, f'{pid}/{key}: invalid missing_reason')
        source_totals = {}
        for p in inputs.values():
            source_totals.setdefault(p['source_id'],[]).append(p['total_pages'])
        ev = self.indexed(evidence,'evidence_id')
        self._checked_evidence = ev
        for eid,e in ev.items():
            sid = e.get('source_id')
            self.need(sid in sources, f'{eid}: unknown evidence source')
            self.need(bool(e.get('claim')) and bool(e.get('observed')), f'{eid}: missing claim/observed content')
            self.need(bool(e.get('locator')) or bool(e.get('pages')), f'{eid}: missing locator')
            pages = e.get('pages',[])
            total = min(source_totals[sid]) if sid in source_totals else sources.get(sid,{}).get('total_pages')
            self.need(isinstance(pages,list) and all(type(p) is int and p > 0 for p in pages), f'{eid}: invalid evidence page numbers')
            self.need(len(set(pages))==len(pages), f'{eid}: duplicate evidence pages')
            if pages:
                self.need(type(total) is int and total > 0, f'{eid}: PDF evidence requires known total_pages')
                if type(total) is int: self.pages(pages,total,eid)
            read_for_source = set(p for pid,c in cards.items() if c['source_id']==sid for p in c['read_pages'])
            if sid in source_totals:
                self.need(set(pages)<=read_for_source, f'{eid}: evidence refers to unread pages')
            self.need(e.get('attribution') in {'author','analyst'}, f'{eid}: invalid attribution')
            self.need(e.get('access_level') in ACCESS, f'{eid}: invalid evidence access')
            if sid in sources:
                order = {'metadata':0,'abstract':1,'fulltext':2}
                self.need(order.get(e.get('access_level'),9)<=order[sources[sid]['access_level']], f'{eid}: access depth exceeds source')
        for pid,c in cards.items():
            for key,f in c.get('fields',{}).items():
                self.need(all(e in ev for e in f.get('evidence_ids',[])), f'{pid}/{key}: dangling evidence')
                if f.get('value') is not None: self.need(bool(f.get('evidence_ids')), f'{pid}/{key}: claim lacks evidence')
        searches = {}
        if (self.root/'synthesis.json').exists():
            syn = self.load('synthesis.json')
            self.require_keys(syn,['groups','matrix','limitations'],'synthesis')
            self.need(isinstance(syn.get('groups'),list) and isinstance(syn.get('matrix'),list) and isinstance(syn.get('limitations'),(str,list)), 'synthesis: invalid groups/matrix/limitations')
            for key in ['purpose_coverage','conclusion_coverage']:
                items = self.indexed(syn[key],'input_id')
                self.need(set(items)==set(inputs), key+': incomplete input coverage')
                for pid,item in items.items():
                    self.need(item.get('status') in {'included','excluded','unknown'}, key+': invalid coverage status')
                    if item.get('status')!='included': self.need(bool(item.get('reason')), key+': missing reason')
        topics = {}
        if (self.root/'topics.json').exists():
            obj = self.load('topics.json'); topics = self.indexed(obj['topics'],'topic_id')
            if not topics: self.need(bool(obj.get('reason')), 'zero topics requires reason')
            for tid,t in topics.items():
                if (t.get('qualification') or {}).get('status')=='ineligible':
                    self.need(bool(t.get('title')) and bool(t.get('question')), f'{tid}: rejected candidate needs its title and problem')
                    continue
                self.need(t.get('gap_state') in GAPS, f'{tid}: invalid gap_state')
                for key in ['title','question','contribution_type','planned_contribution','scope']:
                    self.need(bool(t.get(key)), f'{tid}: missing {key}')
                for key,pool in [('source_ids',sources),('evidence_ids',ev),('search_ids',searches),('closest_sources',sources)]:
                    self.need(all(x in pool for x in t.get(key,[])), f'{tid}: dangling {key}')
                if t.get('gap_state')=='bounded_support':
                    self.errors.append(f'{tid}: bounded_support is unavailable under strict folder-only scope')
        feasibility = None
        if (self.root/'feasibility.json').exists():
            feasibility = self.load('feasibility.json')
            assessments = self.indexed(feasibility['assessments'],'topic_id')
            self.need(set(assessments)==set(topics), 'feasibility/topic coverage mismatch')
            for tid,a in assessments.items():
                self.need(a.get('direction') in {'符合','部分符合','不符合','暂无法判断'}, f'{tid}: invalid direction')
                self.need(a.get('verdict') in {'建议做','调整后再做','不建议做','暂无法判断'}, f'{tid}: invalid verdict')
                self.need(bool(a.get('reason')) and bool(a.get('direction_reason')), f'{tid}: missing assessment reason')
                self.require_keys(a,['resources','design','conditions','unresolved'],tid)
                self.need(bool(a.get('design')), f'{tid}: empty research design')
                self.need(isinstance(a.get('conditions'),list) and isinstance(a.get('unresolved'),list), f'{tid}: conditions/unresolved must be arrays')
                if not m['constraints'].get('direction_original'):
                    self.need(a.get('direction')=='暂无法判断', f'{tid}: direction unknown but verdict certain')
                for r in a.get('resources',[]):
                    self.need(r.get('access_level') in {'entry','documentation','sample','acquired'}, f'{tid}: invalid resource access')
                    for key in ['location','checked_at','fit','limitations']:
                        self.need(bool(r.get(key)), f'{tid}: resource missing {key}')
                    if r.get('checked_at'):
                        datetime.fromisoformat(r['checked_at'])
        report = m.get('report')
        design=design_module()
        selection_report=bool(report and (m.get('mode') in {'topic','full','evaluate'} or report.get('topic_ids')))
        hot=design.check_hotspots(self,m,selection_report)
        if selection_report:
            self.need(isinstance((feasibility or {}).get('selection'),dict),
                      'final selection requires an explicit eligible set and ranking, including zero topics')
            design.check_topics(self,topics,hot,(report or {}).get('topic_ids',[]))
            if hot and (self.root/'topics.json').exists():
                formed=design.time_value(self,self.load('topics.json').get('formed_at'),'topics formed_at')
                checked=design.time_value(self,hot.get('checked_at'),'hotspots checked_at')
                if formed and checked:self.need(formed>=checked,'candidates must be formed after shared hotspot scan')
        web = self.check_web_feasibility(m.get('mode'),topics,feasibility,report)
        self.need(len(design.external_fulltexts(hot,web))<=4,
                  'all online stages share a four-academic-fulltext limit')
        self.check_topic_selection(topics, feasibility, report, web)
        if not report:
            if m['mode'] in {'topic','full','evaluate'}:self.errors.append('report not registered; run is unfinished')
            else:self.warnings.append('stage records only; no report requested/registered, not a formal report acceptance')
        else:
            final_upstream = [] if modern else ['references.json']
            for path in ['synthesis.json','hotspots.json','topics.json','feasibility.json','web-feasibility.json']:
                if (self.root/path).exists(): final_upstream.append(path)
            if not any((self.root/p).exists() for p in ['synthesis.json','topics.json','feasibility.json']): final_upstream += card_paths
            require_dependency(report['markdown'],final_upstream)
            expected = []
            if m['mode'] in {'full','compare'}: expected.append('synthesis.json')
            if selection_report: expected.extend(['topics.json','feasibility.json'])
            if selection_report:expected.append('hotspots.json')
            provisional=(feasibility or {}).get('selection',{}).get('selected_topic_ids',[])
            if selection_report and provisional:expected.append('web-feasibility.json')
            expected.append(report['markdown'])
            for path in expected:
                self.need(self.path(path).is_file(), 'mode requires artifact: '+path)
                matches = [a for a in arts.values() if a.get('path')==path]
                self.need(len(matches)==1 and matches[0]['status'] in {'complete','limited'}, 'artifact not registered/usable: '+path)
            self.check_literature_policy(m.get('mode'),constraints,report)
            self.check_report(report,sources)
            self.check_rules(m,report,sources)
            if report.get('status')=='formal-ready':
                self.need(report.get('review',{}).get('semantic')=='passed', 'formal-ready requires actual semantic review')
                self.need(all(a['status'] in {'complete','limited'} for a in arts.values()), 'formal-ready has unfinished artifacts')
        return {'errors':self.errors,'warnings':self.warnings,
                'scope':'deterministic structure/provenance/citation checks only; semantic and language quality require human review'}

    def check_web_feasibility(self, mode, topics, feasibility, report):
        """Validate the narrow final-shortlist web gate, not source truth."""
        path=self.root/'web-feasibility.json'
        selection=(feasibility or {}).get('selection')
        post_excluded=(selection.get('post_verification_exclusions') or {}) if isinstance(selection,dict) else {}
        if not isinstance(post_excluded,dict):post_excluded={}
        provisional_ids=selection.get('selected_topic_ids',[]) if isinstance(selection,dict) else list(topics)
        required=bool(report and provisional_ids and (mode in {'topic','full','evaluate'} or report.get('topic_ids')))
        if required:self.need(path.is_file(),'final topic report requires web-feasibility.json')
        if not path.is_file():return None
        web=self.load('web-feasibility.json')
        self.require_keys(web,['version','purpose','status','checked_at','topic_ids','final_topic_ids','reason','results'],'web feasibility')
        self.need(web.get('purpose')=='final-feasibility-only','web feasibility purpose must be final-feasibility-only')
        self.need(web.get('status') in {'complete','limited','unavailable'},'invalid web feasibility status')
        if web.get('status') in {'limited','unavailable'}:
            self.need(isinstance(web.get('reason'),str) and bool(web['reason'].strip()),'limited/unavailable web feasibility requires reason')
        checked_at=web.get('checked_at')
        self.need(isinstance(checked_at,str) and bool(checked_at),'web feasibility requires checked_at')
        design=design_module()
        checked_time=design.time_value(self,checked_at,'web feasibility checked_at')
        hot=self.load('hotspots.json') if (self.root/'hotspots.json').is_file() else {}
        lower_time=design.time_value(self,hot.get('checked_at'),'shared hotspot completion') if hot else None
        if (self.root/'topics.json').is_file():
            formed=self.load('topics.json').get('formed_at')
            if formed:
                formed_time=design.time_value(self,formed,'candidate formation')
                if formed_time and (lower_time is None or formed_time>lower_time):lower_time=formed_time
        if checked_time and lower_time:
            self.need(checked_time>=lower_time,'final web verification cannot precede candidate formation')
        def visit_time(value,label):
            stamp=design.time_value(self,value,label)
            if stamp and checked_time:self.need(stamp<=checked_time,label+': visit after verification completion')
            if stamp and lower_time:self.need(stamp>=lower_time,label+': new visit before candidate formation; reuse shared hotspot source instead')
            return stamp

        def topic_ids(value,label):
            valid=isinstance(value,list) and all(isinstance(v,str) and v for v in value)
            self.need(valid,label+': expected topic ID array')
            if not valid:return []
            self.need(len(value)==len(set(value)),label+': duplicate topic IDs')
            self.need(all(v in topics for v in value),label+': unknown topic ID')
            return value

        provisional=topic_ids(web.get('topic_ids'),'web provisional topics')
        final=topic_ids(web.get('final_topic_ids'),'web final topics')
        self.need(len(provisional)<=5,'web feasibility cannot inspect more than five topics')
        self.need(all(v in provisional for v in final),'web final topics must be a subset of the provisional shortlist')
        selection=(feasibility or {}).get('selection')
        if isinstance(selection,dict):
            selected=selection.get('selected_topic_ids') if isinstance(selection,dict) else None
            self.need(provisional==selected,'web feasibility must inspect exactly the eligible locally retained shortlist')
        else:
            self.need(len(provisional)==len(topics) and set(provisional)==set(topics),
                      'web feasibility must inspect every candidate when there are at most five')

        results=self.indexed(web.get('results',[]),'topic_id')
        self.need(set(results)==set(provisional),'web feasibility result coverage mismatch')
        assessments={a.get('topic_id'):a for a in (feasibility or {}).get('assessments',[]) if isinstance(a,dict)}
        for tid,result in results.items():
            self.need(result.get('status') in WEB_RESULTS,f'{tid}: invalid web feasibility result')
            self.require_keys(result,['checks','searches','attempts','reused_hotspot_sources','conclusion','effect_on_verdict','unresolved'],tid+' web feasibility')
            checks=result.get('checks')
            self.need(isinstance(checks,dict),f'{tid}: web checks must be an object')
            if isinstance(checks,dict):
                for key in ['research_overlap','resource_access','current_context','implementation_blockers']:
                    self.need(isinstance(checks.get(key),str) and bool(checks[key].strip()),f'{tid}: missing web check {key}')
            self.need(bool(result.get('conclusion')),f'{tid}: missing web conclusion')
            self.need(result.get('effect_on_verdict') in {'建议做','调整后再做','不建议做','暂无法判断'},f'{tid}: invalid web verdict effect')
            verdicts_by_status={
                'confirmed':{'建议做','调整后再做'},
                'conditional':{'调整后再做','暂无法判断'},
                'not_feasible':{'不建议做'},
                'unavailable':{'暂无法判断'},
            }
            if result.get('status') in verdicts_by_status:
                self.need(result.get('effect_on_verdict') in verdicts_by_status[result['status']],f'{tid}: web status conflicts with verdict effect')
            self.need(isinstance(result.get('unresolved'),list),f'{tid}: web unresolved must be an array')
            if tid in assessments:
                self.need(assessments[tid].get('verdict')==result.get('effect_on_verdict'),f'{tid}: web verdict was not synchronized to feasibility.json')
            searches=result.get('searches')
            self.need(isinstance(searches,list),f'{tid}: web searches must be an array')
            if not isinstance(searches,list):searches=[]
            self.need(len(searches)<=2,f'{tid}: web feasibility exceeds the two-search limit')
            reused=result.get('reused_hotspot_sources',[])
            self.need(isinstance(reused,list),f'{tid}: reused hotspot sources must be an array')
            if not isinstance(reused,list):reused=[]
            hot_sources={s.get('web_id'):s for s in hot.get('sources',[])}
            direct_sources=0
            for item in reused:
                key=item.get('web_id');source=hot_sources.get(key)
                self.need(source is not None,f'{tid}: unknown reused hotspot source')
                self.need(bool(item.get('supports')),f'{tid}: reused source must explain what it verifies')
                if source and source.get('access_level') not in {'metadata','landing-page'}:direct_sources+=1
            attempts=result.get('attempts',[])
            self.need(isinstance(attempts,list) and len(attempts)<=3,f'{tid}: at most three direct-source targets including failures')
            if not isinstance(attempts,list):attempts=[]
            attempt_urls=set()
            complete_urls=set()
            for attempt in attempts:
                if attempt.get('outcome') in {'read','partial'}:attempt_urls.add(attempt.get('url'))
                if attempt.get('outcome')=='read':complete_urls.add(attempt.get('url'))
                self.need(bool(re.match(r'^https?://',str(attempt.get('url','')))),f'{tid}: web attempt requires HTTP(S) URL')
                self.need(attempt.get('outcome') in {'read','partial','failed'},f'{tid}: invalid web attempt outcome')
                visit_time(attempt.get('accessed_at'),tid+' web attempt')
            for number,search in enumerate(searches,1):
                label=f'{tid}/search-{number}'
                self.require_keys(search,['purpose','query','searched_at','reviewed_scope','sources'],label)
                for key in ['purpose','query','reviewed_scope']:
                    self.need(isinstance(search.get(key),str) and bool(search[key].strip()),f'{label}: missing {key}')
                searched_at=search.get('searched_at')
                self.need(isinstance(searched_at,str) and bool(searched_at),f'{label}: missing searched_at')
                visit_time(searched_at,label+' searched_at')
                sources=search.get('sources')
                self.need(isinstance(sources,list),f'{label}: sources must be an array')
                for index,source in enumerate(sources if isinstance(sources,list) else [],1):
                    source_label=f'{label}/source-{index}'
                    for key in ['title','url','source_type','accessed_at','access_level','observed','limitations']:
                        self.need(key in source and source[key] not in (None,''),f'{source_label}: missing {key}')
                    self.need(source.get('access_level') in WEB_ACCESS,f'{source_label}: invalid access_level')
                    self.need(source.get('url') in attempt_urls,f'{source_label}: direct visit missing from attempts')
                    if source.get('access_level') not in {'metadata','landing-page'} and source.get('url') in attempt_urls:direct_sources+=1
                    if source.get('source_type')=='academic':design_module().external_source(self,source,source_label)
                    if source.get('access_level')=='fulltext':
                        self.need(source.get('url') in complete_urls,f'{source_label}: fulltext claim conflicts with incomplete visit')
                    self.need('source_id' not in source and 'evidence_ids' not in source,f'{source_label}: web source must not enter the paper source registry')
                    self.need(isinstance(source.get('url'),str) and bool(re.match(r'^https?://',source['url'],re.I)),f'{source_label}: URL must be HTTP(S)')
                    accessed_at=source.get('accessed_at')
                    visit_time(accessed_at,source_label+' accessed_at')
            design.check_data_evidence(self,tid,topics.get(tid,{}),result,hot,report or {},tid in final)
            if result.get('status')=='not_feasible':self.need(tid not in final,f'{tid}: not_feasible topic cannot enter the report')
            if tid in post_excluded:
                self.need(tid not in final and result.get('status')=='not_feasible',
                          f'{tid}: post-verification exclusion must be not_feasible and absent from final topics')
            if web.get('status')=='complete':
                self.need(result.get('status')!='unavailable',f'{tid}: complete web feasibility contains an unavailable result')
                self.need(direct_sources>0,f'{tid}: complete web feasibility lacks a direct source')
                if tid in final:self.need(result.get('status') in {'confirmed','conditional'},f'{tid}: complete final topic is not feasibility-confirmed')
            if web.get('status')=='unavailable':
                self.need(result.get('status')=='unavailable' or
                          (tid in post_excluded and result.get('status')=='not_feasible'),
                          f'{tid}: unavailable web gate cannot claim a completed result')
        if web.get('status')=='complete':
            retained={tid for tid,result in results.items() if result.get('status') in {'confirmed','conditional'}}
            self.need(set(final)==retained,'complete web gate must output every confirmed/conditional provisional topic and exclude the rest')
        if report:
            self.need(report.get('feasibility_verification')==web.get('status'),'report feasibility_verification does not match web record')
            if web.get('status') in {'limited','unavailable'}:
                self.need(report.get('status')=='draft','limited/unavailable web verification requires a draft report')
        return web

    def check_topic_selection(self, topics, feasibility, report, web=None):
        """Check declared shortlist handoff; the agent must assess feasibility/text."""
        selection = (feasibility or {}).get('selection')
        if len(topics) > 5 and report:
            self.need(isinstance(selection, dict), 'more than five topics requires feasibility selection before the report')
        def ids(value, label):
            valid = isinstance(value, list) and all(isinstance(v, str) and v for v in value)
            self.need(valid, label + ': expected topic ID array')
            if not valid:
                return None
            self.need(len(value) == len(set(value)), label + ': duplicate topic IDs')
            self.need(all(v in topics for v in value), label + ': unknown topic ID')
            return value
        selected = None
        if selection is not None:
            self.need(isinstance(selection, dict), 'invalid feasibility selection')
            if isinstance(selection, dict):
                eligible=ids(selection.get('eligible_topic_ids'),'selection eligible')
                current_eligible={tid for tid,t in topics.items() if (t.get('qualification') or {}).get('status')=='eligible'}
                post=selection.get('post_verification_exclusions',{})
                self.need(isinstance(post,dict),'post-verification exclusions must be an object')
                if not isinstance(post,dict):post={}
                self.need(all(isinstance(v,str) and v.strip() for v in post.values()),
                          'post-verification exclusions need substantive reasons')
                self.need(set(post)<=set(topics)-current_eligible,
                          'post-verification exclusions must identify currently ineligible topics')
                if post:
                    provisional=(web or {}).get('topic_ids',[])
                    results={r.get('topic_id'):r for r in (web or {}).get('results',[]) if isinstance(r,dict)}
                    self.need(web is not None and all(t in provisional for t in post),
                              'post-verification exclusions require the actual verified shortlist')
                    self.need(all(results.get(t,{}).get('status')=='not_feasible' and
                                  results.get(t,{}).get('effect_on_verdict')=='不建议做' for t in post),
                              'post-verification exclusions require synchronized rejection results')
                    self.need(not set(post)&set((web or {}).get('final_topic_ids',[])),
                              'post-verification exclusions cannot reenter final topics')
                expected_eligible=current_eligible|set(post)
                if eligible is not None:
                    self.need(set(eligible)==expected_eligible,'selection eligible snapshot must match qualifications plus documented later exclusions')
                excluded=selection.get('ineligible_reasons',{})
                self.need(isinstance(excluded,dict) and set(excluded)==set(topics)-expected_eligible,
                          'selection must record all ineligible topics internally')
                if isinstance(excluded,dict):self.need(all(isinstance(v,str) and v.strip() for v in excluded.values()),'ineligible reasons cannot be empty')
                ranked = ids(selection.get('ranked_topic_ids'), 'selection ranking')
                selected = ids(selection.get('selected_topic_ids'), 'selection retained')
                if ranked is not None:
                    self.need(set(ranked)==expected_eligible, 'selection ranking must cover only eligible candidates exactly once')
                    if selected is not None:
                        self.need(selected == ranked[:5], 'selection must retain the first five ranked topics, or all when fewer')
                        self.need(set(post)<=set(selected),'later exclusions must belong to the original retained shortlist')
                self.need(isinstance(selection.get('ranking_reason'), str) and bool(selection['ranking_reason'].strip()), 'selection requires a feasibility comparison reason')
        if report and ('topic_ids' in report or len(topics) > 5 or selection is not None):
            shown = ids(report.get('topic_ids'), 'report topics')
            if shown is not None:
                self.need(len(shown) <= 5, 'report cannot present more than five topics')
                if web is not None:
                    self.need(shown == web.get('final_topic_ids'), 'report topics must match web-feasibility final topics and order')
                elif selected is not None:
                    self.need(all(tid in selected for tid in shown), 'report topics must remain within the retained selection')

    def check_literature_policy(self, mode, constraints, report):
        """Enforce review presence from the retained output, not the run label."""
        policy=constraints.get('literature_review_policy')
        waiver=constraints.get('literature_review_waiver')
        topic_ids=report.get('topic_ids')
        retained=topic_ids if isinstance(topic_ids,list) else []
        declared=report.get('literature_review')
        document_type=report.get('document_type')

        if mode=='full':
            self.need(policy=='required',
                      'full mode cannot waive the literature review')
        if document_type=='review-article':
            self.need(policy=='required' and declared=='article',
                      'a review article requires article literature review mode')
            return
        if retained:
            if policy=='required':
                self.need(declared=='per-topic',
                          'a final report with retained topics requires per-topic literature reviews')
            elif policy=='waived':
                self.need(isinstance(waiver,str) and bool(waiver.strip()),
                          'review waiver requires the user\'s exact request')
                self.need(document_type=='topic-report' and declared=='none',
                          'an explicit review waiver may only produce a topic report with literature_review none')
            else:
                self.errors.append('literature review policy is missing or invalid')
        elif document_type in {'topic-report','formal-proposal'}:
            self.need(declared=='none',
                      'a topic report with zero retained topics must use literature_review none')

    def check_review_article_structure(self, report, text):
        """Validate the PDF-required front and body structure of a standalone review."""
        if report.get('document_type')!='review-article':
            return
        h1=re.findall(r'^#\s+(.+?)\s*$',text,re.M)
        self.need(len(h1)==1,'review article requires exactly one level-1 title')

        first_h2=re.search(r'^##\s+',text,re.M)
        front=text[:first_h2.start()] if first_h2 else text
        raw_author=report.get('author',report.get('authors'))
        if isinstance(raw_author,str):
            authors=[raw_author.strip()] if raw_author.strip() else []
        elif isinstance(raw_author,list):
            authors=[str(value).strip() for value in raw_author if str(value).strip()]
        else:
            authors=[]
        if report.get('status')=='formal-ready':
            self.need(bool(authors),'formal-ready review article requires a real author')
        elif not authors:
            self.warnings.append('review article draft has no author; it cannot be formal-ready')
        if authors:
            compact_front=re.sub(r'\s+','',front)
            self.need(all(re.sub(r'\s+','',author) in compact_front for author in authors),
                      'review article author must appear before the first section')

        abstract=re.search(
            r'^(?:#{2,6}\s+)?(?:\*\*)?摘\s*要(?:\*\*)?\s*[：:]?\s*(.*?)\s*$',
            text,re.M)
        self.need(bool(abstract),'review article requires an abstract')
        if abstract:
            abstract_text=re.sub(r'\*+$','',abstract.group(1)).strip()
            if not abstract_text:
                tail=text[abstract.end():]
                paragraph=re.search(r'\A\s*\n(?:\s*\n)*([^#\n].+)',tail)
                abstract_text=paragraph.group(1).strip() if paragraph else ''
            self.need(bool(abstract_text),'review article abstract cannot be empty')

        keywords=re.search(
            r'^(?:#{2,6}\s+)?(?:\*\*)?关\s*键\s*词(?:\*\*)?\s*[：:]\s*(.*?)\s*$',
            text,re.M)
        self.need(bool(keywords),'review article requires keywords')
        if keywords:
            value=re.sub(r'\*+$','',keywords.group(1)).strip()
            terms=[term.strip() for term in re.split(r'[；;，,、]+',value) if term.strip()]
            if len(terms)==1 and re.search(r'\s+',value):
                terms=[term for term in re.split(r'\s+',value) if term]
            self.need(3<=len(terms)<=5,'review article requires 3-5 keywords')

        headings=[match.group(1).strip() for match in re.finditer(r'^#{2,6}\s+(.+?)\s*$',text,re.M)]
        normalized=[re.sub(r'^[一二三四五六七八九十\d、.（）()\s]+','',heading) for heading in headings]
        self.need(any(heading=='引言' for heading in normalized),'review article requires an introduction heading')
        self.need(any(heading in {'参考文献','References'} for heading in normalized),
                  'review article requires a references heading')
        structural={'摘要','关键词','引言','研究述评','结语','结论','展望','结语与展望',
                    '结论与展望','参考文献','References'}
        self.need(any(heading not in structural for heading in normalized),
                  'review article requires content-specific thematic body headings')

    def check_report(self, report, sources):
        text = self.path(report['markdown']).read_text(encoding='utf-8')
        markdown = markdown_module()
        try:
            markdown.validate_heading_hierarchy(text)
        except ValueError as exc:
            self.errors.append(str(exc))
        body,bibtext = markdown.split_reference_sections(text)
        body_labels=numeric_labels(body,markdown=True) if report.get('citation_style')=='numeric' else set()
        bib = self.indexed(report.get('bibliography',[]),'source_id')
        cites = report.get('citations',[])
        self.need(report.get('citation_style') in {'numeric','author-year'}, 'unsupported citation style')
        self.need(report.get('status') in {'draft','formal-ready'}, 'invalid report status')
        literature_review=report.get('literature_review')
        self.need(literature_review in {'none','per-topic','article'},
                  'report must declare literature_review as none, per-topic, or article')
        self.need(report.get('document_type') in {'topic-report','formal-proposal','review-article'},
                  'unsupported report document_type')
        if literature_review=='none':
            self.need(report.get('document_type')=='topic-report' or (report.get('document_type')=='formal-proposal' and report.get('topic_ids')==[]),
                      'only a topic report may omit a formal literature review')
        if report.get('document_type')=='formal-proposal':
            self.need(literature_review=='per-topic' or (report.get('topic_ids')==[] and literature_review=='none'),
                      'formal-proposal requires per-topic literature reviews')
        if report.get('document_type')=='review-article':
            self.need(literature_review=='article',
                      'review-article requires article literature review mode')
            self.check_review_article_structure(report,text)
        self.check_reader_facing_report(report,text,markdown)
        style=str(report.get('reference_style',''))
        if report.get('status')=='formal-ready':
            self.need(bool(style) and style!='basic','formal-ready report requires a verified reference style')
            self.need(isinstance(report.get('reference_style_basis'),str) and
                      bool(report['reference_style_basis'].strip()),
                      'formal-ready report requires a reference style basis')
        if re.search(r'GB\s*/\s*T\s*7714\s*[-—]\s*2015',style,re.I):
            self.need(report.get('reference_style_confirmed_by_user') is True and
                      isinstance(report.get('reference_style_basis'),str) and bool(report['reference_style_basis'].strip()),
                      'GB/T 7714-2015 was replaced; using it requires an explicit user/target-template basis')
        self.need('word' not in report and 'word_declined_by_user' not in report,
                  'remove legacy Word delivery fields; final report must be Markdown only')
        self.need(set(bib)=={c['source_id'] for c in cites}, 'body citations/bibliography mismatch')
        labels = {}
        missing_metadata_verification = []
        for sid,b in bib.items():
            self.need(sid in sources, f'bibliography: unknown source {sid}')
            self.need(bool(b.get('entry')) and b['entry'] in bibtext, f'{sid}: bibliography entry missing from references section')
            label = str(b.get('label',''))
            self.need(bool(label) and label not in labels, f'{sid}: empty/duplicate citation label')
            labels[label] = sid
            if sid in sources:
                source = sources[sid]
                self.need(b.get('entry')==reference_entry(source,report.get('reference_style','basic')), f'{sid}: bibliography differs from canonical source metadata')
                self.need(source['access_level']!='metadata', f'{sid}: metadata-only source cannot support formal body claims')
                verification=source.get('metadata_verification')
                if not isinstance(verification,dict):
                    missing_metadata_verification.append(sid)
                if isinstance(verification,dict):
                    self.need(verification.get('method') in {'pdf-title-page','pdf-title-and-end-pages'},
                              f'{sid}: invalid metadata verification method')
                    self.need(bool(verification.get('locator')) and bool(verification.get('checked_at')),
                              f'{sid}: metadata verification needs locator and date')
                    observed=verification.get('observed');checked=verification.get('checked_fields')
                    self.need(isinstance(observed,dict) and isinstance(checked,list),
                              f'{sid}: metadata verification needs observed values and checked_fields')
                    if isinstance(observed,dict) and isinstance(checked,list):
                        for key in {'title','authors','year','publication','volume','issue','pages_or_article','doi'}:
                            if source.get(key) not in (None,'',[]):
                                self.need(key in checked and observed.get(key)==source.get(key),
                                          f'{sid}: unverified or mismatched metadata field {key}')
                if report.get('status')=='formal-ready':
                    self.need(source['verified'] and not source.get('missing_fields'), f'{sid}: formal-ready has unverified/incomplete reference')
                    for key in set(source.get('required_fields',[]))|{'title','authors','year','publication'}:
                        self.need(bool(source.get(key)), f'{sid}: formal-ready missing {key}')
        self.need(not missing_metadata_verification,
                  'cited sources need metadata_verification: '+', '.join(missing_metadata_verification))
        tokens = {}
        for c in cites:
            self.need(c['source_id'] in sources, 'citation: unknown source')
            present = (str(bib.get(c['source_id'],{}).get('label')) in body_labels
                       if report['citation_style']=='numeric' else c.get('token') in body)
            self.need(bool(c.get('token')) and present, f'citation token absent from body: {c.get("token")}')
            self.need(bool(c.get('locator')), 'citation requires report location')
            if c.get('token') in tokens: self.need(tokens[c['token']]==c['source_id'], 'ambiguous citation token')
            tokens[c.get('token')] = c['source_id']
        if report['citation_style']=='numeric':
            order = numeric_citation_order(body, markdown=True)
            self.need(order == [str(n) for n in range(1, len(order) + 1)],
                      'numeric citations must follow first-appearance order starting at [1]')
            used = set()
            for label in body_labels:
                self.need(label in labels,f'dangling body citation [{label}]')
                if label in labels: used.add(labels[label])
            self.need(used==set(bib), 'numeric body/reference coverage mismatch')
            for c in cites:
                b = bib.get(c['source_id'],{})
                self.need(str(b.get('label','')).isdigit() and c['token']==f'[{b.get("label")}]', 'numeric citation token/label mismatch; use canonical [n] in registry')
        else:
            self.warnings.append('author-year token completeness requires manual review')
        self.need(all(sid in sources for sid in report.get('recommended_source_ids',[])), 'unknown recommended source')
        self.need(not re.search(r'\b(?:TODO|TBD|FIXME)\b|\{\{[^}]+\}\}|<待填>|〔[^〕]+〕',text,re.I), 'unresolved placeholder in report')
        language=report.get('review',{}).get('language')
        self.need(isinstance(language,dict) and language.get('status')=='passed', 'final Markdown requires a passed full-text language review record')
        if isinstance(language,dict) and language.get('record'):
            try:language_module().require_passed(self.path(report['markdown']),self.path(language['record']),run_root=self.root)
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:self.errors.append('language review: '+str(exc))
        else:self.errors.append('missing full-text language review path')

    def check_reader_facing_report(self, report, text, markdown):
        """Check the stable report shell without judging academic prose."""
        document_type=report.get('document_type')
        if document_type not in {'topic-report','formal-proposal'}:
            return
        self.need(report.get('template_version')=='markdown-report-v3',
                  'topic reports require template_version markdown-report-v3')

        stripped=re.sub(r'<!--.*?-->','',text,flags=re.S)
        visible=[];in_code=False
        for line in stripped.splitlines():
            if line.strip().startswith('```'):
                in_code=not in_code
                continue
            if in_code:
                continue
            visible.append(''.join(value for kind,value,_ in markdown.inline_tokens(line)))
        visible_text='\n'.join(visible)
        self.need(not re.search(r'(?<![\w-])[PTES]\d{3,}(?![\w-])',visible_text),
                  'reader-facing report exposes an internal topic/source/evidence ID')
        self.need(not re.search(r'(?:/Users/|/home/|/Volumes/|[A-Za-z]:[\\/]+Users[\\/])',visible_text),
                  'reader-facing report exposes a local absolute path')
        self.need(not re.search(r'\b(?:manifest|references|topics|hotspots|feasibility|web-feasibility|language-review)\.json\b',visible_text,re.I),
                  'reader-facing report exposes an internal run filename')

        h2=[m.group(1).strip() for m in re.finditer(r'^##\s+(.+?)\s*$',stripped,re.M)]
        standard=['一、结论摘要','二、材料范围与判断边界','三、研究基础与热点依据',
                  '四、推荐选题及实施方案','五、优先阅读文献','六、参考文献']
        formal=['一、结论摘要','二、材料范围与判断边界','三、研究基础与热点依据',
                '四、推荐选题及实施方案','五、逐题文献综述','六、优先阅读文献','七、参考文献']
        expected=formal if report.get('literature_review')=='per-topic' else standard
        self.need(h2==expected,
                  'reader-facing report chapters must exactly follow the selected Markdown report template')

        first_h2=re.search(r'^##\s+',stripped,re.M)
        front=stripped[:first_h2.start()] if first_h2 else stripped
        for label in ['报告状态','材料范围','阅读情况','热点核验','学术全文','外部核验','输出结果']:
            self.need(label in front,'report status block is missing '+label)
        # Inspect only status declarations, not quotations or negated discussion.
        front_visible='\n'.join(''.join(value for _,value,_ in markdown.inline_tokens(line))
                                for line in front.splitlines())
        def declaration(text, label):
            match=re.search(r'^[ \t>]*'+re.escape(label)+r'[：:]\s*([^\n]+)', text, re.M)
            return match[1].strip() if match else ''
        if report.get('status')=='draft':
            self.need(not re.match(r'(?:正式可用|正式定稿|可直接使用)', declaration(front_visible,'报告状态')),
                      'draft report cannot visibly claim formal readiness')

        topic_titles=[]
        has_topics_file=(self.root/'topics.json').is_file()
        if has_topics_file:
            topics={t.get('topic_id'):t for t in self.load('topics.json').get('topics',[])}
            topic_titles=[topics.get(tid,{}).get('title') for tid in report.get('topic_ids',[])]
            self.need(all(isinstance(title,str) and title for title in topic_titles),
                      'report topic title is missing from topics.json')
        displayed=[m.group(1).strip() for m in re.finditer(r'^###\s+\d+\.\s+(.+?)\s*$',stripped,re.M)]
        if has_topics_file:
            self.need(displayed==topic_titles,
                      'numbered topic sections must match final topic titles and order')

        topic_blocks={}
        matches=list(re.finditer(r'^###\s+\d+\.\s+(.+?)\s*$',stripped,re.M))
        for index,match in enumerate(matches):
            end=matches[index+1].start() if index+1<len(matches) else len(stripped)
            next_h2=re.search(r'^##\s+',stripped[match.end():end],re.M)
            if next_h2:end=match.end()+next_h2.start()
            topic_blocks[match.group(1).strip()]=stripped[match.start():end]
            self.need('资料条件与联网核验' in topic_blocks[match.group(1).strip()],
                      'each final topic requires one combined data-and-web feasibility section')
            for heading in ['研究问题','选题依据与可能贡献','理论与机制','研究设计','结论与证据对应','预期回答与解决问题的落点']:
                block=topic_blocks[match.group(1).strip()]
                section=re.search(r'^#### '+re.escape(heading)+r'\s*\n(.*?)(?=^#{1,4}\s|\Z)',block,re.M|re.S)
                self.need(section is not None and bool(section[1].strip()),
                          'each final topic requires substantive design section: '+heading)

        hot=self.load('hotspots.json') if (self.root/'hotspots.json').is_file() else {}
        if hot:
            for key,notice in [('status','热点核验受限'),('academic_fulltext','学术全文核验受限')]:
                if hot.get(key)!='complete':self.need(notice in front,'limited verification must visibly state '+notice)
            for key,label in [('status','热点核验'),('academic_fulltext','学术全文')]:
                if hot.get(key)!='complete':
                    self.need(not re.match(r'(?:已完成|全部完成|已确认)', declaration(front_visible,label)),
                              'visible '+label+' completion contradicts limited record')

        web_path=self.root/'web-feasibility.json'
        if web_path.is_file():
            web=self.load('web-feasibility.json')
            results={item.get('topic_id'):item for item in web.get('results',[])}
            summary=re.search(r'^## 一、结论摘要\s*\n(.*?)(?=^##\s|\Z)',stripped,re.M|re.S)
            summary_verdicts={}
            for line in (summary[1] if summary else '').splitlines():
                if line.strip().startswith('|'):
                    cells=[''.join(value for _,value,_ in markdown.inline_tokens(cell)).strip()
                           for cell in line.strip().strip('|').split('|')]
                    if len(cells)>=3 and cells[1] in topic_titles:
                        summary_verdicts[cells[1]]=cells[2]
            for tid,title in zip(report.get('topic_ids',[]),topic_titles):
                result=results.get(tid,{})
                allowed={'confirmed':{'建议开展','建议做','调整后开展','调整后再做'},
                         'conditional':{'调整后开展','调整后再做','暂无法判断'},
                         'unavailable':{'暂无法判断'}}.get(result.get('status'))
                if title in summary_verdicts and allowed is not None:
                    self.need(summary_verdicts[title] in allowed,
                              tid+': summary recommendation contradicts verification record')
                if any(item.get('status')!='verified' for item in result.get('data_checks',[])):
                    self.need('关键资料待核' in topic_blocks.get(title,''),
                              tid+': topic must visibly disclose 关键资料待核')
                sources=[source for search in result.get('searches',[]) for source in search.get('sources',[])]
                hot_sources={s.get('web_id'):s for s in hot.get('sources',[])}
                sources += [hot_sources[item['web_id']] for item in result.get('reused_hotspot_sources',[]) if item.get('web_id') in hot_sources]
                block=topic_blocks.get(title,'')
                block_visible='\n'.join(''.join(value for _,value,_ in markdown.inline_tokens(line))
                                        for line in block.splitlines())
                if result.get('status') in {'conditional','unavailable','not_feasible'}:
                    for label in ['核验结论','推荐结论']:
                        self.need(not re.match(r'(?:已确认|确认可行|建议开展|建议做)', declaration(block_visible,label)),
                                  tid+': visible unconditional recommendation contradicts verification record')
                if sources:
                    links=set(markdown.markdown_links(block))
                    visible_sources=[source for source in sources if source.get('url') in links]
                    self.need(bool(visible_sources),f'{tid}: final report must show a direct web source in its topic section')
                    self.need(any(str(source.get('accessed_at',''))[:10] in block for source in visible_sources),
                              f'{tid}: visible web source requires its access date')
            if web.get('status') in {'limited','unavailable'}:
                self.need('外部可行性待核' in visible_text,
                          'limited/unavailable web verification must visibly state 外部可行性待核')
                self.need(not re.match(r'(?:已完成|全部完成|已确认)', declaration(front_visible,'外部核验')),
                          'visible external completion contradicts limited record')

        # Priority reading is local scholarship, not a second web-source list.
        priority=re.search(r'^##\s+[^\n]*优先阅读文献\s*\n(.*?)(?=^##\s|\Z)',stripped,re.M|re.S)
        if priority:
            external=list(hot.get('sources',[]))
            if web_path.is_file():
                external += [s for result in web.get('results',[]) for search in result.get('searches',[])
                             for s in search.get('sources',[])]
            refs=self.load('references.json') if (self.root/'references.json').is_file() else {}
            local_titles={s.get('title') for s in refs.get('sources',[])}
            urls=set(markdown.markdown_links(priority[1]))
            for source in external:
                title=source.get('title')
                named=bool(title and title not in local_titles and title in priority[1])
                self.need(not (named or source.get('url') in urls),
                          'priority reading cannot include external verification sources')

    def check_rules(self, manifest, report, sources):
        """Only explicit, user-confirmed numeric requirements; no course defaults."""
        cited = [sources[b['source_id']] for b in report.get('bibliography',[]) if b['source_id'] in sources]
        text = self.path(report['markdown']).read_text(encoding='utf-8')
        title = re.search(r'^#[ \t]+(.+)$',text,re.M)
        for rule in manifest.get('rules',[]):
            if not isinstance(rule,dict) or not rule.get('enabled'): continue
            self.need(rule.get('confirmed_by_user') is True and bool(rule.get('source')), 'enabled rule requires user confirmation and source')
            if rule.get('document_type') != report.get('document_type','topic-report'): continue
            gaps = []
            if rule.get('min_references') is not None and len(cited)<rule['min_references']:
                gaps.append('reference count below '+str(rule['min_references']))
            if rule.get('title_max_chars') is not None:
                self.need(rule.get('title_count_mode') in {'han','all'}, 'title rule needs an explicit count mode')
                count = len(re.findall(r'[\u3400-\u9fff]',title[1])) if title and rule.get('title_count_mode')=='han' else len(title[1]) if title else 0
                if not title or count>rule['title_max_chars']: gaps.append('title length exceeds configured limit or title missing')
            if rule.get('recent_min_count') is not None:
                self.need(type(rule.get('as_of_year')) is int and type(rule.get('recent_years')) is int and rule['recent_years']>0, 'recent-reference rule needs explicit year/window')
                if type(rule.get('as_of_year')) is int and type(rule.get('recent_years')) is int:
                    recent = sum(type(s.get('year')) is int and rule['as_of_year']-rule['recent_years']+1 <= s['year'] <= rule['as_of_year'] for s in cited)
                    if recent<rule['recent_min_count']: gaps.append('recent reference count below configured minimum')
            if rule.get('foreign_min_ratio') is not None:
                self.need(0<=rule['foreign_min_ratio']<=1, 'foreign reference ratio must be 0..1')
                known = all(bool(s.get('language')) for s in cited)
                ratio = sum(not s.get('language','zh').lower().startswith('zh') for s in cited)/max(1,len(cited))
                if not known or ratio<rule['foreign_min_ratio']: gaps.append('foreign reference ratio insufficient or languages unknown')
            for gap in gaps:
                message = 'configured rule '+rule.get('source','')+': '+gap
                if report.get('status')=='formal-ready': self.errors.append(message)
                else: self.warnings.append(message+'; draft only')

def delivery_result(checker, result):
    """Expose check failure and an existing draft path without rewriting artifacts."""
    path = None
    report = {}
    try:
        report = checker.load('manifest.json').get('report') or {}
        if report.get('markdown'):
            candidate = checker.path(report['markdown'])
            if candidate.is_file():
                path = str(candidate)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # The check error remains authoritative; do not invent a fallback file.
    failed = bool(result['errors'])
    state = ('unvalidated-draft' if failed else
             'checked-formal' if report.get('status') == 'formal-ready' else 'checked-draft') if path else 'no-report'
    return {'validation': 'failed' if failed else 'passed', 'state': state, 'markdown': path,
            'instruction': ('仅交付未通过验收的现有草稿并明确错误；不得宣称已确认、正式可用或可直接复制。'
                            if failed else '按报告真实状态交付；结构通过不证明学术判断或研究结果正确。')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('init'); p.add_argument(
        'parent',type=Path,help='所有 --source-dir 的共同直接父目录；运行目录将在此创建')
    p.add_argument('--source-dir',type=Path,action='append')
    p.add_argument('--mode',choices=['topic','full','read','compare','evaluate','explore'],default='topic')
    p = sub.add_parser('check'); p.add_argument('run',type=Path)
    p = sub.add_parser('preflight'); p.add_argument('run',type=Path)
    p = sub.add_parser('reference-data'); p.add_argument('run',type=Path)
    p = sub.add_parser('design-data'); p.add_argument('run',type=Path)
    p = sub.add_parser('stamp'); p.add_argument('run',type=Path);p.add_argument('--upgrade',action='store_true')
    args = parser.parse_args(argv)
    if args.command=='init':
        try:print(init(args.parent.expanduser(),args.mode,args.source_dir));return 0
        except (OSError,ValueError) as exc:print(str(exc));return 2
    if args.command=='stamp':
        try:print(json.dumps(stamp(args.run.expanduser(),args.upgrade),ensure_ascii=False,indent=2));return 0
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:print(str(exc));return 1
    if args.command=='reference-data':
        sources = json.loads((args.run.expanduser()/'references.json').read_text(encoding='utf-8'))['sources']
        print(json.dumps([{'source_id':s['source_id'],'metadata_sha256':source_digest(s),'basic_entry':reference_entry(s)} for s in sources],ensure_ascii=False,indent=2))
        return 0
    if args.command=='design-data':
        topics = json.loads((args.run.expanduser()/'topics.json').read_text(encoding='utf-8')).get('topics',[])
        print(json.dumps([{'topic_id':t.get('topic_id'),'design_sha256':design_module().design_signature(t)}
                          for t in topics if (t.get('qualification') or {}).get('status')=='eligible'],ensure_ascii=False,indent=2))
        return 0
    c = Checker(args.run.expanduser())
    try:
        result = c.preflight() if args.command=='preflight' else c.check()
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        c.errors.append('invalid or missing record: '+str(exc))
        result = {'errors':c.errors,'warnings':c.warnings}
    if args.command=='check':
        result['delivery'] = delivery_result(c, result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
