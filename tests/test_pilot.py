"""Synthetic parser/matcher/transport regression tests; not captured-source validation."""
import copy
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from isu_pilot.timezones import local_instant,display
from isu_pilot.html import discover
from isu_pilot.pdf import timetable,race_participation
from isu_pilot.matching import match_athletes,name_key
from isu_pilot.pipeline import build,PATCH_FIELDS
from isu_pilot.synthetic import C08 as TEXT,C08_URL as URL,event_html,demo
from isu_pilot.sources import Client,official,MAX_BYTES

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[0]
ALIASES=json.loads((ROOT/'config/athletes.json').read_text())
def offline(root):
 data=build(EVENT,TEXT,URL,ALIASES,{'athleteFirstStarts':[{'athlete':name,'distance':distance,'startsAt':'2026-10-23T18:00:00-07:00','round':rd} for name in ['Roberts Krūzbergs','Reinis Bērziņš'] for distance,rd in [(500,'heats'),(1000,'heats'),(1500,'quarterfinals')]]})
 return data

class TimeTests(unittest.TestCase):
 def test_riga_dst_midnight(self):
  self.assertEqual(display(local_instant('2026-10-24','16:05','America/Vancouver')),'25.10. 02:05')
  self.assertEqual(display(local_instant('2026-10-25','16:05','America/Vancouver')),'26.10. 01:05')
 def test_montreal_november_dst(self):
  self.assertTrue(local_instant('2026-10-30','09:00','America/Toronto').endswith('-04:00'))
  self.assertTrue(local_instant('2026-11-01','09:00','America/Toronto').endswith('-05:00'))
 def test_gap_fold_rejected(self):
  for day,clock in [('2026-03-08','02:30'),('2026-11-01','01:30')]:
   with self.assertRaises(ValueError):local_instant(day,clock,'America/Toronto')
 def test_invalid_clock(self):
  with self.assertRaises(ValueError):local_instant('2026-10-23','25:00','America/Vancouver')

class SyntheticSourceTests(unittest.TestCase):
 def test_document_discovery_without_eval(self):
  s=discover(event_html(EVENT),EVENT['infoUrl'],EVENT)
  self.assertTrue(s['identityVerified'])
  self.assertIn(URL,[d['url'] for d in s['documents']])
  self.assertTrue(s['tabs']['schedule'].endswith('schedule_16230'))
 def test_shell_not_schedule(self):
  s=discover(event_html(EVENT),EVENT['infoUrl'],EVENT)
  self.assertTrue(s['programmeShell'])
 def test_synthetic_c08_rounds_breaks_no_estimates(self):
  rows,issues=timetable(TEXT,EVENT,URL)
  self.assertEqual(issues,[])
  m500=[r for r in rows if r.get('gender')=='men' and r.get('distance')==500 and r.get('round')=='heats'][0]
  self.assertEqual(m500['startsAt'],'2026-10-23T13:39:00-07:00')
  self.assertTrue(any(r['kind']=='break' for r in rows))
  self.assertEqual(len([r for r in rows if r['kind']=='end']),3)
 def test_identity_wrong_event_rejected(self):
  event=json.loads((ROOT/'config/events.json').read_text())[1]
  self.assertEqual(timetable(TEXT,event,URL)[1],['document-identity-unverified'])
 def test_historical_results_not_start_lists(self):
  data=offline(ROOT)
  self.assertEqual(data['counts']['firstStarts'],6)
  self.assertEqual(sum(c['status']=='discrepancy' for c in data['comparison']),6)
  self.assertFalse(data['approvedForWebsite'])
  self.assertEqual(data['calendarPatchCandidate']['athleteFirstStarts'],[])
  self.assertTrue(all(r['confirmed'] is False for r in data['athleteFirstStarts']))
 def test_patch_cannot_change_homepage(self):
  patch=offline(ROOT)['calendarPatchCandidate']
  self.assertLessEqual(set(patch),PATCH_FIELDS)
  for field in ['sessions','startsAt','endsAt','homepageSessionStates','homepageResultsUrl','countdownEligible','watchUrl']:
   self.assertNotIn(field,patch)

