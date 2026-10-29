"""Replay exact captured responses without network access."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from .live_api import collect_live, BASE
from .html import discover
from .pipeline import build_rows
from .pdf import timetable
from .programme import pdf_revision
from .revisions import choose, version


class CapturedClient:
    def __init__(self, root):
        self.root=Path(root)/'fixtures/real/live-api'
        if not (self.root/'manifest.json').is_file():
            raise ValueError('Historical captures are local-only and absent. Use synthetic-sample; no substitute is presented as real evidence.')
        self.manifest=json.loads((self.root/'manifest.json').read_text())
        self.sources={r['url']:r for r in self.manifest['sources']}
        self.records={}

    def get(self,url):
        record=self.sources.get(url)
        if not record:
            return None,{'url':url,'status':'unavailable','error':'Not present in captured fixture set'}
        body=(self.root/record['file']).read_bytes()
        if hashlib.sha256(body).hexdigest()!=record['sha256']:
            raise ValueError('Captured source hash mismatch')
        self.records[url]=record
        return body,record

    def query(self,path,fields):
        return self.get(BASE+path+'?'+urlencode(sorted(fields.items())))


def replay(root):
    root=Path(root);client=CapturedClient(root)
    events=json.loads((root/'config/events.json').read_text())
    aliases=json.loads((root/'config/athletes.json').read_text())
    reference=json.loads((root/'config/site-reference.json').read_text())
    results=[]
    for event in events:
        raw,_=client.get(event['infoUrl'])
        page=discover(raw.decode(),event['infoUrl'],event)
        ids={int(m['id']) for m in page['metadata'] if str(m.get('id','')).isdigit()}
        cms_id=next(iter(ids)) if len(ids)==1 and page['identityVerified'] else None
        rows,people,evidence=collect_live(event,client,page['identityVerified'],cms_id)
        ref=next((r for r in reference['events'] if r['id']==event['id']),{})
        result=build_rows(event,rows,people,aliases,ref,evidence['issues'])
        result['liveApi']=evidence
        for comparison in result['comparison']:
            if comparison['status']!='match':comparison['assessment']='Unresolved source/revision difference; does not establish that website times were incorrect.'
        api_version=version(event,'online',evidence['programmeSource']['url'],rows,evidence['programmeSource'],{},evidence['issues'])
        versions=[api_version]
        if event['id']=='2026-27-wt1':
            meta=json.loads((root/'fixtures/real/manifest.json').read_text())
            text=(root/'fixtures/real/vancouver-protocol-extract.txt').read_text()
            pdf_rows,errors=timetable(text,event,meta['protocolUrl'])
            versions.append(version(event,'pdf',meta['protocolUrl'],pdf_rows,{'sha256':meta['protocolSha256'],'fetchedAt':meta['capturedAt']},pdf_revision(text,event),errors))
        decision=choose(versions)
        result['scheduleAuthority']={k:v for k,v in decision.items() if k!='selected'}
        result['notes']+=['Captured-source replay; no network requests.', 'API candidate times do not establish which programme was authoritative before racing.']
        result['calendarPatchCandidate']=None  # Capture analysis is not a publication feed.
        result['validationType']='actual-captured-source'
        if decision['status']!='resolved':result['verificationStatus']='needs-review'
        results.append(result)
    return {'mode':'read-only-captured-api-validation','events':results,'sources':client.records,'approvedForWebsite':False}
