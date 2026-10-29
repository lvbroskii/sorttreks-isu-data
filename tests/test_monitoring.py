"""Monitoring/persistence tests. Publication/revision payload changes are synthetic."""
import copy
import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
import urllib.error
from datetime import datetime,timedelta,timezone
from pathlib import Path
from isu_pilot.archive import Archive,load,write
from isu_pilot.monitor import plan,observe,run
from isu_pilot.live_api import discover_draw_ids,BASE
from isu_pilot.sources import Client

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[1]
CONFIG=json.loads((ROOT/'config/monitoring.json').read_text())
UTC=timezone.utc
EMPTY=(ROOT/'fixtures/real/montreal-publication-2026-10-29/programme.json').read_bytes()
URL=BASE+'/events/getschedule/isu-short-track-world-tour-2-montreal'


def record(body,when='2026-10-30T10:00:00Z'):
    return {'url':URL,'sha256':hashlib.sha256(body).hexdigest(),'fetchedAt':when,'status':'fetched'}


def synthetic_programme():
    source=json.loads((ROOT/'fixtures/real/live-api/vancouver-schedule.json').read_text())
    for row in source['data']['value']:
        row['start_time']=(datetime.fromisoformat(row['start_time'].replace('Z','+00:00'))+timedelta(days=7)).isoformat()
    return json.dumps(source).encode()


class CampaignTests(unittest.TestCase):
    def test_final_precompetition_and_active_days_are_due_every_30_minutes(self):
        now=datetime(2026,10,29,12,tzinfo=UTC)
        self.assertEqual(plan(CONFIG,{},now),'due')
        self.assertEqual(plan(CONFIG,{'lastCheckAt':(now-timedelta(minutes=28)).isoformat()},now),'not-due')
        self.assertEqual(plan(CONFIG,{'lastCheckAt':(now-timedelta(minutes=30)).isoformat()},now),'due')
        self.assertEqual(plan(CONFIG,{},datetime(2026,11,1,18,tzinfo=UTC)),'due')
    def test_hard_stop_and_wrong_year_never_collect(self):
        for now in [datetime(2026,10,28,tzinfo=UTC),datetime(2026,11,2,18,tzinfo=UTC),datetime(2027,10,29,tzinfo=UTC)]:
            self.assertEqual(plan(CONFIG,{},now),'outside-campaign-window')
    def test_first_empty_to_real_round_shape_pinned_only_once(self):
        state={};self.assertEqual(observe(EVENT,EMPTY,record(EMPTY),True,state)['status'],'empty')
        body=synthetic_programme();first=observe(EVENT,body,record(body,'2026-10-30T10:30:00Z'),True,state)
        self.assertTrue(first['firstPublicationDetected']);self.assertEqual(len(first['rounds']),52)
        self.assertTrue(all('latvianTime' in r for r in first['rounds']))
        pinned=copy.deepcopy(state['firstPublishedProgramme'])
        again=observe(EVENT,body,record(body,'2026-10-30T11:00:00Z'),True,state)
        self.assertFalse(again['firstPublicationDetected']);self.assertEqual(state['firstPublishedProgramme'],pinned)
        self.assertEqual(pinned['previousEmptyEvidence']['sha256'],hashlib.sha256(EMPTY).hexdigest())
    def test_latest_empty_capture_bounds_first_publication_without_claiming_revision_date(self):
        state={}
        observe(EVENT,EMPTY,record(EMPTY,'2026-10-30T10:00:00Z'),True,state)
        observe(EVENT,EMPTY,record(EMPTY,'2026-10-30T10:30:00Z'),True,state)
        body=synthetic_programme();observe(EVENT,body,record(body,'2026-10-30T11:00:00Z'),True,state)
        first=state['firstPublishedProgramme']
        self.assertEqual(first['previousEmptyEvidence']['retrievedAt'],'2026-10-30T10:30:00Z')
        self.assertFalse(first['isRevisionTimestamp'])
    def test_revisions_report_old_new_round_time_and_source(self):
        state={};body=synthetic_programme();observe(EVENT,body,record(body),True,state)
        revised=json.loads(body);revised['data']['value'][0]['start_time']='2026-10-30T16:05:00Z'
        revised=json.dumps(revised).encode();report=observe(EVENT,revised,record(revised),True,state)
        self.assertFalse(report['firstPublicationDetected']);self.assertEqual(len(report['roundChanges']),1)
        change=report['roundChanges'][0]
        self.assertNotEqual(change['previousTime'],change['updatedTime']);self.assertEqual(change['source'],URL)
    def test_empty_failed_and_unsupported_never_delete_prior_snapshot(self):
        state={};body=synthetic_programme();observe(EVENT,body,record(body),True,state)
        prior=copy.deepcopy(state['lastProgrammeVersion'])
        for raw in [None,EMPTY,b'{"status":200,"data":{"value":[{"start_time":"bad"}]}}']:
            observe(EVENT,raw,record(raw or EMPTY),True,state)
            self.assertEqual(state['lastProgrammeVersion'],prior)
    def test_visible_tab_or_unscoped_data_cannot_trigger_first_publication(self):
        for raw,identity in [(EMPTY,True),(synthetic_programme(),False),(b'{"status":200,"data":{"discipline":{"discipline_id":3},"value":[{"title":"Main Session"}]}}',True)]:
            state={};self.assertFalse(observe(EVENT,raw,record(raw),identity,state)['firstPublicationDetected'])
            self.assertNotIn('firstPublishedProgramme',state)


