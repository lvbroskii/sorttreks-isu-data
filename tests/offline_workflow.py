"""End-to-end workflow rehearsal with synthetic HTTP and local Git only."""
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import urllib.error
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from isu_pilot.archive import Archive,load,write
from isu_pilot.monitor import run
from isu_pilot.sources import Client
from isu_pilot.synthetic import SyntheticClient,programme,metadata,heats,event_html,encode,KIND

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[1]


def shift(value,phase):
    if isinstance(value,list):return [shift(v,phase) for v in value]
    if isinstance(value,dict):
        result={k:shift(v,phase) for k,v in value.items()}
        if 'event_id' in result:result['event_id']=16272
        # One revised round, no changed starting-round identity.
        if phase=='revised':
            if result.get('event_result_round_id')==22870 and 'start_time' in result:
                dt=datetime.fromisoformat(result['start_time']);result['start_time']=(dt+timedelta(minutes=5)).isoformat()
        return result
    if isinstance(value,str) and value.startswith('2026-10-') and 'T' in value:
        return (datetime.fromisoformat(value.replace('Z','+00:00'))+timedelta(days=7)).isoformat()
    return value


class RehearsalClient(Client):
    phase='empty'
    def __init__(self,state,previous,**kwargs):
        phase=type(self).phase
        class Response(io.BytesIO):
            status=200
            def __init__(self,body,url,mime):
                super().__init__(body);self.url=url
                self.headers={'Content-Type':mime,'ETag':hashlib.sha256(body).hexdigest()}
        def transport(req,**kw):
            url=req.full_url;body=None;mime='application/json'
            if url.split('?')[0]==EVENT['infoUrl']:
                body=event_html(EVENT,1).encode();mime='text/html'
            elif '/events/getschedule/' in url:
                if phase=='failed':raise OSError('Synthetic source failure')
                if phase=='empty':
                    from isu_pilot.synthetic import empty
                    body=encode(empty())
                else:body=encode(shift(programme(),phase))
            elif req.data:
                fields=parse_qs(req.data.decode())
                if url.endswith('/events/get-event-result-round'):
                    body=encode(shift(metadata(int(fields['event_result_id'][0])),phase))
                elif url.endswith('/events/get-event-result-round-heats-stk-single'):
                    body=encode(shift(heats(int(fields['event_result_round_id'][0])),phase))
            if body is None:
                raise urllib.error.HTTPError(url,404,'Synthetic missing response',{},io.BytesIO(b'{"code":404,"message":"SYNTHETIC missing"}'))
            digest=hashlib.sha256(body).hexdigest()
            if req.get_header('If-none-match')==digest:
                raise urllib.error.HTTPError(url,304,'Not modified',{},io.BytesIO())
            return Response(body,url,mime)
        super().__init__(state,previous,transport=transport,**kwargs)


def rehearse(out):
    result={'validationType':KIND,'networkRequests':0,'monitoringActivated':False,'checks':[]}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);remote=root/'remote.git';script=ROOT/'scripts/data-branch.sh'
        subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        selected=None;first=None
        for n,phase in enumerate(['empty','populated','revised','failed']):
            archive=root/f'archive-{n}';state=root/f'runner-{n}'
            subprocess.run(['bash',str(script),'load',str(archive),str(remote)],check=True,capture_output=True)
            RehearsalClient.phase=phase
            report=run(ROOT,state,archive,datetime(2026,10,29,13,tzinfo=timezone.utc)+timedelta(minutes=30*n),RehearsalClient)
            if phase=='empty':
                assert report['status']=='empty' and report['firstPublishedProgramme'] is None
            if phase=='populated':
                assert report['firstPublicationDetected']
                assert report['event']['liveApi']['programmeComplete']
                assert len(report['programmeObservation']['rounds'])==9
                assert all(r['latvianTime']['lv'] for r in report['programmeObservation']['rounds'])
                selected=report['event']['scheduleAuthority']['selectedVersionId']
                first=copy.deepcopy(report['firstPublishedProgramme'])
            if phase=='revised':
                assert len(report['programmeObservation']['roundChanges'])==1
                assert report['event']['scheduleAuthority']['status']=='needs-review'
                assert report['event']['scheduleAuthority']['selectedVersionId']==selected
                assert report['firstPublishedProgramme']==first
            if phase=='failed':
                assert report['event']['scheduleAuthority']['selectedVersionId']==selected
                assert report['firstPublishedProgramme']==first
            assert not report['approvedForWebsite']
            Archive(archive).checkpoint(state)
            subprocess.run(['bash',str(script),'save',str(archive),str(remote)],check=True,capture_output=True)
            result['checks'].append({'phase':phase,'status':report['status'],'firstPublicationDetected':report['firstPublicationDetected'],
                                    'authority':report['event']['scheduleAuthority']['status']})
        count=subprocess.check_output(['git','--git-dir',str(remote),'rev-list','--count','pilot-data'],text=True).strip()
        assert count=='4';result['evidenceCommits']=int(count)
    write(Path(out)/'offline-workflow.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':rehearse(sys.argv[1] if len(sys.argv)>1 else 'out/offline-workflow')
