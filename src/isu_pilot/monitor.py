"""One finite Montreal monitoring check. Invocation never enables a scheduler."""
import copy
import hashlib
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from .archive import Archive,load,write
from .sources import Client
from .pipeline import collect
from .revisions import version,changes
from .live_api import schedule,BASE
from .timezones import display

MiB=1024*1024


def instant(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def plan(config,state,now):
    if now.tzinfo is None:raise ValueError('Monitoring clock must be timezone-aware')
    if not instant(config['startsAt'])<=now<instant(config['endsAt']):return 'outside-campaign-window'
    last=state.get('lastCheckAt')
    if last and now-instant(last)<timedelta(minutes=config['intervalMinutes'],seconds=-60):return 'not-due'
    return 'due'


def seed(root,event,state_dir,monitor):
    """Actual prior empty capture, labelled historical; never re-verified as fresh."""
    if monitor.get('baselineInitialized'):return
    path=Path(root)/'config/monitoring.json';config=load(path,{})
    manifest_path=Path(root)/config['baselineManifest']
    manifest=load(manifest_path,{})
    url=BASE+'/events/getschedule/'+event['infoUrl'].rstrip('/').split('/')[-1]
    record=next(r for r in manifest['sources'] if r['url']==url and r['httpStatus']==200)
    body=(manifest_path.parent/record['file']).read_bytes()
    if hashlib.sha256(body).hexdigest()!=record['sha256']:raise ValueError('Bootstrap capture hash mismatch')
    rows,issues=schedule(body,event,url,True)
    if rows or issues!=['live-api-programme-unpublished']:raise ValueError('Expected actual empty-programme baseline')
    Path(state_dir).mkdir(parents=True,exist_ok=True)
    (Path(state_dir)/(record['sha256']+'.body')).write_bytes(body)
    monitor.update(baselineInitialized=True,lastProgrammeState='empty',
                   emptyEvidence={'sha256':record['sha256'],'retrievedAt':record['fetchedAt'],'url':url,
                                  'historicalBootstrap':True},firstPublishedProgramme=None,
                   lastProgrammeVersion=None)


def observe(event,body,record,identity,monitor):
    """Record observation ordering, not sporting authority or a guessed revision date."""
    result={'status':'unavailable','firstPublicationDetected':False,'roundChanges':[],'rounds':[]}
    if body is None:return result
    rows,issues=schedule(body,event,record['url'],identity)
    if issues==['live-api-programme-unpublished']:
        evidence={'sha256':record['sha256'],'retrievedAt':record['fetchedAt'],'url':record['url']}
        monitor.setdefault('firstEmptyEvidence',copy.deepcopy(monitor.get('emptyEvidence',evidence)))
        monitor['emptyEvidence']=evidence
        monitor['lastProgrammeState']='empty'
        result['status']='empty';return result
    if not rows or any('invalid' in i or 'identity' in i for i in issues):
        result.update(status='unsupported-or-unverified',issues=issues);return result
    candidate=version(event,'online',record['url'],rows,record,{},issues)
    prior=monitor.get('lastProgrammeVersion')
    result.update(status='populated-round-data',issues=issues,roundChanges=changes(prior,candidate) if prior else [],
                  rounds=[{**r,'latvianTime':{'lv':display(r['startsAt']),'en':display(r['startsAt'],lang='en')}} for r in rows])
    if not monitor.get('firstPublishedProgramme'):
        first={'sha256':record['sha256'],'retrievedAt':record['fetchedAt'],'url':record['url'],
               'roundCount':len(rows),'previousEmptyEvidence':copy.deepcopy(monitor.get('emptyEvidence')),
               'validationStatus':'candidate-needs-cross-source-validation','isRevisionTimestamp':False}
        monitor['firstPublishedProgramme']=first
        result['firstPublicationDetected']=True
    monitor['lastProgrammeState']='populated-round-data'
    monitor['lastProgrammeVersion']=candidate
    # Empty/failed checks never replace the last parseable round snapshot.
    return result


def run(root,state_dir,archive_dir,now=None,client_factory=Client):
    root=Path(root);state_dir=Path(state_dir);now=now or datetime.now(timezone.utc)
    config=load(root/'config/monitoring.json',{})
    archive=Archive(archive_dir);archive.restore(state_dir)
    monitor=load(state_dir/'monitor-state.json',{})
    if monitor.get('eventId') not in (None,config['eventId']):raise ValueError('Monitoring state belongs to another event')
    monitor['eventId']=config['eventId']
    decision=plan(config,monitor,now)
    if decision!='due':return {'status':decision,'checkedAt':now.isoformat(timespec='seconds'),'approvedForWebsite':False}
    if archive.size()>(config['archiveLimitMiB']-config['reserveMiB'])*MiB:
        return {'status':'archive-cap-monitoring-paused','checkedAt':now.isoformat(timespec='seconds'),
                'approvedForWebsite':False,'reason':'Evidence retained. No source reads; export/archive review required.'}
    events=load(root/'config/events.json',[])
    event=next(e for e in events if e['id']==config['eventId'])
    seed(root,event,state_dir,monitor)
    previous=load(state_dir/'sources.json',{})
    client=client_factory(state_dir,previous,byte_budget=config['runDownloadLimitMiB']*MiB,raw_sink=archive.add)
    error=None;event_report=None
    try:
        event_report=collect([event],load(root/'config/athletes.json',{}),load(root/'config/site-reference.json',{}),client)[0]
    except Exception as err:
        # Persist responses already retrieved even when parsing fails. Caller marks job failed.
        error=type(err).__name__+': '+str(err)[:300]
    programme=next((r for u,r in client.records.items() if '/events/getschedule/' in u),None)
    observation={'status':'unavailable','firstPublicationDetected':False,'roundChanges':[],'rounds':[]}
    if programme:
        observation=observe(event,client.body(programme),programme,
                            bool(event_report and event_report.get('discovery',{}).get('identityVerified')),monitor)
    monitor['lastCheckAt']=now.isoformat(timespec='seconds')
    if event_report and event_report.get('liveApi',{}).get('programmeComplete') and not monitor.get('firstStructurallyValidatedProgramme'):
        monitor['firstStructurallyValidatedProgramme']={'sha256':programme['sha256'],'retrievedAt':programme['fetchedAt']}
    report={'schemaVersion':1,'mode':'read-only-montreal-monitor','checkedAt':monitor['lastCheckAt'],
            'status':'collector-error' if error else observation['status'],'collectorError':error,
            'firstPublicationDetected':observation['firstPublicationDetected'],
            'programmeObservation':observation,'firstPublishedProgramme':monitor.get('firstPublishedProgramme'),
            'firstStructurallyValidatedProgramme':monitor.get('firstStructurallyValidatedProgramme'),
            'event':event_report,'sources':client.records,'approvedForWebsite':False,
            'fallback':'existing verified data retained; no website writes'}
    write(state_dir/'sources.json',{**previous,**client.records});write(state_dir/'monitor-state.json',monitor)
    archive.persist(state_dir,report)
    return report
