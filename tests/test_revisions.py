"""Synthetic authority tests are explicitly distinct from archived Vancouver proof."""
import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from isu_pilot.revisions import version,choose,changes,History
from isu_pilot.programme import programme,pdf_revision
from isu_pilot.pipeline import build,retime_previous,collect
from isu_pilot.pdf import timetable
from isu_pilot.polling import cadence,due

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[0]
ALIASES=json.loads((ROOT/'config/athletes.json').read_text())
from isu_pilot.synthetic import C08 as TEXT,C08_URL as URL,event_html
ONLINE=EVENT['infoUrl']+'?tab=schedule_16230'
ROWS=timetable(TEXT,EVENT,URL)[0]

def variant(kind='pdf',revised=None,number='1.0',changed=False,retrieved='2026-10-29T12:00:00Z'):
 rows=copy.deepcopy(ROWS)
 if changed:
  r=next(r for r in rows if r.get('gender')=='men' and r.get('distance')==500 and r.get('round')=='heats')
  r['startsAt']='2026-10-23T13:53:00-07:00'
 rev={'scope':'whole-event','series':EVENT['id']+(':'+kind),'number':number}
 if revised:rev['revisedAt']=revised
 if kind=='pdf':rev['printedAt']='2026-10-21T21:32:00-07:00'
 return version(EVENT,kind,URL if kind=='pdf' else ONLINE,rows,{'sha256':kind+number,'fetchedAt':retrieved},rev)

class AuthorityTests(unittest.TestCase):
 def test_revised_online_supersedes_older_pdf(self):
  pdf=variant();online=variant('online','2026-10-23',changed=True)
  d=choose([pdf,online]);self.assertEqual(d['selected']['versionId'],online['versionId']);self.assertEqual(d['status'],'resolved')
 def test_revised_pdf_supersedes_older_online(self):
  online=variant('online','2026-10-22',changed=True)
  pdf=variant('pdf','2026-10-23','2.0')
  self.assertEqual(choose([online,pdf])['selected']['versionId'],pdf['versionId'])
 def test_newer_fetch_does_not_determine_authority(self):
  pdf=variant(retrieved='2026-10-30T12:00:00Z');online=variant('online',changed=True,retrieved='2026-10-29T12:00:00Z')
  d=choose([pdf,online]);self.assertEqual(d['status'],'needs-review');self.assertIsNone(d['selected'])
 def test_pdf_print_date_alone_does_not_supersede_online_revision(self):
  pdf=variant();pdf['revision']['printedAt']='2026-10-25T12:00:00-07:00'
  online=variant('online','2026-10-23',changed=True)
  self.assertEqual(choose([pdf,online])['status'],'needs-review')
 def test_revision_number_only_within_same_series(self):
  pdf1=variant();pdf2=variant(number='2.0',changed=True)
  self.assertEqual(choose([pdf1,pdf2])['selected']['versionId'],pdf2['versionId'])
  other=variant('online',number='9.0',changed=True)
  self.assertEqual(choose([pdf1,other])['status'],'needs-review')
 def test_same_day_dates_not_orderable(self):
  self.assertEqual(choose([variant(revised='2026-10-23'),variant('online','2026-10-23',changed=True)])['status'],'needs-review')
 def test_adjacent_day_revision_is_orderable(self):
  d=choose([variant(revised='2026-10-22'),variant('online','2026-10-23',changed=True)])
  self.assertEqual(d['selected']['kind'],'online')
 def test_identical_rounds_do_not_need_revision_order(self):
  a=variant();b=variant('online')
  for r in b['rows']:r['heatCount']=None
  self.assertEqual(choose([a,b])['status'],'resolved')
 def test_stale_or_incomplete_online_cannot_replace_complete_pdf(self):
  online=variant('online','2026-10-24',changed=True);online['complete']=False
  self.assertEqual(choose([variant(),online])['selected']['kind'],'pdf')
 def test_conflict_retains_previous_local_snapshot(self):
  old=variant();new=variant('online',changed=True)
  d=choose([new],old);self.assertEqual(d['status'],'needs-review');self.assertEqual(d['selected']['versionId'],old['versionId'])
 def test_wrong_event_cannot_supersede(self):
  new=variant('online','2026-10-24',changed=True);new['eventId']='other-event'
  self.assertEqual(choose([variant(),new])['status'],'needs-review')