class MatchingTests(unittest.TestCase):
 def setUp(self):
  self.rows=timetable(TEXT,EVENT,URL)[0]
  self.p={'name':'KRUZBERGS Roberts','nation':'LAT','gender':'men','distance':500,'occurrence':1,'round':'heats',
          'date':'2026-10-23','sourceUrl':URL,'evidenceKind':'start-list','status':'listed','directEntryConfirmed':True}
 def test_exact_identity_normalization(self):
  self.assertEqual(name_key('Rūdolfs Šternmanis'),name_key('STERNMANIS Rudolfs'))
  self.assertNotEqual(name_key('STERNMANIS Maris Janis'),name_key('STERNMANIS Rudolfs'))
 def test_seeded_into_later_round(self):
  first,_,issues=match_athletes(self.rows,[self.p],ALIASES,EVENT)
  self.assertEqual(issues,[]);self.assertEqual(first[0]['round'],'heats')
  self.assertTrue(first[0]['confirmed']);self.assertEqual(first[0]['startsAt'],'2026-10-23T13:39:00-07:00')
  self.assertEqual(first[0]['timeBasis'],'round-start');self.assertIsNone(first[0]['heatStartsAt'])
 def test_entry_does_not_confirm_start(self):
  p={**self.p,'evidenceKind':'entry'}
  first,_,_=match_athletes(self.rows,[p],ALIASES,EVENT)
  self.assertFalse(first[0]['confirmed'])
 def test_dns_and_other_nations(self):
  for patch in [{'status':'DNS'},{'nation':'LTU'}]:
   self.assertEqual(match_athletes(self.rows,[{**self.p,**patch}],ALIASES,EVENT)[0],[])
 def test_unknown_athlete_review(self):
  _,_,issues=match_athletes(self.rows,[{**self.p,'name':'NEW Athlete'}],ALIASES,EVENT)
  self.assertEqual(issues[0]['code'],'unmatched-lat-athlete')
 def test_ambiguous_round_never_picked(self):
  rows=self.rows+copy.deepcopy([r for r in self.rows if r.get('distance')==500 and r.get('round')=='heats'])
  first,_,issues=match_athletes(rows,[self.p],ALIASES,EVENT)
  self.assertEqual(first,[]);self.assertEqual(issues[0]['code'],'ambiguous-or-missing-round')
 def test_junior_repeated_distance_keeps_occurrence(self):
  rows=copy.deepcopy(self.rows)
  base=next(r for r in rows if r.get('gender')=='men' and r.get('distance')==500 and r.get('round')=='heats')
  second={**base,'occurrence':2,'startsAt':'2026-10-23T15:39:00-07:00'};rows.append(second)
  p2={**self.p,'occurrence':2}
  first,_,issues=match_athletes(rows,[self.p,p2],ALIASES,EVENT)
  self.assertEqual(len(first),2);self.assertEqual(issues,[])
 def test_cancelled_round_excluded(self):
  rows=[{**r,'cancelled':True} for r in self.rows]
  self.assertEqual(match_athletes(rows,[self.p],ALIASES,EVENT)[0],[])

class TransportTests(unittest.TestCase):
 def test_only_official_https_and_no_beta(self):
  for url in ['http://isu-skating.com/a','https://beta.isu-skating.com/a','https://isu-skating.com.evil/a','https://user@isu-skating.com/a','https://127.0.0.1/a']:
   with self.assertRaises(ValueError):official(url)
 def test_changed_unchanged_and_etag(self):
  class Response(io.BytesIO):
   status=200;url='https://www.isu-skating.com/example';headers={'Content-Type':'text/html','ETag':'v1'}
  with tempfile.TemporaryDirectory() as td:
   c=Client(td,transport=lambda *a,**kw:Response(b'<html>ok</html>'))
   body,r=c.get(Response.url);self.assertTrue(r['changed'])
   def not_modified(req,**kw):
    self.assertEqual(req.get_header('If-none-match'),'v1')
    raise urllib.error.HTTPError(Response.url,304,'',{},None)
   c2=Client(td,c.records,not_modified);body2,r2=c2.get(Response.url)
   self.assertEqual(body,body2);self.assertFalse(r2['changed'])
 def test_outage_keeps_old_metadata_not_reverified(self):
  def fail(*a,**kw):raise OSError('network unavailable')
  with tempfile.TemporaryDirectory() as td:
   c=Client(td,{'https://www.isu-skating.com/a':{'sha256':'old'}},fail)
   body,r=c.get('https://www.isu-skating.com/a')
   self.assertIsNone(body);self.assertEqual(r['sha256'],'old');self.assertTrue(r['stale'])
 def test_d1_schema_requires_reviewer_for_approval(self):
  db=sqlite3.connect(':memory:');db.executescript((ROOT/'migrations/0001.sql').read_text())
  with self.assertRaises(sqlite3.IntegrityError):
   db.execute("INSERT INTO snapshots(state,sha256,body,created_at) VALUES ('approved','x','{}','now')")


class AdapterEdgeTests(unittest.TestCase):
 def test_synthetic_start_list_is_parsed_as_start_list(self):
  text=(ROOT/'fixtures/synthetic/c51-start-list.txt').read_text()
  p=race_participation(text,EVENT,URL)
  self.assertEqual(len(p),1)
  self.assertEqual(p[0]['evidenceKind'],'start-list')
  first,_,issues=match_athletes(timetable(TEXT,EVENT,URL)[0],p,ALIASES,EVENT)
  self.assertEqual(issues[0]['code'],'opening-day-coverage-unverified');self.assertFalse(first[0]['confirmed'])
 def test_synthetic_junior_c08_repeated_500_and_cancelled_round(self):
  event=json.loads((ROOT/'config/events.json').read_text())[3]
  source='''SYNTHETIC TEST DATA - NOT OFFICIAL
Bormio
DETAILED TIME SCHEDULE
12 NOV 2026 09:00  Men 500 m  Heats (Heats: 4) Race 1
            10:00  Men 500 m  Heats (Heats: 4) Race 2
            10:15  Women 500 m  Rep. Quarterfinals CANCELLED
14 NOV 2026 14:00  Men 500 m  Finals (Heats: 2) Race 2
            14:30  End of Day
'''
  rows,issues=timetable(source,event,URL)
  self.assertEqual(issues,[])
  self.assertEqual([r['occurrence'] for r in rows if r.get('round')=='heats'],[1,2])
  self.assertTrue(next(r for r in rows if r.get('gender')=='women')['cancelled'])
 def test_source_size_cap(self):
  class Response(io.BytesIO):
   status=200;url='https://www.isu-skating.com/example';headers={'Content-Type':'text/html'}
  with tempfile.TemporaryDirectory() as td:
   c=Client(td,transport=lambda *a,**kw:Response(b'x'*(MAX_BYTES+1)))
   body,rec=c.get(Response.url)
   self.assertIsNone(body);self.assertEqual(rec['status'],'unavailable')

if __name__=='__main__':unittest.main()