class ArchiveTests(unittest.TestCase):
    def test_compressed_dedup_and_fresh_runner_restore_with_304(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=Archive(root/'archive');state=root/'state';state.mkdir()
            digest=archive.add(EMPTY);self.assertEqual(archive.add(EMPTY),digest)
            self.assertEqual(len(list((root/'archive/raw').rglob('*.gz'))),1)
            rec={**record(EMPTY),'etag':'captured-etag','firstSeenAt':'2026-10-29T12:53:00Z'}
            write(state/'sources.json',{URL:rec});(state/(digest+'.body')).write_bytes(EMPTY)
            archive.persist(state,{'status':'empty','checkedAt':'2026-10-29T13:00:00Z'})
            fresh=root/'fresh';archive.restore(fresh)
            def transport(req,**kw):
                self.assertEqual(req.get_header('If-none-match'),'captured-etag')
                raise urllib.error.HTTPError(req.full_url,304,'Not Modified',{},io.BytesIO())
            client=Client(fresh,load(fresh/'sources.json',{}),transport)
            raw,r=client.get(URL);self.assertEqual(raw,EMPTY);self.assertEqual(r['status'],'not-modified')
            self.assertEqual(archive.read(digest),EMPTY)
    def test_corrupt_or_missing_raw_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            a=Archive(Path(td)/'archive');digest=a.add(EMPTY)
            a.path(digest).write_bytes(gzip.compress(b'wrong'))
            with self.assertRaises(ValueError):a.read(digest)
            write(a.root/'state/sources.json',{URL:record(EMPTY)})
            a.path(digest).unlink()
            with self.assertRaises(ValueError):a.restore(Path(td)/'state')
    def test_legacy_state_preserved_and_missing_historical_raw_reported(self):
        with tempfile.TemporaryDirectory() as td:
            a=Archive(Path(td)/'archive');write(a.root/'sources.json',{URL:record(EMPTY)})
            selected={'events':{'2026-27-wt2':{'selected':{'verified':'retain'}}}}
            write(a.root/'schedules.json',selected);a.restore(Path(td)/'fresh')
            self.assertEqual(load(Path(td)/'fresh/schedules.json',{}),selected)
            gaps=load(a.root/'legacy-archive-gaps.json',{})
            self.assertIn(record(EMPTY)['sha256'],gaps['missingHistoricalBodyHashes'])
    def test_append_only_check_reports_keep_first_empty_raw_and_transition(self):
        with tempfile.TemporaryDirectory() as td:
            a=Archive(Path(td)/'archive');state=Path(td)/'state';state.mkdir()
            for body,stamp in [(EMPTY,'2026-10-29T13:00:00Z'),(synthetic_programme(),'2026-10-29T13:30:00Z')]:
                (state/(hashlib.sha256(body).hexdigest()+'.body')).write_bytes(body)
                a.persist(state,{'status':'observed','checkedAt':stamp})
            self.assertEqual(len(load(a.root/'index.json',{})['checks']),2)
            self.assertEqual(a.read(hashlib.sha256(EMPTY).hexdigest()),EMPTY)
    def test_archive_cap_or_closed_campaign_has_no_source_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=Archive(root/'archive')
            (a.root/'large').write_bytes(b'x')
            def forbidden(*a,**k):raise AssertionError('No client should be initialized')
            # Simulate cap accounting without allocating hundreds of MiB.
            from unittest.mock import patch
            with patch.object(Archive,'size',return_value=300*1024*1024):
                result=run(ROOT,root/'state',a.root,datetime(2026,10,29,13,tzinfo=UTC),forbidden)
            self.assertEqual(result['status'],'archive-cap-monitoring-paused')
            result=run(ROOT,root/'fresh',a.root,datetime(2027,1,1,tzinfo=UTC),forbidden)
            self.assertEqual(result['status'],'outside-campaign-window')


class DownloadBudgetTests(unittest.TestCase):
    def test_aggregate_download_budget_limits_subsequent_responses(self):
        class Response(io.BytesIO):
            status=200;url='https://front-api.isu.org/test';headers={'Content-Type':'application/json'}
        with tempfile.TemporaryDirectory() as td:
            c=Client(td,transport=lambda *a,**k:Response(b'1234'),byte_budget=5)
            self.assertEqual(c.get(BASE+'/a')[0],b'1234')
            data,r=c.get(BASE+'/b');self.assertIsNone(data);self.assertEqual(r['status'],'unavailable')
            self.assertIn('budget',r['error'])


class DataBranchTests(unittest.TestCase):
    def git(self,*args):
        return subprocess.run(['git',*map(str,args)],check=True,capture_output=True,text=True)
    def test_append_restore_preserves_history_main_and_raw(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);remote=t/'remote.git';self.git('init','--bare',remote)
            checkout=t/'code';self.git('clone',remote,checkout)
            self.git('-C',checkout,'checkout','-b','main')
            self.git('-C',checkout,'config','user.name','Test');self.git('-C',checkout,'config','user.email','test@example.invalid')
            (checkout/'source.txt').write_text('unchanged');self.git('-C',checkout,'add','.');self.git('-C',checkout,'commit','-m','source');self.git('-C',checkout,'push','origin','main')
            main=self.git('--git-dir',remote,'rev-parse','main').stdout.strip()
            script=ROOT/'scripts/data-branch.sh'
            for n in (1,2):
                archive=t/f'archive{n}'
                subprocess.run(['bash',str(script),'load',str(archive),str(remote)],check=True,capture_output=True)
                if n==2:self.assertEqual((archive/'raw.txt').read_text(),'first evidence')
                (archive/'raw.txt').write_text('first evidence');(archive/f'check{n}.json').write_text('{}')
                (archive/'incomplete.tmp').write_text('not a completed source')
                subprocess.run(['bash',str(script),'save',str(archive),str(remote)],check=True,capture_output=True)
            self.assertEqual(self.git('--git-dir',remote,'rev-list','--count','pilot-data').stdout.strip(),'2')
            self.assertNotIn('incomplete.tmp',self.git('--git-dir',remote,'ls-tree','--name-only','pilot-data').stdout)
            self.assertEqual(self.git('--git-dir',remote,'rev-parse','main').stdout.strip(),main)
    def test_remote_failure_does_not_initialize_blank_branch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);target=root/'archive'
            result=subprocess.run(['bash',str(ROOT/'scripts/data-branch.sh'),'load',str(target),str(root/'missing.git')],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(target.exists())
    def test_workflow_guards_no_artifacts_cache_force_push_or_secrets_in_collector(self):
        text=(ROOT/'.github/workflows/pilot.yml').read_text()
        self.assertIn("vars.ENABLE_PILOT == 'true'",text);self.assertIn('repository.private == false',text)
        self.assertIn('persist-credentials: false',text);self.assertIn('ubuntu-24.04',text)
        self.assertIn("'17,47 * 29-31 10 *'",text);self.assertIn("'17,47 * 1-2 11 *'",text)
        self.assertNotIn('upload-artifact',text);self.assertNotIn('actions/cache',text)
        self.assertNotIn('--force',(ROOT/'scripts/data-branch.sh').read_text())
        self.assertNotIn('CLOUDFLARE_API_TOKEN',text)


class IndependentDrawProbeTests(unittest.TestCase):
    def test_only_verified_event_ids_are_queried_and_never_confirm_first_round(self):
        class Source:
            def __init__(self,wrong=False):self.calls=[];self.wrong=wrong
            def get(self,url):return json.dumps({'status':200,'data':[{'event_id':16272,'event_result_id':54321}]}).encode(),{'url':url,'status':'fetched'}
            def query(self,path,fields):
                self.calls.append((path,fields))
                if path.endswith('get-event-result-round'):
                    data=[{'event_id':1 if self.wrong else 16272,'event_result_id':54321,'event_result_round_id':65432,'name':'Heats','date':'2026-10-30T13:00:00Z'}]
                else:data=[]
                return json.dumps({'status':200,'data':data}).encode(),{'url':BASE+path,'status':'fetched'}
        c=Source();r=discover_draw_ids(EVENT,c,16272)
        self.assertEqual(r['roundCandidates'][0]['eventResultRoundId'],65432)
        self.assertFalse(r['confirmedFirstStarts']);self.assertEqual(len(c.calls),2)
        bad=Source(True);r=discover_draw_ids(EVENT,bad,16272)
        self.assertEqual(r['status'],'inventory-needs-review');self.assertEqual(len(bad.calls),1)
    def test_foreign_result_tab_not_probed(self):
        class Source:
            def __init__(self):self.urls=[]
            def get(self,url):self.urls.append(url);return None,{'url':url,'status':'unavailable'}
        for tab in [EVENT['infoUrl']+'?tab=results_999','https://example.org/?tab=results_16272']:
            c=Source();discover_draw_ids(EVENT,c,16272,tab);self.assertEqual(len(c.urls),1)


class FullMonitorRestartTests(unittest.TestCase):
    def factory(self,state,previous,**kwargs):
        fixture=ROOT/'fixtures/real/montreal-publication-2026-10-29'
        records={r['url']:r for r in load(fixture/'manifest.json',{})['sources']}
        class Response(io.BytesIO):
            status=200
            def __init__(self,body,url,mime):
                super().__init__(body);self.url=url
                self.headers={'Content-Type':mime,'ETag':hashlib.sha256(body).hexdigest()}
        def transport(req,**kw):
            rec=records.get(req.full_url)
            if not rec or rec['status']=='unavailable':
                raise urllib.error.HTTPError(req.full_url,404,'Not Found',{},io.BytesIO(b'{"code":404,"message":"Not Found"}'))
            if req.get_header('If-none-match'):
                raise urllib.error.HTTPError(req.full_url,304,'Not Modified',{},io.BytesIO())
            return Response((fixture/rec['file']).read_bytes(),req.full_url,'text/html' if rec['file'].endswith('.html') else 'application/json')
        return Client(state,previous,transport=transport,**kwargs)
    def test_two_fresh_runners_preserve_actual_empty_raw_and_prior_state(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td);now=datetime(2026,10,29,13,tzinfo=UTC)
            first=run(ROOT,t/'runner1',t/'archive',now,self.factory)
            self.assertEqual(first['status'],'empty');self.assertFalse(first['firstPublicationDetected'])
            second=run(ROOT,t/'runner2',t/'archive',now+timedelta(minutes=30),self.factory)
            self.assertEqual(second['status'],'empty')
            self.assertTrue(any(r['status']=='not-modified' for r in second['sources'].values()))
            self.assertEqual(len(load(t/'archive/index.json',{})['checks']),2)
            self.assertEqual(Archive(t/'archive').read(hashlib.sha256(EMPTY).hexdigest()),EMPTY)
            self.assertFalse(second['approvedForWebsite'])
    def test_collector_crash_still_persists_already_retrieved_responses(self):
        from unittest.mock import patch
        def crash(events,aliases,reference,client):
            client.get(URL);raise ValueError('synthetic collector crash')
        with tempfile.TemporaryDirectory() as td:
            t=Path(td)
            with patch('isu_pilot.monitor.collect',side_effect=crash):
                report=run(ROOT,t/'state',t/'archive',datetime(2026,10,29,13,tzinfo=UTC),self.factory)
            self.assertEqual(report['status'],'collector-error')
            self.assertEqual(Archive(t/'archive').read(hashlib.sha256(EMPTY).hexdigest()),EMPTY)
            self.assertTrue((t/'archive/latest.json').is_file())
