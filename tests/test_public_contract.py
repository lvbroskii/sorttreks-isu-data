"""Public synthetic contract tests; no claim of actual-source validation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from isu_pilot.synthetic import programme,empty,metadata,heats,event_html,SyntheticClient,demo,encode,KIND
from isu_pilot.live_api import schedule,rounds,draw,collect_live,BASE
from isu_pilot.html import discover
from isu_pilot.pipeline import collect
from isu_pilot.revisions import History
from isu_pilot.publication import assess,changes,check

ROOT=Path(__file__).resolve().parents[1]
EVENTS=json.loads((ROOT/'config/events.json').read_text())
ALIASES=json.loads((ROOT/'config/athletes.json').read_text())


class SyntheticProgrammeContractTests(unittest.TestCase):
    def test_fixture_is_explicitly_synthetic_and_deterministic(self):
        self.assertEqual(KIND,'synthetic-not-official');self.assertIn('SYNTHETIC',programme()['message'])
        self.assertEqual(hashlib.sha256(encode(programme())).hexdigest(),hashlib.sha256(encode(programme())).hexdigest())
    def test_event_identity_parser_all_four_synthetic_pages(self):
        for i,event in enumerate(EVENTS):self.assertTrue(discover(event_html(event,i),event['infoUrl'],event)['identityVerified'])
    def test_nine_known_rounds_and_utc_conversion(self):
        rows,issues=schedule(encode(programme()),EVENTS[0],BASE,True)
        self.assertEqual(issues,[]);self.assertEqual(len(rows),9)
        self.assertEqual(next(r for r in rows if r['eventResultRoundId']==22870)['startsAt'],'2026-10-23T09:21:00-07:00')
    def test_synthetic_empty_is_unpublished_not_absent_athletes(self):
        rows,issues=schedule(encode(empty()),EVENTS[1],BASE,True)
        self.assertEqual(rows,[]);self.assertEqual(issues,['live-api-programme-unpublished'])
    def test_metadata_maps_all_known_group_rounds(self):
        rows=schedule(encode(programme()),EVENTS[0],BASE,True)[0]
        result=rounds(encode(metadata(15939)),EVENTS[0],16230,15939,rows)
        self.assertEqual(len(result),3);self.assertTrue(all(r['status']=='Finished' for r in result))
    def test_finished_heat_records_keep_heat_and_round_times_distinct(self):
        rows=schedule(encode(programme()),EVENTS[0],BASE,True)[0]
        for rid,name in [(22870,'Reinis BERZINS'),(22872,'Roberts KRUZBERGS')]:
            row=next(r for r in rows if r['eventResultRoundId']==rid)
            meta=next(r for r in metadata(15939)['data'] if r['event_result_round_id']==rid)
            people,coverage=draw(encode(heats(rid)),row,meta,BASE,EVENTS[0])
            self.assertEqual(people[0]['name'],name);self.assertNotEqual(people[0]['heatStartsAt'],row['startsAt'])
            self.assertFalse(coverage['preRace']);self.assertEqual(people[0]['evidenceKind'],'historical-result')
    def test_demo_six_starts_are_synthetic_and_unconfirmed(self):
        report=demo(ROOT);event=report['events'][0]
        self.assertEqual(report['mode'],KIND);self.assertEqual(event['counts']['firstStarts'],6)
        self.assertFalse(any(r['confirmed'] for r in event['athleteFirstStarts']))
        self.assertIsNone(event['calendarPatchCandidate']);self.assertFalse(report['approvedForWebsite'])
    def test_complete_adapter_integrates_without_html_timetable(self):
        with tempfile.TemporaryDirectory() as td:
            r=collect([EVENTS[0]],ALIASES,{'events':[]},SyntheticClient(ROOT),History(Path(td)/'history.json'))[0]
            self.assertTrue(r['liveApi']['programmeComplete']);self.assertEqual(r['counts']['firstStarts'],6)
            self.assertNotIn('online-programme-incomplete; supersession-not-established',r['issues'])
            self.assertFalse(r['approvedForWebsite'])


class SyntheticPublicationContractTests(unittest.TestCase):
    def check(self,previous=None):return check(EVENTS[1],SyntheticClient(ROOT),ALIASES,previous)
    def test_tab_is_visible_but_times_unpublished(self):
        stages=self.check()['publication']['stages']
        self.assertEqual(stages['scheduleTab']['status'],'visible');self.assertEqual(stages['roundTimes']['status'],'unpublished')
    def test_sessions_are_not_inferred(self):
        self.assertEqual(self.check()['publication']['stages']['sessions']['rows'],[])
    def test_no_guessed_identifiers_or_confirmed_first_starts(self):
        r=self.check();self.assertEqual(r['resultsPageIdentifierObservation']['eventResultIds'],[])
        self.assertTrue(all(a['status']=='not-verified' and a['firstStarts']==[] for a in r['publication']['stages']['athleteDraws'].values()))
    def test_missing_inventory_is_not_absence(self):
        r=self.check()['publication'];self.assertEqual(r['drawDiscovery']['status'],'identifiers-unavailable')
        self.assertTrue(r['retainVerifiedFallback'])
    def test_check_has_no_patch_and_remains_read_only(self):
        r=self.check();self.assertIsNone(r['calendarPatchCandidate']);self.assertFalse(r['approvedForWebsite'])
    def test_repeated_empty_check_has_no_stage_changes(self):
        prior=self.check()['publication'];self.assertEqual(self.check(prior)['publicationChanges'],[])


class LiveBaselineContractTests(unittest.TestCase):
    def test_monitor_configuration_has_no_fixture_bootstrap(self):
        config=json.loads((ROOT/'config/monitoring.json').read_text())
        self.assertNotIn('baselineManifest',config)
    def test_initial_populated_source_is_not_claimed_as_empty_transition(self):
        from isu_pilot.monitor import observe
        event=EVENTS[0];body=encode(programme());state={}
        record={'url':BASE+'/events/getschedule/synthetic-test','sha256':hashlib.sha256(body).hexdigest(),'fetchedAt':'2026-10-29T00:00:00Z'}
        result=observe(event,body,record,True,state)
        self.assertFalse(result['firstPublicationDetected']);self.assertTrue(result['firstRoundDataObserved'])
        self.assertIsNone(state['firstPublishedProgramme']['previousEmptyEvidence'])
        self.assertEqual(state['firstPublishedProgramme']['observationKind'],'initial-populated-without-empty-baseline')
