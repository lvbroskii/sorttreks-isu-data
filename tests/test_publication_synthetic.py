"""Synthetic publication-stage transitions, never a populated Montreal capture."""
from datetime import datetime,timedelta
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from isu_pilot.publication import assess,changes
from isu_pilot.live_api import schedule,BASE
from isu_pilot.sources import Client
from isu_pilot.synthetic import programme as synthetic_programme,encode
from isu_pilot.revisions import version,History

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[1]
PAGE={'identityVerified':True,'tabs':{'schedule':EVENT['infoUrl']+'?tab=schedule_16272'},'tabStates':{'schedule':True}}
EMPTY={'availability':'unpublished','scheduleRows':0,'participants':[]}


class SyntheticPublicationTests(unittest.TestCase):
    def test_visible_tab_does_not_imply_sessions_rounds_or_draws(self):
        report=assess(EVENT,PAGE,EMPTY)
        self.assertEqual(report['stages']['scheduleTab']['status'],'visible')
        self.assertEqual(report['stages']['sessions']['status'],'not-verified')
        self.assertEqual(report['stages']['roundTimes']['status'],'unpublished')
        self.assertTrue(all(a['status']=='not-verified' for a in report['stages']['athleteDraws'].values()))
    def test_hidden_or_unverified_tab_has_its_own_stage(self):
        for page in [dict(PAGE,tabStates={'schedule':False}),dict(PAGE,tabs={}),dict(PAGE,identityVerified=False)]:
            self.assertNotEqual(assess(EVENT,page,EMPTY)['stages']['scheduleTab']['status'],'visible')
    def test_explicit_session_evidence_does_not_create_rounds(self):
        # Normalized future-adapter contract, not a purported ISU API payload.
        session={'title':'Qualification','startsAt':'2026-10-30T09:00:00-04:00','sourceUrl':EVENT['infoUrl'],
                 'verificationStatus':'verified','timeBasis':'session-start'}
        r=assess(EVENT,PAGE,EMPTY,sessions=[session])['stages']
        self.assertEqual(r['sessions']['status'],'published')
        self.assertEqual(r['sessions']['rows'][0]['latvianTime']['lv'],'30.10. 15:00')
        self.assertEqual(r['roundTimes']['status'],'unpublished')
    def test_session_dst_conversion_uses_november_montreal_offset(self):
        sessions=[{'title':'Main','startsAt':'2026-11-01T09:00:00-05:00','sourceUrl':EVENT['infoUrl'],
                   'verificationStatus':'verified','timeBasis':'session-start'}]
        self.assertEqual(assess(EVENT,PAGE,EMPTY,sessions=sessions)['stages']['sessions']['rows'][0]['latvianTime']['lv'],'01.11. 16:00')
    def test_rounds_are_not_automatically_session_boundaries_or_draws(self):
        api={'availability':'available','programmeComplete':True,'scheduleRows':52,'participants':[]}
        stages=assess(EVENT,PAGE,api)['stages']
        self.assertEqual(stages['roundTimes']['status'],'published')
        self.assertEqual(stages['sessions']['status'],'not-verified')
        self.assertEqual(stages['athleteDraws']['Roberts Krūzbergs']['status'],'not-verified')
    def test_partial_programme_needs_review(self):
        api={'availability':'available','programmeComplete':False,'scheduleRows':4}
        self.assertEqual(assess(EVENT,PAGE,api)['stages']['roundTimes']['status'],'partial-or-unverified')
    def test_unsupported_nonempty_payload_is_not_claimed_as_empty_or_published_rounds(self):
        raw=json.dumps({'status':200,'data':{'discipline':{'discipline_id':3},'value':[{'start_time':'2026-10-30T13:00:00Z','event_schedule_title':'Qualification session'}]}})
        rows,issues=schedule(raw,EVENT,BASE,True)
        self.assertEqual(rows,[]);self.assertTrue(issues)
        self.assertNotIn('live-api-programme-unpublished',issues)
    def test_draws_and_confirmed_first_rounds_are_separate(self):
        first={'athlete':'Roberts Krūzbergs','gender':'men','distance':500,'round':'heats','occurrence':1,'startsAt':'2026-10-30T13:00:00-04:00','confirmed':True}
        person={'matchedAthlete':first['athlete'],'gender':'men','distance':500,'round':'heats','occurrence':1,'date':'2026-10-30','evidenceKind':'start-list','openingDayCoverageComplete':False}
        api={'availability':'available','scheduleRows':52,'programmeComplete':True,'preRaceStartListsVerified':True,'participants':[person]}
        r=assess(EVENT,PAGE,api,[first])['stages']['athleteDraws'][first['athlete']]
        self.assertEqual(r['status'],'assignments-first-round-unverified')
        person['openingDayCoverageComplete']=True
        r=assess(EVENT,PAGE,api,[first])['stages']['athleteDraws'][first['athlete']]
        self.assertEqual(r['status'],'confirmed-first-rounds');self.assertEqual(r['firstStarts'],[first])
    def test_retained_old_confirmation_does_not_reverify_empty_current_source(self):
        old={'athlete':'Roberts Krūzbergs','startsAt':'2026-10-30T13:00:00-04:00','confirmed':True}
        r=assess(EVENT,PAGE,EMPTY,[old])
        self.assertEqual(r['stages']['athleteDraws'][old['athlete']]['status'],'not-verified')
        self.assertTrue(r['retainVerifiedFallback']);self.assertFalse(r['approvedForWebsite'])
    def test_empty_to_populated_transition_is_synthetic_and_preserves_authority_review(self):
        raw=synthetic_programme()
        # Explicitly synthetic Montreal times/IDs; no populated Montreal source was captured.
        for item in raw['data']['value']:
            item['start_time']=(datetime.fromisoformat(item['start_time'].replace('Z','+00:00'))+timedelta(days=7)).isoformat()
        rows,issues=schedule(json.dumps(raw),EVENT,BASE,True)
        self.assertFalse(issues)
        before=assess(EVENT,PAGE,EMPTY)
        after=assess(EVENT,PAGE,{'availability':'available','scheduleRows':len(rows),'programmeComplete':True})
        diff=changes(before,after)
        self.assertEqual([d['stage'] for d in diff],['roundTimes'])
        self.assertEqual(diff[0]['previous']['status'],'unpublished')
        self.assertEqual(diff[0]['current']['status'],'published')
        with tempfile.TemporaryDirectory() as td:
            history=History(Path(td)/'history.json')
            empty=version(EVENT,'online',BASE,[],{'sha256':'empty'},issues=['live-api-programme-unpublished'])
            history.resolve(EVENT['id'],[empty])
            populated=version(EVENT,'online',BASE,rows,{'sha256':'synthetic-populated'})
            decision=history.resolve(EVENT['id'],[populated])
            self.assertEqual(decision['status'],'resolved')
            self.assertTrue(after['retainVerifiedFallback']);self.assertFalse(after['approvedForWebsite'])
    def test_failed_or_empty_later_check_retains_selected_schedule(self):
        with tempfile.TemporaryDirectory() as td:
            h=History(Path(td)/'history.json')
            event=json.loads((ROOT/'config/events.json').read_text())[0]
            rows,issues=schedule(encode(synthetic_programme()),event,BASE,True)
            h.resolve(event['id'],[version(event,'online',BASE,rows,{'sha256':'synthetic'})])
            d=h.resolve(event['id'],[version(event,'online',BASE,[],{'sha256':'empty'},issues=['unpublished'])])
            self.assertTrue(d['retainedPrevious']);self.assertEqual(len(d['selected']['rows']),9)
    def test_transitions_cannot_cross_event_identity(self):
        with self.assertRaises(ValueError):changes({'eventId':'other'},assess(EVENT,PAGE,EMPTY))


class ErrorEvidenceTests(unittest.TestCase):
    def test_error_response_archived_without_reverifying_or_replacing_old_body(self):
        url=BASE+'/events/get-event-result/example'
        body=b'{"status":404,"message":"Not Found"}'
        def fail(req,**kwargs):raise urllib.error.HTTPError(req.full_url,404,'Not Found',{},io.BytesIO(body))
        with tempfile.TemporaryDirectory() as td:
            c=Client(td,{url:{'sha256':'previous-verified-body'}},fail)
            data,r=c.get(url)
            self.assertIsNone(data);self.assertEqual(r['httpStatus'],404)
            self.assertEqual(r['sha256'],'previous-verified-body')
            self.assertEqual((Path(td)/(r['errorBodySha256']+'.body')).read_bytes(),body)
            self.assertEqual(r['status'],'unavailable')
