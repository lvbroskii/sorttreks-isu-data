"""Fresh actual Montreal publication captures; no simulated populated programme."""
import hashlib
import json
import unittest
from pathlib import Path
from isu_pilot.publication import check,changes
from isu_pilot.html import discover

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'fixtures/real/montreal-publication-2026-10-29'
EVENT=json.loads((ROOT/'config/events.json').read_text())[1]
ALIASES=json.loads((ROOT/'config/athletes.json').read_text())


class MontrealCapturedClient:
    def __init__(self):
        self.manifest=json.loads((FIX/'manifest.json').read_text())
        self.sources={r['url']:r for r in self.manifest['sources']}
        self.requested=[]
    def get(self,url):
        self.requested.append(url)
        if url.endswith('/get-event-result/results_16272'):
            return None,{'url':url,'status':'unavailable','error':'Not captured in this fixture set'}
        record=self.sources[url]
        if record['status']=='unavailable':return None,record
        return (FIX/record['file']).read_bytes(),record
    def query(self,*args):
        raise AssertionError('No guessed heat or round queries permitted without Montreal identifiers')


class ActualMontrealPublicationTests(unittest.TestCase):
    def test_all_actual_raw_response_hashes_and_error_provenance(self):
        m=json.loads((FIX/'manifest.json').read_text())
        self.assertEqual(len(m['sources']),5)
        for r in m['sources']:
            self.assertEqual(hashlib.sha256((FIX/r['file']).read_bytes()).hexdigest(),r[r['bodyHashField']])
            self.assertTrue(r['fetchedAt'].startswith('2026-10-29'))
    def test_visible_dynamic_tab_has_no_published_round_rows(self):
        page=discover((FIX/'schedule-page.html').read_text(),EVENT['infoUrl'],EVENT)
        self.assertTrue(page['identityVerified']);self.assertTrue(page['tabStates']['schedule'])
        self.assertTrue(page['programmeShell'])
        raw=json.loads((FIX/'programme.json').read_text())
        self.assertEqual(raw,{'status':200,'message':'Event schedule fetched successfully','data':{'discipline':{'discipline_id':3,'title':'SHORT TRACK'},'value':[]}})
    def test_actual_programme_remains_identical_to_earlier_empty_capture(self):
        self.assertEqual((FIX/'programme.json').read_bytes(),(ROOT/'fixtures/real/live-api/montreal-schedule.json').read_bytes())
    def test_inventory_404_does_not_mean_athlete_absence(self):
        self.assertEqual(json.loads((FIX/'result-inventory-error.json').read_text()),{'code':404,'message':'Not Found'})
        report=check(EVENT,MontrealCapturedClient(),ALIASES)
        state=report['publication'];self.assertEqual(state['drawDiscovery']['status'],'identifiers-unavailable')
        for name in ['Roberts Krūzbergs','Reinis Bērziņš']:
            self.assertEqual(state['stages']['athleteDraws'][name]['status'],'not-verified')
            self.assertEqual(state['stages']['athleteDraws'][name]['firstStarts'],[])
        self.assertEqual(report['resultsPageIdentifierObservation']['eventResultIds'],[])
        self.assertEqual(report['resultsPageIdentifierObservation']['eventResultRoundIds'],[])
    def test_focused_check_retains_fallback_and_never_emits_patch(self):
        report=check(EVENT,MontrealCapturedClient(),ALIASES)
        stages=report['publication']['stages']
        self.assertEqual(stages['scheduleTab']['status'],'visible')
        self.assertEqual(stages['sessions']['status'],'not-verified')
        self.assertEqual(stages['roundTimes']['status'],'unpublished')
        self.assertIsNone(report['calendarPatchCandidate']);self.assertFalse(report['approvedForWebsite'])
        self.assertTrue(report['publication']['retainVerifiedFallback'])
    def test_repeated_empty_check_does_not_report_a_programme_publication(self):
        previous=check(EVENT,MontrealCapturedClient(),ALIASES)['publication']
        current=check(EVENT,MontrealCapturedClient(),ALIASES,previous)
        self.assertEqual(current['publicationChanges'],[])