class HistoryTests(unittest.TestCase):
 def test_round_change_report_and_saved_versions(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'history.json');old=variant();h.resolve(EVENT['id'],[old]);h.save()
   new=variant('pdf','2026-10-23','2.0',changed=True)
   h=History(h.path);d=h.resolve(EVENT['id'],[new]);h.save()
   self.assertEqual(len(d['selectedChanges']),1)
   c=d['selectedChanges'][0]
   self.assertEqual(c['previousTime'],'2026-10-23T13:39:00-07:00');self.assertEqual(c['updatedTime'],'2026-10-23T13:53:00-07:00')
   self.assertEqual(c['round'],'heats');self.assertEqual(c['source'],URL)
   self.assertEqual(len(json.loads(h.path.read_text())['sources'][URL]['versions']),2)
 def test_retrieval_update_is_not_schedule_revision(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'history.json');old=variant();h.observe(old)
   new=copy.deepcopy(old);new['retrievedAt']='2026-10-30T10:00:00Z'
   d=h.observe(new);self.assertFalse(d['rawChanged']);self.assertFalse(d['scheduleChanged']);self.assertEqual(d['changes'],[])
 def test_markup_only_change_is_saved_without_round_changes(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'history.json');a=variant();h.observe(a);b=copy.deepcopy(a);b['rawSha256']='new-layout'
   d=h.observe(b);self.assertTrue(d['rawChanged']);self.assertFalse(d['scheduleChanged'])
 def test_failed_check_retains_selected_and_marks_stale(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'history.json');h.resolve(EVENT['id'],[variant()]);d=h.resolve(EVENT['id'],[])
   self.assertEqual(d['status'],'retained-fallback');self.assertTrue(d['stale']);self.assertTrue(d['retainedPrevious']);self.assertEqual(len(d['selected']['rows']),10)
 def test_incomplete_check_retains_previously_verified_athlete_rows(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'schedules.json');h.resolve(EVENT['id'],[variant()])
   report=build(EVENT,TEXT,URL,ALIASES)
   report['athleteFirstStarts'][0]['confirmed']=True
   h.data['events'][EVENT['id']]['report']=report
   class FailedClient:
    root=Path(td)
    def get(self,url):return None,{'error':'network unavailable','status':'unavailable'}
   out=collect([EVENT],ALIASES,{'events':[]},FailedClient(),h)[0]
   self.assertEqual(out['athleteFirstStarts'],report['athleteFirstStarts']);self.assertEqual(out['verificationStatus'],'needs-review')
 def test_new_schedule_retimes_but_does_not_change_starting_round(self):
  old=build(EVENT,TEXT,URL,ALIASES);new=retime_previous(old,variant('online','2026-10-23',changed=True))
  a=next(r for r in old['athleteFirstStarts'] if r['athlete']=='Roberts Krūzbergs' and r['distance']==500)
  b=next(r for r in new['athleteFirstStarts'] if r['athlete']==a['athlete'] and r['distance']==500)
  self.assertEqual(a['round'],b['round']);self.assertEqual(b['startsAt'],'2026-10-23T13:53:00-07:00');self.assertEqual(a['confirmed'],b['confirmed'])
 def test_bounded_history_exposes_pruned_count(self):
  with tempfile.TemporaryDirectory() as td:
   h=History(Path(td)/'history.json',limit=2)
   for n in range(4):h.observe(variant(number=str(n)))
   self.assertEqual(len(h.data['sources'][URL]['versions']),2);self.assertEqual(h.data['sources'][URL]['prunedVersions'],2)

