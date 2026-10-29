"""Offline review/export boundary. Collector results never approve themselves.

No network, Git writes, Cloudflare calls or changes to the monitoring campaign.
"""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .revisions import digest

SCHEMA='sorttreks.calendar.v1'

def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def project(report, approval, report_sha):
    if approval.get('reportSha256')!=report_sha or not approval.get('reviewer','').strip():
        raise ValueError('Approval must bind the exact reviewed report bytes and name the reviewer')
    authority=report.get('scheduleAuthority',{})
    if (authority.get('status')!='resolved' or authority.get('stale') 
        or not report.get('discovery',{}).get('identityVerified') or not report.get('liveApi',{}).get('programmeComplete')):
        raise ValueError('Unresolved, incomplete, stale or unidentified programme - retain approved feed')
    if any(c.get('status')!='match' for c in report.get('comparison',[])):
        raise ValueError('Manual baseline conflict requires separate source-authority review')
    version=next((v for v in report.get('scheduleVersions',[]) if v['versionId']==authority.get('selectedVersionId')),None)
    if not version or not version.get('complete') or not version.get('rawSha256'):
        raise ValueError('Selected version lacks complete source evidence')
    event=report['event'];rows=[]
    for r in report.get('schedule',[]):
        if r.get('cancelled'):raise ValueError('Cancellation/removal requires a future explicit review contract')
        if r.get('kind')=='race' and r.get('discipline')=='individual':
            rows.append({k:r[k] for k in ('gender','distance','round','occurrence','startsAt','sourceUrl')}|{'timeBasis':'round-start'})
    if not rows:raise ValueError('No individual round programme')
    sources=[{'url':version['url'],'sha256':version['rawSha256'],'retrievedAt':version['retrievedAt'],'revision':version.get('revision',{})}]
    # Confirmations come from the existing publication assessor, never the optimistic patch.
    first=[];later=[]
    for athlete in report.get('publication',{}).get('stages',{}).get('athleteDraws',{}).values():
        for target,field in ((first,'firstStarts'),(later,'laterStarts')):
            for a in athlete.get(field,[]):
                if not a.get('confirmed'):continue
                observation=next((p for p in report.get('liveApi',{}).get('participants',[]) if p.get('matchedAthlete')==a['athlete'] and p.get('evidenceKind')=='start-list' and all(p.get(k)==a.get(k) for k in ('gender','distance','round','occurrence')) and p.get('date')==a['startsAt'][:10]),None)
                if not observation or field=='firstStarts' and not observation.get('openingDayCoverageComplete'):
                    raise ValueError('Assignment lacks event-specific start-list coverage')
                draw_sources=report.get('feedDrawSources',[])+[{'url':o['source']['url'],'sha256':o['source'].get('sha256'),'retrievedAt':o['source'].get('fetchedAt'),'revision':{'kind':'event-specific-start-list'}} for o in report.get('liveApi',{}).get('rounds',[]) if o.get('kind')=='heat-draw' and o.get('complete') and o.get('source',{}).get('sha256')]
                draw_source=next((s for s in draw_sources if s.get('url')==a['sourceUrl']),None)
                # The upstream collector must supply raw source evidence; do not fabricate a hash.
                if not draw_source:raise ValueError('Draw response provenance must be supplied for review')
                if draw_source not in sources:sources.append(draw_source)
                r=next((r for r in rows if all(r[k]==a[k] for k in ('gender','distance','round','occurrence','startsAt'))),None)
                if not r:raise ValueError('Draw/round mismatch')
                target.append({k:a[k] for k in ('athlete','gender','distance','round','occurrence','startsAt','sourceUrl')}|{'roundSourceUrl':r['sourceUrl'],'timeBasis':'round-start','evidenceKind':'start-list','openingDayCoverageComplete':bool(observation.get('openingDayCoverageComplete'))})
    # Session identity mapping is a distinct reviewed input. No inference from race rows.
    sessions=[]
    for mapping in approval.get('sessionMappings',[]):
        s=next((s for s in report.get('publication',{}).get('stages',{}).get('sessions',{}).get('rows',[]) if s.get('id')==mapping['sourceId']),None)
        if not s or s.get('timeBasis')!='session-start' or s.get('verificationStatus')!='verified':raise ValueError('Unverified session mapping')
        source=next((p for p in report.get('feedSessionSources',[]) if p.get('url')==s['sourceUrl']),None)
        if not source:raise ValueError('Missing session source provenance')
        if source not in sources:sources.append(source)
        sessions.append({'id':mapping['siteId'],'label':mapping['label'],'startsAt':s['startsAt'],'endsAt':s.get('endsAt') if s.get('endVerified') else None,'sourceUrl':s['sourceUrl'],'timeBasis':'session-start'})
    return {k:event[k] for k in ('id','timeZone','startDate','endDate')}|{
        'approval':{'reviewer':approval['reviewer'],'reviewedAt':approval['reviewedAt'],'reportSha256':report_sha,'authorityVersionId':version['versionId'],'basis':'resolved-official-programme'},
        'sources':sources,'rounds':rows,'firstStarts':first,'laterStarts':later,'sessions':sessions,'links':{'infoUrl':event['infoUrl']}}

