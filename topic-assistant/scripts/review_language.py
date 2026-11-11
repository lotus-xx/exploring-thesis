#!/usr/bin/env python3
"""Track a real full-text editorial pass before Markdown delivery; Python 3.9+, stdlib.

prepare creates an immutable input snapshot and a pending review, never a pass.
The agent edits prose and resolves findings; seal checks coverage and fidelity.
This does not detect authorship, perform semantic editing, or call a model/API.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

POLICY=Path(__file__).resolve().parent.parent/'references/humanize-academic.md'
CHECKS=('full_text_read','facts_and_numbers','citations_and_quotes',
        'terms_and_scope','logic_and_uncertainty','changes_rechecked')
LITERATURE_CHECKS=('pdf_structure','source_selection','comparison_and_critique','evidence_and_scope',
                   'standalone_prose','reference_format')
# Context cues, not banned words. Retaining one with a specific reason is valid.
PATTERNS={
    'empty_significance':r'具有重要意义|深刻揭示|开启新篇章|注入新动能|里程碑式',
    'stock_transition':r'综上所述|值得注意的是|首先|其次|最后|总而言之|展望未来',
    'vague_jargon':r'赋能|核心抓手|全方位|多维度|闭环',
    'vague_attribution':r'有研究表明|相关研究表明|学者普遍认为|众所周知|不言而喻',
    'overclaim':r'填补[^。；\n]{0,12}空白|彻底解决|必将|毋庸置疑',
    'chat_residue':r'希望[^。\n]{0,12}帮助|以下是|让我们|作为[^。\n]{0,8}AI|如需[^。\n]{0,12}告诉我',
    'staged_contrast':r'不仅[^。\n]{0,50}而且|不是[^。\n]{0,50}而是',
    'english_filler':r'\b(?:delve|tapestry|pivotal|moreover)\b|it is worth noting|in conclusion',
}

def digest(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def units(text):
    return [{'unit_id':f'U{i:05d}','line':line,'sha256':digest(value.encode())}
            for i,(line,value) in enumerate(((n,s) for n,s in enumerate(text.splitlines(),1) if s.strip()),1)]

def scan(text):
    lines=text.splitlines();result=[]
    for unit in units(text):
        for pattern,regex in PATTERNS.items():
            for match in re.finditer(regex,lines[unit['line']-1],re.I):
                result.append({'issue_id':f'I{len(result)+1:05d}','units':[unit['unit_id']],
                    'pattern':pattern,'before':match[0],'action':'pending','after':'','reason':''})
    return result

def markdown_tools():
    spec=importlib.util.spec_from_file_location('_language_md',Path(__file__).with_name('markdown_utils.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def run_tools():
    spec=importlib.util.spec_from_file_location('_literature_run',Path(__file__).with_name('validate_run.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def context_root(source, record=None, run_root=None):
    """Use only explicitly supplied locations, never discover parent folders."""
    if run_root is not None:return Path(run_root).resolve()
    candidates=[record.parent,source.parent] if record is not None else [source.parent]
    for root in candidates:
        path=root/'manifest.json'
        if not path.is_file():continue
        report=load(path).get('report') or {}
        if report.get('markdown') and (root/report['markdown']).resolve()==source.resolve():return root
    return source.parent

def literature_context(source, root=None):
    root=root or source.parent;manifest=load(root/'manifest.json') if (root/'manifest.json').is_file() else {}
    report=manifest.get('report') or {}
    if not report.get('markdown') or (root/report['markdown']).resolve()!=source.resolve():return {},[],[]
    topics=load(root/'topics.json').get('topics',[]) if (root/'topics.json').is_file() else []
    feasibility=load(root/'feasibility.json') if (root/'feasibility.json').is_file() else None
    checker=run_tools().Checker(root)
    web=load(root/'web-feasibility.json') if (root/'web-feasibility.json').is_file() else None
    checker.check_topic_selection({t['topic_id']:t for t in topics},feasibility,report,web)
    constraints=manifest.get('constraints') if isinstance(manifest.get('constraints'),dict) else {}
    checker.check_literature_policy(manifest.get('mode'),constraints,report)
    declared=report.get('literature_review')
    policy=constraints.get('literature_review_policy')
    if report.get('document_type')=='review-article' or declared=='article':
        expected=['review']
    elif report.get('topic_ids') and policy!='waived':
        expected=report['topic_ids']
    elif declared=='none':
        expected=[]
    else:
        expected=report.get('topic_ids') or [t['topic_id'] for t in topics]
        if not expected and report.get('document_type') in {'formal-proposal','review-article'}:expected=['review']
    return report,expected,checker.errors

def literature_template(source, root=None):
    root=root or source.parent
    report,expected,_=literature_context(source,root)
    manifest=load(root/'manifest.json') if (root/'manifest.json').is_file() else {}
    constraints=manifest.get('constraints') if isinstance(manifest.get('constraints'),dict) else {}
    if expected:reason=''
    elif constraints.get('literature_review_policy')=='waived':reason='用户已明确要求不写文献综述'
    else:reason='本次没有最终入选题，不适用逐题文献综述'
    return {'applicable':True if expected else False,
            'reason':reason,
            'sources_path':'references.json',
            'citation_style':report.get('citation_style'),'reference_style':report.get('reference_style'),
            'reference_style_basis':report.get('reference_style_basis'),
            'sections':[{'topic_id':tid,'status':'pending','body_lines':[], 'reference_lines':[],
                         'source_ids':[],'evidence_ids':[],'notice':'',
                         'checks':{key:False for key in LITERATURE_CHECKS}} for tid in expected]}

def validate_literature(source,record,root=None):
    """Check declared review blocks and evidence links, not the truth of prose."""
    errors=[]
    def need(ok,message):
        if not ok:errors.append('literature: '+message)
    obj=record.get('literature')
    need(isinstance(obj,dict),'content acceptance declaration required')
    if not isinstance(obj,dict):return {'errors':errors,'context_sha256':None}
    root=root or source.parent
    report,expected,selection_errors=literature_context(source,root)
    errors.extend(selection_errors)
    text=source.read_text(encoding='utf-8');lines=text.splitlines()
    cv=markdown_tools();vr=run_tools()
    need(type(obj.get('applicable')) is bool,'declare whether the document contains a literature review')
    if obj.get('applicable') is False:
        need(not expected,'retained topics or review article cannot bypass review acceptance')
        need(not obj.get('sections') and bool(obj.get('reason','').strip()),'non-review document needs a reason and no review sections')
        need(not re.search(r'^#{1,6}\s+(?:(?:[一二三四五六七八九十]+|\d+)[、.]\s*)?(?:逐题)?(?:文献综述|研究现状|文献回顾|相关研究|Literature Review|Related Work)\s*$',text,re.M|re.I),'review heading conflicts with non-review declaration')
        return {'errors':errors,'context_sha256':None}
    if obj.get('applicable') is not True:return {'errors':errors,'context_sha256':None}
    sections=obj.get('sections');need(isinstance(sections,list) and bool(sections),'review sections required')
    if not isinstance(sections,list) or not sections:return {'errors':errors,'context_sha256':None}
    need(all(isinstance(s,dict) for s in sections),'invalid review section')
    if not all(isinstance(s,dict) for s in sections):return {'errors':errors,'context_sha256':None}
    ids=[s.get('topic_id') for s in sections]
    need(all(isinstance(t,str) and t for t in ids) and len(set(str(t) for t in ids))==len(ids),'unique review IDs required')
    if expected:need(ids==expected,'review sections must cover retained topics in order')
    style=obj.get('citation_style');refstyle=obj.get('reference_style')
    style_basis=obj.get('reference_style_basis')
    need(style in {'numeric','author-year'} and bool(refstyle),'explicit citation and reference styles required')
    if report:
        need(style==report.get('citation_style') and refstyle==report.get('reference_style','basic'),'review style differs from report')
        need(style_basis==report.get('reference_style_basis'),'review reference style basis differs from report')
    source_path=(root/obj.get('sources_path','references.json')).resolve()
    need(source_path.parent==root.resolve(),'source ledger must be in the run directory')
    if errors:return {'errors':errors,'context_sha256':None}
    ledger=load(source_path);sources={s['source_id']:s for s in ledger['sources']}
    need(len(sources)==len(ledger['sources']),'duplicate source IDs')
    citations=report.get('citations',[]) if report else obj.get('citations',[])
    bibliography=report.get('bibliography',[]) if report else obj.get('bibliography',[])
    bib={b['source_id']:b for b in bibliography}
    need(len(bib)==len(bibliography),'duplicate bibliography sources')
    token_sources={}
    for c in citations:
        token=c.get('token');sid=c.get('source_id')
        need(isinstance(token,str) and bool(token),'citation token required')
        if token in token_sources:need(token_sources[token]==sid,'ambiguous citation token')
        token_sources[token]=sid
        need(sid in bib and sid in sources,'citation references an unknown source')
        if style=='numeric' and sid in bib:
            need(str(bib[sid].get('label','')).isdigit() and token=='['+str(bib[sid]['label'])+']','numeric citation registry differs from bibliography label')
    evidence={e['evidence_id']:e for e in ledger.get('evidence',[])}
    consumed={sid for s in sections for sid in s.get('source_ids',[]) if isinstance(sid,str)}
    manifest=load(root/'manifest.json') if (root/'manifest.json').is_file() else {}
    seen_cards=set()
    for item in manifest.get('inputs',[]):
        if item.get('card_path') and item.get('source_id') in consumed:
            card=(root/item['card_path']).resolve()
            if card.parent!= (root/'cards').resolve():raise ValueError('invalid reading card path')
            if card in seen_cards:continue
            seen_cards.add(card)
            for e in load(card).get('evidence',[]):
                need(e['evidence_id'] not in evidence,'duplicate evidence IDs')
                evidence[e['evidence_id']]=e
    occupied=[]
    def block(bounds,label):
        valid=isinstance(bounds,list) and len(bounds)==2 and all(type(n) is int for n in bounds) and 1<=bounds[0]<=bounds[1]<=len(lines)
        need(valid,label+': invalid final-text line range')
        if not valid:return ''
        need(not any(bounds[0]<=end and start<=bounds[1] for start,end in occupied),label+': review blocks overlap')
        occupied.append(tuple(bounds))
        return '\n'.join(lines[bounds[0]-1:bounds[1]])
    for section in sections:
        label=str(section.get('topic_id'));status=section.get('status')
        need(status in {'ready','limited'},label+': content review is unfinished')
        body=block(section.get('body_lines'),label+' body')
        refs=block(section.get('reference_lines'),label+' references')
        if not body or not refs:continue
        need(section['body_lines'][1]<section['reference_lines'][0],label+': references must follow review prose')
        need(bool(re.match(r'^#{1,6}\s+(?:参考文献|References)\s*(?:\n|$)',refs,re.I)),label+': local reference heading required')
        need(not cv.split_reference_sections(body)[1],label+': body range includes a bibliography')
        plain='\n'.join(''.join(v if k not in {'link','code'} else ' ' for k,v,_ in cv.inline_tokens(line)) for line in body.splitlines())
        forbidden_heading=re.search(
            r'^#{1,6}\s+.*(?:本题.*(?:问题|贡献)|研究设计|设计与实施|实施路径|'
            r'可行性|实施条件|条件、风险|风险与降级|降级方案|选题建议).*$' , body, re.M)
        need(not forbidden_heading,label+': review body includes research design, contribution, feasibility, or implementation advice')
        source_ids=section.get('source_ids',[]);eids=section.get('evidence_ids',[])
        need(isinstance(source_ids,list) and all(isinstance(s,str) for s in source_ids) and len(set(source_ids))==len(source_ids),label+': invalid source IDs')
        if errors:continue
        if style=='numeric':
            used_labels=vr.numeric_labels(body,markdown=True)
            mapping={str(b.get('label')):sid for sid,b in bib.items()}
            need(len(mapping)==len(bib),label+': duplicate numeric labels')
            need(used_labels<=mapping.keys(),label+': dangling numeric citation')
            used={mapping[n] for n in used_labels if n in mapping}
        else:
            used={sid for token,sid in token_sources.items() if token and token in plain}
        need(used==set(source_ids),label+': declared sources differ from body citations')
        entries=[]
        for sid in source_ids:
            need(sid in sources and sid in bib,label+': unknown source or bibliography entry '+sid)
            if sid not in sources or sid not in bib:continue
            s=sources[sid];entry=vr.reference_entry(s,refstyle)
            need(bib[sid].get('entry')==entry,label+': bibliography differs from canonical source '+sid)
            prefix='['+str(bib[sid]['label'])+'] ' if style=='numeric' else ''
            entries.append(prefix+entry)
            need(s.get('access_level') in {'abstract','fulltext'},label+': unread source '+sid)
            if status=='ready':
                need(s.get('verified') is True and not s.get('missing_fields'),label+': unverified reference '+sid)
                need(bool(s.get('required_fields')) and all(s.get(k) for k in set(s.get('required_fields',[]))|{'title','authors','year','publication'}),label+': incomplete reference '+sid)
        actual_entries=[line.strip() for line in refs.splitlines()[1:] if line.strip()]
        need(sorted(actual_entries)==sorted(entries),label+': local references must contain exactly the cited entries')
        if status=='ready':
            need(bool(source_ids),label+': no cited research')
            need(refstyle!='basic',label+': basic bibliography is not a verified paper citation style')
            need(isinstance(style_basis,str) and bool(style_basis.strip()),label+': verified review requires a reference style basis')
            need(all(section.get('checks',{}).get(k) is True for k in LITERATURE_CHECKS),label+': actual content acceptance checks required')
            headings=re.findall(r'^#{1,6}\s+(.+)$',body,re.M)
            generic={'文献综述','引言','研究述评','结语','结论','展望','结语与展望','参考文献'}
            themes=[re.sub(r'^[一二三四五六七八九十\d、.（）()\s]+','',h) for h in headings]
            need(any(h not in generic for h in themes),label+': review requires content-specific thematic headings')
            need(bool(re.search(r'^(?!\s*(?:#|\||[-*+]\s|\d+[.)]\s))\S.+',body,re.M)),label+': narrative review prose required')
            need(not re.search(r'^\s*(?:\*\*)?(?:已有研究做到哪一步|本题要增加的认识与差异|条件与风险)(?:\*\*)?[：:。]',body,re.M),label+': topic cards cannot replace review prose')
            need(isinstance(eids,list) and all(isinstance(e,str) and e in evidence for e in eids),label+': invalid evidence IDs')
            supported={evidence[e]['source_id'] for e in eids if isinstance(e,str) and e in evidence}
            need(set(source_ids)<=supported,label+': missing read evidence for cited sources')
            need(all(evidence[e].get('claim') and evidence[e].get('observed') and (evidence[e].get('pages') or evidence[e].get('locator')) and evidence[e].get('access_level') in {'abstract','fulltext'} for e in eids if isinstance(e,str) and e in evidence),label+': evidence lacks actual read content or location')
            need(not section.get('notice'),label+': ready review has an unresolved notice')
        elif status=='limited':
            notice=section.get('notice','')
            need(isinstance(notice,str) and '待补证综述稿' in notice and len(notice)>len('待补证综述稿') and notice in text,label+': limited draft must visibly state its specific limitation outside prose')
            need(not notice or notice not in body,label+': draft notice belongs outside copyable prose')
    if any(s.get('status')=='limited' for s in sections):
        need(not re.search(r'(?:全部|所有|每个|各题)?[^\n。]{0,16}综述[^\n。]{0,12}(?:可|可以|能够)直接(?:复制|粘贴|使用)',text),
             'blanket directly-copyable claim conflicts with limited literature review')
    consumed_evidence={eid for s in sections for eid in s.get('evidence_ids',[]) if isinstance(eid,str)}
    context={'sources':{sid:sources.get(sid) for sid in sorted(consumed)},
             'evidence':{eid:evidence.get(eid) for eid in sorted(consumed_evidence)},
             'citations':[c for c in citations if c.get('source_id') in consumed],
             'bibliography':{sid:bib.get(sid) for sid in sorted(consumed)},
             'citation_style':style,'reference_style':refstyle,
             'reference_style_basis':style_basis,'expected_topics':expected}
    context_sha=digest(json.dumps(context,ensure_ascii=False,sort_keys=True).encode())
    if record.get('status')=='passed':need(record.get('literature_context_sha256')==context_sha,'used sources or evidence changed after acceptance')
    return {'errors':errors,'context_sha256':context_sha}

def protected(text):
    """Conservative mechanical checks; meaning/units/attribution need real review."""
    out={};cv=markdown_tools()
    out['code']=Counter(re.findall(r'```[^\n]*\n.*?```|`[^`\n]+`',text,re.S))
    out['math']=Counter(re.findall(r'\$\$.*?\$\$|\$[^$\n]+\$|\\\[.*?\\\]|\\\(.*?\\\)',text,re.S))
    out['quotes']=Counter(re.findall(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]+"',text))
    out['links']=Counter(cv.markdown_links(text))
    _, bibliography = cv.split_reference_sections(text)
    out['bibliography']=Counter(line.strip() for line in bibliography.splitlines() if line.strip())
    plain=re.sub(r'```[^\n]*\n.*?```|`[^`\n]+`|<!--.*?-->','',text,flags=re.S)
    # Link labels may be edited, destinations may not. Reuse the converter parser.
    plain='\n'.join(''.join(value for _,value,_ in cv.inline_tokens(line)) for line in plain.splitlines())
    citations=re.findall(r'\[\d+(?:\s*[-,，]\s*\d+)*\]',plain)
    out['numeric_citations']=Counter(citations)
    # Numbered list markers are formatting, not research measurements.
    plain=re.sub(r'^\s*\d+[.)]\s+','',plain,flags=re.M)
    out['numbers']=Counter(re.findall(r'(?<![A-Za-z0-9_])[+−-]?\d+(?:[.,]\d+)*(?:[%‰])?(?![A-Za-z0-9_])',plain))
    return out


def design_context(source, text, root=None):
    """Bind only final designs and their used theory cards, not the whole library."""
    root=root or source.parent
    manifest=load(root/'manifest.json') if (root/'manifest.json').is_file() else {}
    if manifest.get('schema_version') not in {4,5,6}:return None,[]
    report=manifest.get('report') or {}
    if not report.get('markdown') or (root/report['markdown']).resolve()!=source.resolve():return None,[]
    topics=load(root/'topics.json').get('topics',[]) if (root/'topics.json').is_file() else []
    final=[t for t in topics if t.get('topic_id') in report.get('topic_ids',[])]
    design=run_tools().design_module()
    cards=design.used_theories(root,report['markdown'])
    terms=set()
    for topic in final:
        scope=topic.get('scope') or {}
        if isinstance(scope,dict):
            terms.update(value for key,value in scope.items() if key in {'region','population','unit','object','boundary'} and isinstance(value,str) and value in text)
        basis=topic.get('disciplinary_terms',[])
        terms.update(value for value in basis if isinstance(value,str) and value in text)
    for key in cards:
        name=design.theory_metadata(key,root if manifest.get('policy_version')=='3.0' else None).get('name')
        if name and name in text:terms.add(name)
    web=load(root/'web-feasibility.json') if (root/'web-feasibility.json').is_file() else {}
    data=[{'topic_id':r.get('topic_id'),'data_checks':r.get('data_checks',[])}
          for r in web.get('results',[]) if r.get('topic_id') in report.get('topic_ids',[])]
    context={'final_topics':final,'cards':cards,'policy_version':manifest.get('policy_version'),'core_data':data}
    return digest(json.dumps(context,ensure_ascii=False,sort_keys=True).encode()),sorted(terms)

def atomic_record(path,obj):
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.language-review-',delete=False) as f:
        tmp=Path(f.name)
        try:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
        except BaseException:tmp.unlink();raise
    try:os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def prepare(source,record):
    source,record=source.resolve(),record.resolve()
    snapshot=record.with_suffix('.before.md')
    if record.exists() or snapshot.exists():raise FileExistsError('review or input snapshot already exists; use a new review filename')
    if source in {record,snapshot}:raise ValueError('review output collides with source')
    raw=source.read_bytes();text=raw.decode('utf-8')
    block_units=units(text)
    root=context_root(source,record)
    design_sha,design_terms=design_context(source,text,root)
    if not block_units:raise ValueError('empty document cannot be reviewed')
    obj={'schema_version':2,'version':1,'status':'pending',
        'source_path':os.path.relpath(source,record.parent),'snapshot':snapshot.name,
        'original_sha256':digest(raw),'policy_sha256':digest(POLICY.read_bytes()),
        'units':block_units,'reviewed_units':[],'issues':scan(text),'protected_terms':[],
        'checks':{key:False for key in CHECKS},'reviewer':None,
        'reviewer_type':None,'human_reviewer':None,
        'final_sha256':None,'completed_at':None,'literature':literature_template(source,root),
        'literature_context_sha256':None,'design_context_sha256':design_sha,
        'design_protected_terms':design_terms}
    record.parent.mkdir(parents=True,exist_ok=True)
    # Publish the pair without clobbering another run's snapshot or review.
    with tempfile.TemporaryDirectory(prefix='.language-prepare-',dir=record.parent) as d:
        raw_path=Path(d)/'before';raw_path.write_bytes(raw)
        json_path=Path(d)/'review';json_path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.link(raw_path,snapshot)
        try:os.link(json_path,record)
        except BaseException:snapshot.unlink();raise
    return {'record':str(record),'units':len(block_units),'candidates':len(obj['issues']),
            'status':'pending','scope':'cues only; read every unit and actually revise before seal'}

def covered_ids(values,allowed):
    if not isinstance(values,list):raise ValueError('reviewed_units must be an array')
    covered=set()
    for value in values:
        if not isinstance(value,str):raise ValueError('invalid coverage unit')
        match=re.fullmatch(r'U(\d{5})(?:-U(\d{5}))?',value)
        if not match:raise ValueError('coverage expects U00001 or U00001-U00009')
        first,last=int(match[1]),int(match[2] or match[1])
        if first>last or last-first>len(allowed):raise ValueError('invalid coverage range')
        expanded={f'U{i:05d}' for i in range(first,last+1)}
        if not expanded<=allowed:raise ValueError('coverage includes unknown units')
        if covered & expanded:raise ValueError('duplicate coverage units')
        covered|=expanded
    return covered

def validate(source,record,sealing=False,run_root=None):
    source,record=source.resolve(),record.resolve();errors=[]
    def need(condition,message):
        if not condition:errors.append(message)
    obj=load(record)
    need(obj.get('schema_version')==2 and type(obj.get('version')) is int and obj['version']>0,'review schema changed; prepare a new content/language review')
    need(obj.get('status') in {'pending','passed'},'invalid language review status')
    need((record.parent/obj['source_path']).resolve()==source,'review belongs to another source')
    snapshot=(record.parent/obj['snapshot']).resolve()
    need(snapshot.parent==record.parent and snapshot!=source,'invalid input snapshot path')
    if errors:return {'errors':errors}
    before_raw=snapshot.read_bytes();before=before_raw.decode('utf-8');after_raw=source.read_bytes();after=after_raw.decode('utf-8')
    root=context_root(source,record,run_root)
    design_sha,design_terms=design_context(source,before,root)
    need(obj.get('design_context_sha256')==design_sha,'final scope, theory or decision changed after content freeze')
    need(obj.get('design_protected_terms',[])==design_terms,'protected design terms changed')
    for term in design_terms:need(term in after,'protected scope/theory terminology missing: '+term)
    need(digest(before_raw)==obj.get('original_sha256'),'input snapshot changed')
    need(obj.get('policy_sha256')==digest(POLICY.read_bytes()),'editorial policy changed; review must be renewed')
    expected_units=units(before);need(bool(expected_units),'empty review input')
    need(obj.get('units')==expected_units,'input unit coverage metadata changed')
    if errors:return {'errors':errors}
    by_id={u['unit_id']:u for u in expected_units}
    coverage=covered_ids(obj.get('reviewed_units',[]),set(by_id))
    need(coverage==set(by_id),'full-text coverage incomplete, including tables/headings/references/appendices')
    need(bool(obj.get('reviewer')) and isinstance(obj['reviewer'],str),'actual reviewer required')
    reviewer_type=obj.get('reviewer_type')
    need(reviewer_type in {'model','human','mixed'},'reviewer_type must be model, human, or mixed')
    if reviewer_type in {'human','mixed'}:
        need(isinstance(obj.get('human_reviewer'),str) and bool(obj['human_reviewer'].strip()),
             'human or mixed review requires the actual human reviewer')
    if reviewer_type=='model':
        need(not re.search(r'人工(?:核定|复核|审核|审校)',obj.get('reviewer','')),
             'model-only review cannot claim human approval')
    for key in CHECKS:need(obj.get('checks',{}).get(key) is True,'editorial check not confirmed: '+key)
    issues=obj.get('issues',[]);need(isinstance(issues,list),'issues must be an array')
    indexed={};changed_units=set();before_lines=before.splitlines();after_lines=after.splitlines()
    touched=set()
    for op,i,j,_,_ in difflib.SequenceMatcher(None,before_lines,after_lines,autojunk=False).get_opcodes():
        if op=='equal':continue
        if op=='insert':touched.add(min(max(i,0),len(before_lines)-1)+1)
        else:touched.update(range(i+1,j+1))
    for issue in issues:
        iid=issue.get('issue_id');need(isinstance(iid,str) and bool(iid) and iid not in indexed,'missing/duplicate issue id')
        indexed[iid]=issue
        affected=issue.get('units',[])
        need(isinstance(affected,list) and bool(affected) and all(u in by_id for u in affected),'issue has invalid unit scope: '+str(iid))
        if not isinstance(affected,list) or not affected or not all(u in by_id for u in affected):continue
        original='\n'.join(before_lines[by_id[u]['line']-1] for u in affected)
        need(isinstance(issue.get('before'),str) and bool(issue['before']) and issue['before'] in original,'issue lacks real original text: '+str(iid))
        action=issue.get('action');need(action in {'revised','deleted','retained'},'unresolved issue: '+str(iid))
        need(bool(issue.get('reason')) and isinstance(issue['reason'],str),'issue needs a specific reason: '+str(iid))
        if action in {'revised','deleted'}:
            need(any(by_id[u]['line'] in touched for u in affected),'claimed edit has no change at its source unit: '+str(iid))
            changed_units.update(affected)
            if action=='revised':need(bool(issue.get('after')) and isinstance(issue['after'],str) and issue['after'] in after and issue['after']!=issue.get('before'),'replacement missing from final text: '+str(iid))
        elif action=='retained':need(issue.get('before','') in after,'retained expression missing from final text: '+str(iid))
    for candidate in scan(before):
        actual=indexed.get(candidate['issue_id'],{})
        need(all(actual.get(k)==candidate[k] for k in ['units','pattern','before']),'original candidate removed or altered: '+candidate['issue_id'])
    need({u['unit_id'] for u in expected_units if u['line'] in touched}<=changed_units,'some edited/inserted text lacks an issue record')
    original_protected,final_protected=protected(before),protected(after)
    for category in original_protected:need(original_protected[category]==final_protected[category],'protected content changed: '+category)
    terms=obj.get('protected_terms',[]);need(isinstance(terms,list),'protected_terms must be an array')
    for term in terms:
        need(isinstance(term,str) and bool(term) and term in before and term in after,'protected terminology missing: '+str(term))
    literature=validate_literature(source,obj,root)
    errors.extend(literature['errors'])
    if not sealing:
        need(obj.get('status')=='passed','language review not sealed')
        need(obj.get('final_sha256')==digest(after_raw),'final text changed after language review')
        need(bool(obj.get('completed_at')),'missing language review completion time')
        if obj.get('completed_at'):need(datetime.fromisoformat(obj['completed_at']).utcoffset() is not None,'language review date requires timezone')
    return {'errors':errors,'units':len(expected_units),'issues':len(issues),'final_sha256':digest(after_raw),
            'literature_context_sha256':literature['context_sha256'],
            'scope':'coverage/version/mechanical fidelity only; the agent must perform real semantic editing'}

def seal(source,record):
    if load(record).get('status')=='passed':return validate(source,record)
    result=validate(source,record,sealing=True)
    if result['errors']:return result
    if digest(source.read_bytes())!=result['final_sha256']:return {'errors':['source changed while sealing language review']}
    obj=load(record);obj.update(status='passed',final_sha256=result['final_sha256'],
        literature_context_sha256=result['literature_context_sha256'],completed_at=datetime.now().astimezone().isoformat())
    atomic_record(record,obj);return result

def require_passed(source,record=None,run_root=None):
    record=record or source.parent/'language-review.json'
    if not record.is_file():raise ValueError('full-text language review required before Markdown delivery: run review_language.py prepare, actually review/edit, then seal')
    try:result=validate(source,record,run_root=run_root)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:raise ValueError('invalid language review: '+str(exc)) from exc
    if result['errors']:raise ValueError('language review failed: '+'; '.join(result['errors']))
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','seal','check'])
    parser.add_argument('source',type=Path);parser.add_argument('record',type=Path)
    args=parser.parse_args(argv)
    try:
        source,record=args.source.expanduser(),args.record.expanduser()
        result=prepare(source,record) if args.command=='prepare' else seal(source,record) if args.command=='seal' else validate(source,record)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:result={'errors':[str(exc)]}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result.get('errors') else 0

if __name__=='__main__':raise SystemExit(main())