class AdapterTests(unittest.TestCase):
 def html(self,revision='Programme revised: 2026-10-23'):
  return '<section data-isu-programme>'+revision+'<table data-complete="true"><tr><th>Date</th><th>Time</th><th>Event</th><th>Round</th></tr><tr><td>2026-10-23</td><td>13:53</td><td>Men 500 m</td><td>Heats</td></tr><tr><td>2026-10-25</td><td>16:56</td><td>Men 1000 m</td><td>Quarterfinals</td></tr></table></section>'
 def test_rendered_programme_with_scoped_revision(self):
  rows,rev,issues=programme(self.html(),EVENT,ONLINE,True)
  self.assertEqual(issues,[]);self.assertEqual(rev['revisedAt'],'2026-10-23');self.assertEqual(rows[0]['startsAt'],'2026-10-23T13:53:00-07:00')
 def test_global_page_update_ignored(self):
  rows,rev,issues=programme('<p>Page updated: 2026-10-28</p>'+self.html(''),EVENT,ONLINE,True)
  self.assertNotIn('revisedAt',rev)
 def test_incomplete_programme_goes_to_review(self):
  rows,rev,issues=programme(self.html().replace('data-complete="true"',''),EVENT,ONLINE,True)
  self.assertIn('online-completeness-unverified',issues)
 def test_synthetic_shell_is_not_revised_schedule(self):
  text=event_html(EVENT)
  rows,rev,issues=programme(text,EVENT,ONLINE,True)
  self.assertEqual(rows,[]);self.assertNotIn('revisedAt',rev)
 def test_synthetic_c08_revision_not_upload_date(self):
  rev=pdf_revision(TEXT,EVENT)
  self.assertEqual(rev['number'],'1.0');self.assertEqual(rev['printedAt'],'2026-10-21T21:32:00');self.assertEqual(rev['printedTimeZone'],'unspecified');self.assertNotIn('revisedAt',rev)

class PollingTests(unittest.TestCase):
 def test_active_30_minutes_and_distant_daily(self):
  now=datetime(2026,10,23,16,tzinfo=timezone.utc)
  self.assertEqual(cadence(EVENT,now),30)
  self.assertEqual(cadence(EVENT,datetime(2026,9,1,tzinfo=timezone.utc)),1440)
  self.assertEqual(due([EVENT],{EVENT['id']:'2026-10-23T15:45:00+00:00'},now),[])
  self.assertEqual(due([EVENT],{EVENT['id']:'2026-10-23T15:30:00+00:00'},now),[EVENT])
 def test_near_events_and_montreal_dst(self):
  montreal=json.loads((ROOT/'config/events.json').read_text())[1]
  self.assertEqual(cadence(montreal,datetime(2026,10,29,12,tzinfo=timezone.utc)),30)
  self.assertEqual(cadence(montreal,datetime(2026,11,1,18,tzinfo=timezone.utc)),30)
  self.assertEqual(cadence(montreal,datetime(2026,11,2,4,59,tzinfo=timezone.utc)),30)
  self.assertEqual(cadence(montreal,datetime(2026,11,2,5,tzinfo=timezone.utc)),1440)

class AdditionalGuards(unittest.TestCase):
 def test_newer_partial_source_cannot_erase_known_rounds(self):
  older=variant();newer=variant('online','2026-10-24',changed=True)
  newer['rows']=newer['rows'][:3]
  d=choose([newer],older)
  self.assertEqual(d['status'],'needs-review');self.assertEqual(d['selected']['versionId'],older['versionId'])
 def test_synthetic_shell_does_not_prove_supersession(self):
  rows,rev,issues=programme(event_html(EVENT),EVENT,ONLINE,True)
  self.assertEqual(rows,[]);self.assertNotIn('revisedAt',rev)
  self.assertEqual(choose([variant(),variant('online',changed=True)])['status'],'needs-review')
 def test_page_upload_time_not_a_revision_stamp(self):
  from isu_pilot.programme import evidence
  rev=evidence('Protocol uploaded 2026-10-26. Page updated 2026-10-29','America/Vancouver')
  self.assertNotIn('revisedAt',rev)
 def test_future_retrieval_never_overrides_same_day_conflict(self):
  a=variant('pdf','2026-10-23');b=variant('online','2026-10-23',changed=True,retrieved='2030-01-01T12:00:00Z')
  self.assertEqual(choose([a,b])['status'],'needs-review')

class PrintZoneGuard(unittest.TestCase):
 def test_unknown_print_zone_cannot_force_adjacent_day_order(self):
  pdf=variant();pdf['revision']['printedAt']='2026-10-21T23:30:00';pdf['revision']['printedTimeZone']='unspecified'
  online=variant('online','2026-10-22',changed=True)
  self.assertEqual(choose([pdf,online])['status'],'needs-review')
