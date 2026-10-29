"""Immutable compressed evidence in a small Git branch, not Actions artifacts/LFS."""
import gzip
import hashlib
import json
import re
import threading
from pathlib import Path
from .sources import MAX_BYTES
from .security import public_body

HASH=re.compile(r'[0-9a-f]{64}')
STATE_FILES=('sources.json','source-history.json','schedules.json','polling.json',
             'monitor-state.json','publication-observations.json')


def load(path,default):
    return json.loads(Path(path).read_text()) if Path(path).is_file() else default


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


class Archive:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.Lock()
    def path(self,digest):
        if not isinstance(digest,str) or not HASH.fullmatch(digest):raise ValueError('Invalid archive hash')
        return self.root/'raw'/digest[:2]/(digest+'.body.gz')
    def add(self,body):
        with self.lock:return self._add(body)
    def _add(self,body):
        if len(body)>MAX_BYTES:raise ValueError('Raw body exceeds cap')
        if public_body(body)!=body:raise ValueError('Credential-bearing body blocked from public archive')
        digest=hashlib.sha256(body).hexdigest();target=self.path(digest)
        if target.is_file():
            if self.read(digest)!=body:raise ValueError('Archive hash/body mismatch')
            return digest
        target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_suffix('.tmp');temp.write_bytes(gzip.compress(body,mtime=0));temp.replace(target)
        return digest
    def read(self,digest):
        with gzip.open(self.path(digest),'rb') as f:body=f.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES or hashlib.sha256(body).hexdigest()!=digest:
            raise ValueError('Corrupt/oversize archived source; refuse fresh verification')
        if public_body(body)!=body:raise ValueError('Credential-bearing historical archive requires sanitization')
        return body
    def restore(self,state):
        state=Path(state);state.mkdir(parents=True,exist_ok=True)
        legacy=not (self.root/'state').exists() and any((self.root/n).is_file() for n in STATE_FILES)
        gaps=load(self.root/'legacy-archive-gaps.json',{'missingHistoricalBodyHashes':[]})
        for name in STATE_FILES:
            src=self.root/'state'/name
            if legacy:src=self.root/name
            if src.is_file():
                # Invalid state stops the run; never silently reset evidence history.
                write(state/name,json.loads(src.read_text()))
        # Restore only current bodies needed for conditional requests/PDF extraction.
        for record in load(state/'sources.json',{}).values():
            for field in ('sha256','errorBodySha256'):
                digest=record.get(field)
                if digest:
                    if not self.path(digest).is_file():
                        if legacy or digest in gaps['missingHistoricalBodyHashes']:
                            if digest not in gaps['missingHistoricalBodyHashes']:gaps['missingHistoricalBodyHashes'].append(digest)
                            continue
                        raise ValueError('Archive missing retained source body: '+digest)
                    (state/(digest+'.body')).write_bytes(self.read(digest))
        if gaps['missingHistoricalBodyHashes']:
            gaps['note']='Legacy workflow did not preserve these raw bodies; metadata and selected verified snapshots retained. Refetch needed, no stale re-verification.'
            write(self.root/'legacy-archive-gaps.json',gaps)
    def checkpoint(self,state):
        state=Path(state)
        for src in state.glob("*.body"):self.add(src.read_bytes())
        for name in STATE_FILES:
            src=state/name
            if src.is_file():write(self.root/"state"/name,json.loads(src.read_text()))

    def persist(self,state,report):
        self.checkpoint(state)
        state=Path(state)
        write(self.root/'latest.json',report)
        encoded=json.dumps(report,ensure_ascii=False,sort_keys=True).encode()
        digest=hashlib.sha256(encoded).hexdigest()
        day=report['checkedAt'][:10]
        target=self.root/'checks'/day/(report['checkedAt'].replace(':','-')+'-'+digest[:12]+'.json.gz')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(gzip.compress(encoded,mtime=0))
        index=load(self.root/'index.json',{'schemaVersion':1,'checks':[]})
        if not any(i['file']==str(target.relative_to(self.root)) for i in index['checks']):
            index['checks'].append({'checkedAt':report['checkedAt'],'file':str(target.relative_to(self.root)),
                                    'status':report['status'],'firstPublication':bool(report.get('firstPublicationDetected'))})
        write(self.root/'index.json',index)
    def size(self):
        return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts)
