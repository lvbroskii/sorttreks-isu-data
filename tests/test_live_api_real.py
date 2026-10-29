"""Actual 29 October official API captures; no mutated/synthetic source bodies."""
import hashlib
import json
import unittest
import tempfile
from pathlib import Path
from isu_pilot.live_api import schedule,rounds,draw,BASE
from isu_pilot.captured import replay, CapturedClient
from isu_pilot.pipeline import collect
from isu_pilot.revisions import History
from isu_pilot.html import discover

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'fixtures/real/live-api'
EVENTS=json.loads((ROOT/'config/events.json').read_text())


class ActualCapturedSourceTests(unittest.TestCase):
    def test_every_capture_matches_recorded_response_hash(self):
        manifest=json.loads((FIX/'manifest.json').read_text())
        self.assertEqual(manifest['kind'],'actual-official-response-captures')
        for record in manifest['sources']:
            with self.subTest(source=record['url']):
                self.assertEqual(hashlib.sha256((FIX/record['file']).read_bytes()).hexdigest(),record['sha256'])
                self.assertTrue(record['fetchedAt'].startswith('2026-10-29'))
    def test_actual_event_identity_in_all_four_pages(self):
        for event,name in zip(EVENTS,['vancouver','montreal','bormio1','bormio2']):
            page=discover((FIX/(name+'-event.html')).read_text(),event['infoUrl'],event)
            self.assertTrue(page['identityVerified'])
            self.assertTrue(all(str(m['id']).isdigit() for m in page['metadata']))
    def test_vancouver_actual_programme_52_rounds_and_utc_conversion(self):
        rows,errors=schedule((FIX/'vancouver-schedule.json').read_bytes(),EVENTS[0],BASE,True)
        self.assertEqual(errors,[]);self.assertEqual(len(rows),52)
        self.assertEqual(len({r['eventResultRoundId'] for r in rows}),52)
        prelim=next(r for r in rows if r['eventResultRoundId']==22870)
        self.assertEqual(prelim['startsAt'],'2026-10-23T09:21:00-07:00')
        self.assertEqual(prelim['apiUtcStart'],'2026-10-23T16:21:00.000Z')
    def test_upcoming_actual_successful_empty_programmes_are_unpublished(self):
        for event,name in zip(EVENTS[1:],['montreal','bormio1','bormio2']):
            raw=(FIX/(name+'-schedule.json')).read_bytes()
            self.assertEqual(json.loads(raw)['status'],200)
            rows,errors=schedule(raw,event,BASE,True)
            self.assertEqual(rows,[]);self.assertEqual(errors,['live-api-programme-unpublished'])
    def test_actual_500m_metadata_covers_programme_and_is_finished(self):
        rows=schedule((FIX/'vancouver-schedule.json').read_bytes(),EVENTS[0],BASE,True)[0]
        items=rounds((FIX/'vancouver-rounds-15939.json').read_bytes(),EVENTS[0],16230,15939,rows)
        self.assertEqual(len(items),8);self.assertTrue(all(i['status']=='Finished' for i in items))
        self.assertTrue(all(i.get('updated_at') for i in items))
    def test_actual_heat_assignments_keep_round_and_heat_times_distinct(self):
        rows=schedule((FIX/'vancouver-schedule.json').read_bytes(),EVENTS[0],BASE,True)[0]
        items=json.loads((FIX/'vancouver-rounds-15939.json').read_text())['data']
        for rid,athlete,heat,lane in [(22870,'Reinis BERZINS','Heat 8',1),(22872,'Roberts KRUZBERGS','Heat 7',2)]:
            r=next(r for r in rows if r['eventResultRoundId']==rid)
            people,coverage=draw((FIX/f'vancouver-draw-{rid}.json').read_bytes(),r,next(i for i in items if i['event_result_round_id']==rid),BASE,EVENTS[0])
            self.assertEqual(len(people),1);p=people[0]
            self.assertEqual((p['name'],p['heatName'],p['startingPosition']),(athlete,heat,lane))
            self.assertNotEqual(p['heatStartsAt'],r['startsAt'])
            self.assertEqual(p['evidenceKind'],'historical-result');self.assertFalse(coverage['preRace'])
    def test_replay_all_six_opening_starts_no_pre_race_claim_or_publication(self):
        report=replay(ROOT);event=report['events'][0]
        self.assertEqual(event['counts']['firstStarts'],6)
        self.assertFalse(any(p['confirmed'] for p in event['athleteFirstStarts']))
        roberts=next(p for p in event['athleteFirstStarts'] if p['athlete']=='Roberts Krūzbergs' and p['distance']==500)
        self.assertEqual(roberts['round'],'heats')
        self.assertEqual(event['scheduleAuthority']['status'],'needs-review')
        self.assertEqual(event['scheduleAuthority']['reason'],'conflicting-schedules-without-proven-supersession')
        self.assertIsNone(event['calendarPatchCandidate']);self.assertFalse(report['approvedForWebsite'])
        self.assertTrue(all(e['validationType']=='actual-captured-source' for e in report['events']))
        self.assertTrue(all(e['liveApi']['availability']=='unpublished' for e in report['events'][1:]))

    def test_actual_api_integrates_into_collector_when_html_is_only_a_shell(self):
        with tempfile.TemporaryDirectory() as td:
            aliases=json.loads((ROOT/'config/athletes.json').read_text())
            result=collect([EVENTS[0]],aliases,{'events':[]},CapturedClient(ROOT),History(Path(td)/'history.json'))[0]
            self.assertTrue(result['liveApi']['programmeComplete'])
            self.assertEqual(result['counts']['firstStarts'],6)
            self.assertNotIn('online-programme-incomplete; supersession-not-established',result['issues'])
            self.assertFalse(any(p['confirmed'] for p in result['athleteFirstStarts']))
            self.assertTrue(all(p['heatStartsAt'] for p in result['athleteFirstStarts']))
            self.assertFalse(result['approvedForWebsite'])
