import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from .pipeline import offline,collect
from .sources import Client
from .polling import due,cadence


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description='Read-only collector: never updates sorttreks.lv or Cloudflare')
    parser.add_argument('mode',choices=['sample','api-sample','collect','publication','monitor'])
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--out',type=Path,default=Path('out'))
    parser.add_argument('--archive',type=Path,default=Path('.archive'))
    parser.add_argument('--state',type=Path,default=Path('.state'))
    parser.add_argument('--due-only',action='store_true',help='Use persisted adaptive check times')
    parser.add_argument('--event',help='Optional registry id')
    args=parser.parse_args();root=args.root
    if args.mode=='monitor':
        from .monitor import run
        result=run(root,args.state,args.archive)
        dump(args.out/'report.json',result)
        summary=['# Montreal read-only monitoring','',f'Status: {result["status"]}',f'Checked: {result["checkedAt"]}',
                 'No website writes, deployment or paid services.','']
        if result.get('firstPublicationDetected'):summary+=['FIRST RACE-ROUND PUBLICATION OBSERVED (candidate; not an approved feed).','']
        if result.get('firstPublishedProgramme'):summary+=[json.dumps(result['firstPublishedProgramme'],ensure_ascii=False),'']
        for row in result.get('programmeObservation',{}).get('roundChanges',[]):
            summary.append(f'- {row["date"]} {row["gender"]} {row["distance"]} m {row["round"]}: {row["previousTime"]} -> {row["updatedTime"]}; {row["source"]}')
        if result.get('event'):
            summary += ['Authority: '+result['event']['scheduleAuthority']['status'],
                        'Publication stages: '+json.dumps(result['event']['publication']['stages'],ensure_ascii=False)]
        if result.get('reason'):summary+=[result['reason']]
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'summary.md').write_text('\n'.join(summary)+'\n')
        print('\n'.join(summary))
        if result['status'] in ('collector-error','archive-cap-monitoring-paused'):raise SystemExit(2)
        return
    elif args.mode=='publication':
        from .publication import check
        if not args.event:parser.error('publication requires --event')
        events=json.loads((root/'config/events.json').read_text())
        event=next((e for e in events if e['id']==args.event),None)
        if event is None:parser.error('Unknown event id')
        aliases=json.loads((root/'config/athletes.json').read_text())
        state_path=args.state/'sources.json'
        previous=json.loads(state_path.read_text()) if state_path.is_file() else {}
        observations_path=args.state/'publication-observations.json'
        observations=json.loads(observations_path.read_text()) if observations_path.is_file() else {}
        checks=observations.setdefault(event['id'],[])
        client=Client(args.state,previous)
        result=check(event,client,aliases,checks[-1]['publication'] if checks else None)
        now=datetime.now(timezone.utc).isoformat(timespec='seconds')
        checks.append({'checkedAt':now,'publication':result['publication'],'changes':result['publicationChanges']})
        observations[event['id']]=checks[-256:]
        dump(observations_path,observations);dump(state_path,{**previous,**client.records})
        report={'mode':'read-only-publication-check','collectedAt':now,'events':[result],
                'sources':client.records,'approvedForWebsite':False}
    elif args.mode=='api-sample':
        from .captured import replay
        report=replay(root)
    elif args.mode=='sample':
        result=offline(root);dump(args.out/'vancouver.json',result)
        dump(args.out/'vancouver-revision-validation.json',result['revisionValidation'])
        report={'mode':'read-only-offline-validation','events':[result],'approvedForWebsite':False}
    else:
        events=json.loads((root/'config/events.json').read_text())
        if args.event:
            events=[e for e in events if e['id']==args.event]
            if not events:parser.error('Unknown event id')
        now=datetime.now(timezone.utc)
        polling_path=args.state/'polling.json'
        last_checks=json.loads(polling_path.read_text()) if polling_path.is_file() else {}
        if args.due_only:events=due(events,last_checks,now)
        aliases=json.loads((root/'config/athletes.json').read_text())
        reference=json.loads((root/'config/site-reference.json').read_text())
        state_path=args.state/'sources.json'
        previous=json.loads(state_path.read_text()) if state_path.is_file() else {}
        client=Client(args.state,previous)
        rows=collect(events,aliases,reference,client)
        # Monitor actual official classification pages separately from race results.
        standings={}
        for key,url in (json.loads((root/'config/standings-sources.json').read_text()).items() if events else []):
            body,rec=client.get(url)
            standings[key]={'sourceUrl':url,'status':rec['status'],'sha256':rec.get('sha256'),
                            'verificationStatus':'needs-review','positions':None,
                            'reason':'Classification row extraction not yet validated; never substitute World Rankings or race placements.'}
        dump(state_path,{**previous,**client.records})
        for event in events:last_checks[event['id']]=now.isoformat(timespec='seconds')
        dump(polling_path,last_checks)
        report={'mode':'read-only-live-collection','collectedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'pollingIntervalsMinutes':{e['id']:cadence(e,now) for e in events},'events':rows,'standings':standings,'sources':client.records,'approvedForWebsite':False}
    dump(args.out/'report.json',report)
    summary=['# ISU read-only pilot','',f'Mode: {report["mode"]}', 'No website writes or approved-feed publication.','']
    for item in report['events']:
        summary += [f'## {item["event"]["title"]}',f'Status: {item["verificationStatus"]}',
                    f'Issues: {json.dumps(item["issues"],ensure_ascii=False)}','']
        if item.get('revisionValidation'):
            summary += ['Vancouver revision validation: supersession NOT established from saved source evidence.',item['revisionValidation']['archiveLimitation'],'Existing manual website data must be retained.']
        if item.get('publication'):
            summary += [f'Publication stages: {json.dumps(item["publication"]["stages"],ensure_ascii=False)}','']
        authority=item.get('scheduleAuthority')
        if authority:
            summary += [f'Authority: {authority["status"]} - {authority["reason"]}',f'Selected source: {authority.get("selectedSource")}',f'Previous data retained: {authority.get("retainedPrevious",False)}; stale: {authority.get("stale",False)}']
            for update in authority.get('sourceChanges',[]):
                for change in update['changes']:
                    summary.append(f'- {change["date"]} {change["gender"]} {change["distance"]} m {change["round"]}: {change["previousTime"]} -> {change["updatedTime"]}; {change["source"]}')
        for c in item.get('comparison',[]):
            summary.append(f'- {c["athlete"]}, {c["distance"]} m: {c["status"]}; website {c["expected"]}; extracted {c["actual"]}')
    (args.out/'summary.md').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary))

if __name__=='__main__':main()
