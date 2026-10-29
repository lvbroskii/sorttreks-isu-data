import copy,json,unittest
from datetime import datetime,timezone
from isu_pilot.feed import export,project
class FeedTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,29,15,tzinfo=timezone.utc);self.sha='a'*64
  self.report={'event':{'id':'2026-27-wt2','timeZone':'America/Toronto','startDate':'2026-10-30','endDate':'2026-11-01','infoUrl':'https://www.isu-skating.com/en/short-track/events/eventdetail/isu-short-track-world-tour-2-montreal/'},'scheduleAuthority':{'status':'resolved','selectedVersionId':'v1'},'discovery':{'identityVerified':True},'liveApi':{'programmeComplete':True},'scheduleVersions':[{'versionId':'v1','complete':True,'rawSha256':self.sha,'url':'https://front-api.isu.org/example','retrievedAt':self.now.isoformat()}],'schedule':[{'kind':'race','discipline':'individual','gender':'men','distance':500,'round':'heats','occurrence':1,'startsAt':'2026-10-30T09:00:00-04:00','sourceUrl':'https://front-api.isu.org/example'}]}
  self.approval={'reviewer':'Synthetic test reviewer','reviewedAt':self.now.isoformat(),'reportSha256':self.sha}
 def test_schedule_without_draws_is_not_an_athlete_confirmation(self):
  f=export(self.report,self.approval,self.sha,self.sha,synthetic=True,now=self.now);self.assertEqual(f['events'][0]['firstStarts'],[]);self.assertEqual(f['kind'],'synthetic-not-official')
 def test_hash_approval_and_authority_are_required(self):
  for edit in [lambda r:r['scheduleAuthority'].update(status='needs-review'),lambda r:r['scheduleAuthority'].update(stale=True),lambda r:r['liveApi'].update(programmeComplete=False),lambda r:r['discovery'].update(identityVerified=False),lambda r:r.update(comparison=[{'status':'different'}]),lambda r:r['schedule'][0].update(cancelled=True)]:
   with self.subTest(edit=edit):
    r=copy.deepcopy(self.report);edit(r)
    with self.assertRaises(ValueError):project(r,self.approval,self.sha)
  with self.assertRaises(ValueError):project(self.report,self.approval,'b'*64)
 def test_revision_and_reduction(self):
  old=export(self.report,self.approval,self.sha,self.sha,synthetic=True,now=self.now)
  r=copy.deepcopy(self.report);r['schedule'][0]['startsAt']='2026-10-30T09:10:00-04:00'
  new=export(r,self.approval,self.sha,self.sha,old,True,self.now);self.assertEqual(new['revision'],2)
  r['schedule'][0]['round']='finals'
  with self.assertRaises(ValueError):export(r,self.approval,self.sha,self.sha,old,True,self.now)
 def test_empty_draw_and_session_evidence_cannot_be_approved(self):
  r=copy.deepcopy(self.report);r['publication']={'stages':{'athleteDraws':{'x':{'firstStarts':[{'confirmed':True,'athlete':'x','sourceUrl':'x','startsAt':'2026-10-30T09:00:00-04:00','gender':'men','distance':500,'round':'heats','occurrence':1}]}}}}
  with self.assertRaises(ValueError):project(r,self.approval,self.sha)
  with self.assertRaises(ValueError):project(self.report,self.approval|{'sessionMappings':[{'sourceId':'absent'}]},self.sha)
 def test_public_export_cannot_relabel_a_synthetic_report_as_official(self):
  with self.assertRaises(ValueError):export(self.report|{'validationType':'synthetic-not-official'},self.approval,self.sha,self.sha,now=self.now)
