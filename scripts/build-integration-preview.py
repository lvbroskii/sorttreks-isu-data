"""Reproducible SYNTHETIC preview using the actual collector projector and site baseline."""
import copy,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from isu_pilot.feed import export,file_sha
root=Path(__file__).resolve().parents[1]
base=root/'fixtures/integration/website-baseline.json';data=json.loads(base.read_text());event=data['events'][1]
url=event['infoUrl'];api='https://front-api.isu.org/events/getschedule/isu-short-track-world-tour-2-montreal'
now=datetime(2026,10,29,15,0,tzinfo=timezone.utc)
rows=[{'gender':'men','distance':500,'round':'preliminaries','occurrence':1,'startsAt':'2026-10-30T09:20:00-04:00','date':'2026-10-30','sourceUrl':api,'kind':'race','discipline':'individual'},
 {'gender':'men','distance':500,'round':'heats','occurrence':1,'startsAt':'2026-10-30T13:20:00-04:00','date':'2026-10-30','sourceUrl':api,'kind':'race','discipline':'individual'},
 {'gender':'men','distance':500,'round':'quarterfinals','occurrence':1,'startsAt':'2026-10-31T13:00:00-04:00','date':'2026-10-31','sourceUrl':api,'kind':'race','discipline':'individual'},
 {'gender':'men','distance':1000,'round':'finals','occurrence':1,'startsAt':'2026-11-01T13:00:00-05:00','date':'2026-11-01','sourceUrl':api,'kind':'race','discipline':'individual'}]
report={'validationType':'synthetic-not-official','event':{k:event[k] for k in ('id','timeZone','startDate','endDate','infoUrl')},'schedule':rows,'scheduleAuthority':{'status':'resolved','selectedVersionId':'synthetic-v1','stale':False},'discovery':{'identityVerified':True},'liveApi':{'programmeComplete':True,'participants':[]},'scheduleVersions':[{'versionId':'synthetic-v1','complete':True,'rawSha256':'1'*64,'url':api,'retrievedAt':now.isoformat(),'revision':{'scope':'schedule','sequence':1}}],'publication':{'stages':{'athleteDraws':{},'sessions':{'rows':[]}}}}
def build(report,previous=None):
 sha=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()
 approval={'reportSha256':sha,'reviewer':'SYNTHETIC PREVIEW - NOT A REAL APPROVAL','reviewedAt':now.isoformat()}
 return export(report,approval,sha,file_sha(base),previous,synthetic=True,now=now)
feeds={};feeds['schedule']=build(report)
draw='https://front-api.isu.org/events/get-event-result-round-heats-stk-single'
report['feedDrawSources']=[{'url':draw,'sha256':'2'*64,'retrievedAt':now.isoformat(),'revision':{'note':'synthetic test draw'}}]
for name,rd in [('Reinis Bērziņš','preliminaries'),('Roberts Krūzbergs','heats')]:
 r=next(r for r in rows if r['round']==rd);a={k:r[k] for k in ('gender','distance','round','occurrence','startsAt')};a.update(athlete=name,sourceUrl=draw,confirmed=True)
 report['publication']['stages']['athleteDraws'][name]={'firstStarts':[a],'laterStarts':[]}
 report['liveApi']['participants'].append(a|{'matchedAthlete':name,'evidenceKind':'start-list','openingDayCoverageComplete':True,'date':'2026-10-30'})
feeds['draws']=build(report,feeds['schedule'])
report=copy.deepcopy(report);report['schedule'][1]['startsAt']='2026-10-30T13:35:00-04:00';report['publication']['stages']['athleteDraws']['Roberts Krūzbergs']['firstStarts'][0]['startsAt']=report['schedule'][1]['startsAt'];report['scheduleAuthority']['selectedVersionId']='synthetic-v2';report['scheduleVersions'][0].update(versionId='synthetic-v2',rawSha256='3'*64,revision={'scope':'schedule','sequence':2})
feeds['revised']=build(report,feeds['draws'])
# Explicit session evidence is separate from round evidence and makes countdown update possible.
report['publication']['stages']['sessions']['rows']=[{'id':'session-example','title':'Synthetic qualification session','startsAt':'2026-10-30T09:00:00-04:00','endsAt':None,'verificationStatus':'verified','timeBasis':'session-start','sourceUrl':url}]
report['feedSessionSources']=[{'url':url,'sha256':'4'*64,'retrievedAt':now.isoformat(),'revision':{'note':'synthetic session evidence'}}]
sha=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest();approval={'reportSha256':sha,'reviewer':'SYNTHETIC PREVIEW','reviewedAt':now.isoformat(),'sessionMappings':[{'sourceId':'session-example','siteId':'qualifications','label':{'lv':'Priekšsacīkstes','en':'Qualifications'}}]}
feeds['session']=export(report,approval,sha,file_sha(base),feeds['revised'],True,now)
feeds['conflict']=copy.deepcopy(feeds['revised']);feeds['conflict']['events'][0]['approval']['basis']='unresolved-source-conflict'
for name,feed in feeds.items():(root/f'fixtures/integration/{name}.json').write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n')
print('Built five synthetic fixtures; none are official Montreal times or draws. Baseline digest:',file_sha(base))
