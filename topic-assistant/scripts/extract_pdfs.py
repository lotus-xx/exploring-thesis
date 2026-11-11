#!/usr/bin/env python3
"""Read-only PDF extraction with per-page quality, optional local OCR, no overwrite.

Python 3.9+; requires pdftotext+pdfinfo, PDFKit+clang, or optional pypdf.
Extraction is NOT evidence of actual reading. Exit 3 means pages need review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


def list_pdfs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError(f"not a directory: {folder}")
    return sorted((p for p in folder.iterdir() if p.is_file() and
                   p.suffix.lower() == '.pdf' and not p.name.startswith('.')),
                  key=lambda p: (p.name.casefold(), p.name))


def run(args: list[str], timeout: int = 180) -> str:
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8', errors='replace')[:800] or
                           f"command failed ({p.returncode}): {args[0]}")
    return p.stdout.decode('utf-8', errors='replace')


def pdfkit_binary(cache_dir: Path | None) -> Path:
    if sys.platform != 'darwin' or not shutil.which('clang'):
        raise RuntimeError('macOS PDFKit/clang unavailable')
    source = Path(__file__).with_name('pdfextract.m')
    key = hashlib.sha256(source.read_bytes() +
                         (platform.machine()+platform.platform()).encode()).hexdigest()[:20]
    cache = cache_dir or Path(tempfile.gettempdir()) / 'topic-assistant-cache'
    cache.mkdir(parents=True, exist_ok=True)
    binary = cache / ('pdfextract-' + key)
    if binary.is_file():
        return binary
    clang = shutil.which('clang')
    sdks = sorted(Path('/Library/Developer/CommandLineTools/SDKs').glob('MacOSX*.sdk'),
                  key=lambda p: p.name, reverse=True)
    # Compile for the host architecture only. Separate temporary builds and atomic
    # publication prevent simultaneous runs from corrupting a shared executable.
    with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as tmp:
        temp_binary = Path(tmp) / 'pdfextract'
        base = [clang, '-arch', platform.machine(), '-fobjc-arc', '-framework',
                'Foundation', '-framework', 'PDFKit', '-O2', str(source), '-o', str(temp_binary)]
        errors = []
        for command in [base] + [base + ['-isysroot', str(s)] for s in sdks]:
            try:
                run(command, 120)
                try:
                    os.link(temp_binary, binary)
                except FileExistsError:
                    pass  # Another successful compiler already published this key.
                return binary
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                errors.append(str(exc))
        raise RuntimeError('PDFKit build failed: ' + '; '.join(errors)[-1200:])


def extract_backend(pdf: Path, backend: str, cache: Path | None, selected=None) -> list[dict]:
    if backend == 'pdftotext':
        if not shutil.which('pdftotext') or not shutil.which('pdfinfo'):
            raise RuntimeError('pdftotext/pdfinfo unavailable')
        info = run(['pdfinfo', str(pdf)])
        match = re.search(r'^Pages:\s+(\d+)', info, re.M)
        if not match:
            raise RuntimeError('pdfinfo did not report page count')
        n = int(match.group(1))
        if selected is None:
            chunks = run(['pdftotext','-layout','-enc','UTF-8',str(pdf),'-']).split('\f')
            if len(chunks)==n+1 and not chunks[-1].strip(): chunks.pop()
            if len(chunks)!=n: raise RuntimeError('pdftotext page separators disagree with pdfinfo')
            return [{'page':i,'text':text,'error':None} for i,text in enumerate(chunks,1)]
        pages = []
        for i in sorted(selected):
            try:
                text = run(['pdftotext', '-f', str(i), '-l', str(i), '-layout',
                            '-enc', 'UTF-8', str(pdf), '-']).replace('\f', '')
                pages.append({'page': i, 'text': text, 'error': None})
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                pages.append({'page': i, 'text': '', 'error': str(exc)})
        return pages
    if backend == 'pdfkit':
        argv=[str(pdfkit_binary(cache)),str(pdf)]
        if selected is not None: argv.append(','.join(map(str,sorted(selected))))
        obj = json.loads(run(argv))
        if (len(selected) if selected is not None else obj.get('total_pages')) != len(obj.get('pages', [])):
            raise RuntimeError('PDFKit inconsistent page count')
        return obj['pages']
    if backend == 'pypdf':
        from pypdf import PdfReader
        reader = PdfReader(str(pdf))
        if reader.is_encrypted and not reader.decrypt(''):
            raise RuntimeError('password-protected PDF')
        pages = []
        for i in (sorted(selected) if selected is not None else range(1,len(reader.pages)+1)):
            try:
                page=reader.pages[i-1]
                pages.append({'page': i, 'text': page.extract_text() or '', 'error': None})
            except Exception as exc:
                pages.append({'page': i, 'text': '', 'error': str(exc)})
        return pages
    raise ValueError(f'unknown backend: {backend}')


def assess(pages: list[dict]) -> None:
    """Conservative heuristic: discard numeric/repeated edge lines for scoring only.
    Original text is retained. Short genuine pages still require human review.
    """
    edges = Counter()
    for p in pages:
        lines = [s.strip() for s in p['text'].splitlines() if s.strip()]
        edges.update(set(lines[:2] + lines[-2:]))
    repeated = {s for s, n in edges.items() if len(pages) >= 3 and n >= max(3, len(pages)*.6)}
    for p in pages:
        lines = [s.strip() for s in p['text'].splitlines() if s.strip()]
        scored = []
        for j, line in enumerate(lines):
            edge = j < 2 or j >= len(lines)-2
            if re.fullmatch(r'[\d\W_]+', line):
                continue
            if edge and (line in repeated or re.fullmatch(
                    r'(?:page|第)?\s*\d+\s*(?:/\s*\d+|页)?', line, re.I)):
                continue
            scored.append(line)
        useful = sum(c.isalnum() for c in '\n'.join(scored))
        bad = p['text'].count('\ufffd') + sum(ord(c) < 32 and c not in '\n\r\t' for c in p['text'])
        p['meaningful_chars'] = useful
        p['raw_chars'] = len(p['text'])
        p['method'] = p.get('method', 'text_layer')
        if p.get('error'):
            p['status'] = 'error'
        elif not p['text'].strip():
            p['status'] = 'empty'
        elif useful < 40 or bad/max(1, len(p['text'])) > .02:
            p['status'] = 'review_required'
        else:
            p['status'] = 'text_ready'


def ocr_pages(pdf: Path, pages: list[dict], lang: str, command: list[str] | None = None,
              selected: set[int] | None = None, ocr_key=None) -> list[str]:
    targets=[p for p in pages if (p['page'] in selected if selected is not None else p['status']!='text_ready')
             and not (ocr_key and p.get('ocr_key')==ocr_key and p.get('method')=='local_ocr' and not p.get('ocr_error'))]
    if not targets: return []
    if not shutil.which('pdftoppm') or (not command and not shutil.which('tesseract')):
        reason = 'local OCR unavailable: requires pdftoppm and a local tesseract or explicit local adapter'
        for page in targets:
            page['ocr_error'] = reason
            page['status'] = 'review_required'
        return [reason]
    if command and (not all(isinstance(x,str) for x in command) or not any('{image}' in x for x in command)):
        raise ValueError('OCR adapter must be an argv array containing {image}; no shell is used')
    errors = []
    for page in targets:
        try:
            with tempfile.TemporaryDirectory(prefix='topic-ocr-') as tmp:
                prefix = str(Path(tmp) / 'page')
                run(['pdftoppm', '-f', str(page['page']), '-l', str(page['page']),
                     '-singlefile', '-scale-to', '2400', '-png', str(pdf), prefix])
                if command:
                    argv = [part.replace('{image}',prefix+'.png').replace('{lang}',lang) for part in command]
                    result = json.loads(run(argv,240))
                    text,confidence = result['text'],result.get('confidence')
                    if not isinstance(text,str): raise ValueError('OCR adapter text must be a string')
                else:
                    run(['tesseract',prefix+'.png',prefix+'-ocr','-l',lang,'txt','tsv'],240)
                    text = Path(prefix+'-ocr.txt').read_text(encoding='utf-8')
                    rows = list(csv.DictReader(Path(prefix+'-ocr.tsv').read_text(encoding='utf-8').splitlines(),delimiter='\t'))
                    values = [float(r['conf']) for r in rows if r.get('text','').strip() and float(r['conf'])>=0]
                    confidence = sum(values)/len(values) if values else None
                if page.get('method')!='local_ocr': page['text_before_ocr'] = page['text']
                page['text'] = text
                page['method'] = 'local_ocr'
                page['ocr_confidence'] = confidence
                page['ocr_language'] = lang
                page['ocr_key'] = ocr_key
                page.pop('ocr_error',None)
                page['error'] = None
                assess([page])
                # OCR can silently misread numbers/figures: never auto-pass it.
                page['status'] = 'ocr_review_required'
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            page['ocr_error'] = str(exc)
            page['status'] = 'review_required'
            errors.append(f"page {page['page']}: {exc}")
    return errors


def object_digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def processing_keys(backend,lang,command,model_key):
    tools={}
    for name in ['pdftotext','pdfinfo','clang','pdftoppm','tesseract']+list(command or []):
        p=Path(shutil.which(name) or name)
        if p.is_file():
            st=p.stat();tools[name]=[str(p.resolve()),st.st_size,st.st_mtime_ns]
    try: version=importlib.metadata.version('pypdf')
    except importlib.metadata.PackageNotFoundError: version=None
    code=hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('pdfextract.m').read_bytes()).hexdigest()
    base=object_digest({'code':code,'backend':backend,'tools':tools,'python':sys.version,'pypdf':version,'platform':platform.platform()})
    return base,object_digest({'base':base,'lang':lang,'command':command,'model_key':model_key})


def extract(pdf: Path, backend='auto', cache: Path | None = None,
            ocr=False, lang='chi_sim+eng', ocr_command=None, ocr_selected=None,
            reuse_quality=None, ocr_model_key=None) -> dict:
    if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
        raise ValueError(f'not a PDF file: {pdf}')
    source_hash=hashlib.sha256(pdf.read_bytes()).hexdigest()
    text_key,ocr_key=processing_keys(backend,lang,ocr_command,ocr_model_key)
    errors,pages,chosen,reused=[],None,None,False
    if reuse_quality:
        old=json.loads(Path(reuse_quality).read_text(encoding='utf-8'))
        integrity=old.pop('result_digest',None)
        if (integrity==object_digest(old) and old.get('sha256')==source_hash and old.get('text_key')==text_key
                and (not ocr or ocr_model_key)):
            pages=old['pages'];chosen=old['backend'];reused=True
            if [p['page'] for p in pages]!=list(range(1,old['total_pages']+1)): raise ValueError('cached page coverage mismatch')
            if not ocr:
                for p in pages:
                    if p.get('method')=='local_ocr':
                        p['text']=p['text_before_ocr'];p['method']='text_layer'
                        for key in ['ocr_key','ocr_confidence','ocr_language','ocr_error']:p.pop(key,None)
                assess(pages)
    for name in (['pdftotext', 'pdfkit', 'pypdf'] if backend == 'auto' else [backend]):
        if pages is not None: break
        try:
            candidate = extract_backend(pdf, name, cache)
            if not candidate:
                raise RuntimeError('PDF contains no pages')
            if [p['page'] for p in candidate]!=list(range(1,len(candidate)+1)): raise RuntimeError('backend page coverage mismatch')
            pages,chosen=candidate,name
            assess(pages)
        except Exception as exc:
            errors.append({'backend': name, 'error': str(exc)[:1500]})
    if pages is None:
        raise RuntimeError('all extraction backends failed: '+json.dumps(errors, ensure_ascii=False))
    # Sparse/scanned pages go straight to OCR/visual review. Only actual text
    # extraction errors justify another backend, restricted to affected pages.
    affected={p['page'] for p in pages if p.get('error')}
    if backend=='auto' and affected and not reused:
        for name in ['pdftotext','pdfkit','pypdf']:
            if name==chosen or not affected: continue
            try:
                fixed=extract_backend(pdf,name,cache,affected)
                if {p['page'] for p in fixed}!=affected: raise RuntimeError('targeted backend page coverage mismatch')
                for p in fixed:
                    if not p.get('error'): p['backend']=name;pages[p['page']-1]=p
                affected={p['page'] for p in pages if p.get('error')}
            except Exception as exc: errors.append({'backend':name,'pages':sorted(affected),'error':str(exc)[:1500]})
        assess(pages)
    if ocr_selected and not ocr_selected <= set(range(1,len(pages)+1)):
        raise ValueError('OCR page selection out of range')
    ocr_errors = ocr_pages(pdf,pages,lang,ocr_command,ocr_selected,ocr_key if ocr_model_key else None) if ocr else []
    pending = [p['page'] for p in pages if p['status'] != 'text_ready']
    result={'schema_version': 2, 'source_path': str(pdf.resolve()),
            'sha256': source_hash, 'backend': chosen,'text_key':text_key,'reused_extraction':reused,
            'total_pages': len(pages), 'status': 'review_required' if pending else 'text_ready',
            'review_pages': pending, 'actual_reading': 'not_recorded',
            'backend_errors': errors, 'ocr_errors': ocr_errors, 'pages': pages}
    result['result_digest']=object_digest(result)
    return result


def ensure_output(out):
    if out.suffix=='.json':raise ValueError('text output must not have .json extension')
    if out.exists() or out.with_suffix('.json').exists():raise FileExistsError(f'output already exists: {out}')


def publish_pair(out: Path, payload: dict) -> None:
    sidecar = out.with_suffix('.json')
    ensure_output(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = '\n\n'.join(f"--- page {p['page']} / {payload['total_pages']} [{p['status']}] ---\n{p['text']}"
                       for p in payload['pages'])
    with tempfile.TemporaryDirectory(prefix='.extract-', dir=out.parent) as tmp:
        t, j = Path(tmp)/'text', Path(tmp)/'json'
        t.write_text(text, encoding='utf-8')
        j.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        os.link(t, out)  # Atomic no-clobber publication, including concurrent runs.
        try:
            os.link(j, sidecar)
        except Exception:
            out.unlink()  # Only undo the text file just created by this invocation.
            raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ls = sub.add_parser('list'); ls.add_argument('folder', type=Path)
    for name in ['extract', 'batch']:
        p = sub.add_parser(name)
        p.add_argument('source', type=Path); p.add_argument('output', type=Path)
        p.add_argument('--backend', choices=['auto','pdftotext','pdfkit','pypdf'], default='auto')
        p.add_argument('--cache-dir', type=Path)
        p.add_argument('--ocr', action='store_true')
        p.add_argument('--ocr-lang', default='chi_sim+eng')
        p.add_argument('--ocr-command-json', help='explicit local OCR argv array; {image}/{lang}; stdout JSON text/confidence')
        p.add_argument('--ocr-pages', help='explicit comma-separated physical page numbers, also for text-ready pages')
        p.add_argument('--reuse-quality',type=Path,help='reuse a matching, intact previous quality JSON; single-file extract only')
        p.add_argument('--ocr-model-key',help='explicit local OCR model/config fingerprint, required for OCR cache reuse')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            files = list_pdfs(args.folder.expanduser())
            print(json.dumps({'count':len(files), 'pdfs':[{'file':p.name,'path':str(p.resolve())} for p in files]}, ensure_ascii=False, indent=2))
            return 0
        files = list_pdfs(args.source.expanduser()) if args.command == 'batch' else [args.source.expanduser()]
        results, failures, review = [], [], False
        for i, pdf in enumerate(files, 1):
            out = args.output / f'{i:04d}-{pdf.stem}.txt' if args.command == 'batch' else args.output
            try:
                out=out.expanduser();ensure_output(out)
                if args.command=='batch' and args.reuse_quality:raise ValueError('--reuse-quality requires single-file extract')
                adapter = json.loads(args.ocr_command_json) if args.ocr_command_json else None
                if adapter is not None and (not isinstance(adapter,list) or not adapter):
                    raise ValueError('OCR adapter must be a nonempty JSON argv array')
                selected = {int(p) for p in args.ocr_pages.split(',')} if args.ocr_pages else None
                if not args.ocr and (adapter or selected): raise ValueError('OCR options require --ocr')
                payload = extract(pdf,args.backend,args.cache_dir,args.ocr,args.ocr_lang,adapter,selected,args.reuse_quality,args.ocr_model_key)
                publish_pair(out.expanduser(), payload)
                results.append({'file':pdf.name,'text_path':str(out.resolve()),
                                'quality_path':str(out.with_suffix('.json').resolve()),
                                'total_pages':payload['total_pages'],'status':payload['status']})
                review |= payload['status'] != 'text_ready'
            except Exception as exc:
                failures.append({'file':pdf.name,'error':str(exc)})
        print(json.dumps({'ok':results,'failed':failures,'count':len(results)}, ensure_ascii=False, indent=2))
        return 1 if failures else 3 if review else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