def export(report, approval, report_sha, baseline_digest, previous=None, synthetic=False, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Aware UTC time required')
    if not synthetic and any(report.get(k)=='synthetic-not-official' for k in ('validationType','mode','kind')):raise ValueError('Synthetic reports cannot receive production approval')
    event=project(report,approval,report_sha)
    events=copy.deepcopy((previous or {}).get('events',[]))
    old=next((e for e in events if e['id']==event['id']),None)
    if previous and previous['baselineDigest']!=baseline_digest:raise ValueError('Baseline changed; re-review required')
    if previous and previous['kind']!=('synthetic-not-official' if synthetic else 'approved'):raise ValueError('Cannot mix synthetic and real approval history')
    if old:
        def key(r):return (r['startsAt'][:10],r['gender'],r['distance'],r['round'],r['occurrence'])
        if not {key(r) for r in old['rounds']}<={key(r) for r in event['rounds']}:raise ValueError('Programme reduction requires review; keep previous feed')
        # Retain previously approved draws; retime only uniquely matched same round identities.
        current={key(r):r for r in event['rounds']}
        for field in ('firstStarts','laterStarts'):
            for a in old[field]:
                if not any(x['athlete']==a['athlete'] and key(x)==key(a) for x in event[field]):
                    r=current[key(a)];event[field].append(a|{'startsAt':r['startsAt'],'roundSourceUrl':r['sourceUrl']})
                    for s in old['sources']:
                        if s['url']==a['sourceUrl'] and s not in event['sources']:event['sources'].append(s)
        for session in old['sessions']:
            if not any(s['id']==session['id'] for s in event['sessions']):event['sessions'].append(session)
        event['sources']+=[s for s in old['sources'] if s not in event['sources']]
        events[events.index(old)]=event
    else:events.append(event)
    return {'schemaVersion':SCHEMA,'kind':'synthetic-not-official' if synthetic else 'approved','revision':(previous or {}).get('revision',0)+1,
            'issuedAt':now.isoformat(timespec='seconds'),'validUntil':(now+timedelta(hours=6)).isoformat(timespec='seconds'),
            'baselineDigest':baseline_digest,'events':events}

def main():
    p=argparse.ArgumentParser(description='Offline, explicit review exporter. Never publishes anything.')
    p.add_argument('--report',type=Path,required=True);p.add_argument('--approval',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raw=a.report.read_bytes();report=json.loads(raw)
    # Accept a monitor envelope or a single existing collector event report.
    if 'scheduleAuthority' not in report:report=report.get('event') if isinstance(report.get('event'),dict) and 'scheduleAuthority' in report['event'] else report['events'][0]
    output=export(report,json.loads(a.approval.read_text()),hashlib.sha256(raw).hexdigest(),file_sha(a.baseline),json.loads(a.previous.read_text()) if a.previous else None)
    # Validate with the exact browser/Worker validator before writing a usable feed.
    import subprocess
    body=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
    result=subprocess.run(['node','--input-type=module','-e',"import {validateFeed} from './integration/feed.mjs';let s='';for await(const b of process.stdin)s+=b;validateFeed(JSON.parse(s));"],input=body,text=True,capture_output=True)
    if result.returncode:raise ValueError('Feed validation failed: '+result.stderr)
    a.out.parent.mkdir(parents=True,exist_ok=True);temp=a.out.with_suffix('.tmp');temp.write_text(body);temp.replace(a.out)
    print('Approved local JSON written; no publication or deployment performed.')

if __name__=='__main__':main()
