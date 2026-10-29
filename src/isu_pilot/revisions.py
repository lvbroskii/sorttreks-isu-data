"""Schedule-specific revision evidence, conservative authority selection and history.

A fetchedAt/HTTP Last-Modified/CMS page updated_at is never schedule authority.
"""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KEY_FIELDS = ('date','gender','distance','discipline','round','occurrence')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def key(row):
    return '|'.join(str(row.get(k,'')) for k in KEY_FIELDS)


def race_rows(version):
    return {key(r):r for r in version.get('rows',[]) if r.get('kind')=='race'}


def changes(before,after):
    old=race_rows(before or {});new=race_rows(after or {})
    result=[]
    for k in sorted(old.keys()|new.keys()):
        a,b=old.get(k),new.get(k)
        if a and b and a['startsAt']==b['startsAt'] and bool(a.get('cancelled'))==bool(b.get('cancelled')):continue
        result.append({'roundKey':k,'round':(b or a)['round'],'distance':(b or a)['distance'],
                       'date':(b or a)['date'],'gender':(b or a)['gender'],'occurrence':(b or a).get('occurrence',1),
                       'previousTime':a['startsAt'] if a else None,'updatedTime':b['startsAt'] if b else None,
                       'previousCancelled':bool(a.get('cancelled')) if a else None,
                       'updatedCancelled':bool(b.get('cancelled')) if b else None,
                       'change':'added' if not a else 'removed' if not b else 'cancelled' if b.get('cancelled') else 'updated',
                       'previousSource':(before or {}).get('url'),'source':(after or {}).get('url')})
    return result


def semantic_hash(rows):
    # Includes breaks/ends, but excludes retrieval/page/layout metadata.
    return digest([{k:r.get(k) for k in (*KEY_FIELDS,'kind','startsAt','cancelled','heatCount')} for r in rows])


def version(event,kind,url,rows,record,revision=None,issues=None):
    ids=[key(r) for r in rows if r.get('kind')=='race']
    valid=bool(ids) and len(ids)==len(set(ids)) and not issues
    sem=semantic_hash(rows)
    rev=revision or {}
    return {'versionId':digest({'event':event['id'],'url':url,'semanticHash':sem,'revision':rev}),
            'eventId':event['id'],'kind':kind,'url':url,'timeZone':event['timeZone'],
            'rawSha256':record.get('sha256'),'retrievedAt':record.get('fetchedAt'),
            'revision':rev,'semanticHash':sem,'rows':rows,'complete':valid,'issues':issues or [],
            'identityVerified':True}


def interval(value,zone):
    """Date-only evidence has day precision; same-day order cannot be assumed."""
    if not value:return None
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if len(value)==10:
            start=d.replace(tzinfo=ZoneInfo(zone))
            return start.astimezone(timezone.utc),(start+timedelta(days=1)).astimezone(timezone.utc)-timedelta(microseconds=1)
        if d.tzinfo is None:return None
        return d.astimezone(timezone.utc),d.astimezone(timezone.utc)
    except (ValueError,TypeError):return None


def dominates(a,b):
    """Return a reviewable reason when a explicitly supersedes b."""
    if a['eventId']!=b['eventId']:return None
    ra,rb=a.get('revision',{}),b.get('revision',{})
    # A partial replacement may not erase known rounds, even with a newer stamp.
    # Explicit cancellations must retain a keyed cancelled row for review.
    if not set(race_rows(b))<=set(race_rows(a)):return None
    # Cross-source revision must explicitly cover the whole schedule, not a news/page edit.
    if ra.get('scope')!='whole-event':return None
    if b['versionId'] in ra.get('supersedesVersionIds',[]):return 'explicit-schedule-supersession'
    # Revision numbers compare only within the same scoped document series.
    if ra.get('series') and ra.get('series')==rb.get('series'):
        try:
            an=tuple(int(x) for x in str(ra['number']).split('.'))
            bn=tuple(int(x) for x in str(rb['number']).split('.'))
            if an>bn:return 'higher-revision-in-same-schedule-series'
        except (KeyError,ValueError):pass
    # A schedule-specific REVISED/UPDATED stamp can supersede an earlier schedule
    # revision, or an older PDF C08 edition whose own print stamp predates it.
    # A later PDF print/upload time alone cannot supersede a revised online programme.
    revised=interval(ra.get('revisedAt'),a['timeZone'])
    baseline=interval(rb.get('revisedAt') or (rb.get('printedAt') if b['kind']=='pdf' else None),b['timeZone'])
    if not rb.get('revisedAt') and b['kind']=='pdf' and rb.get('printedTimeZone')=='unspecified':
        try:
            printed=datetime.fromisoformat(rb['printedAt']).replace(tzinfo=timezone.utc)
            # The PDF does not state its print clock zone. Bound every plausible
            # civil offset instead of inventing a Vancouver offset for that stamp.
            baseline=(printed-timedelta(hours=14),printed+timedelta(hours=14))
        except (KeyError,ValueError):baseline=None
    if revised and baseline and revised[0]>baseline[1]:return 'later-explicit-whole-schedule-revision'
    return None


def choose(versions,previous=None):
    usable=[v for v in versions if v.get('complete') and v.get('identityVerified')]
    # Include the last selected local snapshot: a transient partial source cannot roll it back.
    if previous and previous.get('complete') and not any(v['versionId']==previous['versionId'] for v in usable):
        usable.append(previous)
    if not usable:return {'status':'unavailable','selected':None,'reason':'no-complete-identity-matched-schedule','conflicts':[]}
    unique={v['versionId']:v for v in usable};usable=list(unique.values())
    candidates=[]
    for a in usable:
        reasons=[]
        for b in usable:
            if a['versionId']==b['versionId']:continue
            if not changes(a,b):reasons.append('same-round-times-and-status');continue
            reason=dominates(a,b)
            if not reason:break
            reasons.append(reason)
        else:candidates.append((a,reasons))
    if candidates and not any(changes(candidates[0][0],a) for a,_ in candidates[1:]):
        # Prefer a currently retrieved wrapper with agreeing round content. A
        # previous wrapper is preferred only when it is also present now.
        # Selection never compares retrieval timestamps for sporting authority.
        current_ids={v['versionId'] for v in versions if v.get('complete')}
        selected=next((a for a,_ in candidates if previous and a['versionId']==previous['versionId'] and a['versionId'] in current_ids),candidates[0][0])
        return {'status':'resolved','selected':copy.deepcopy(selected),
                'reason':'single-complete-source' if len(usable)==1 else '; '.join(sorted(set(r for _,rs in candidates for r in rs))),
                'conflicts':[]}
    conflicts=[]
    for i,a in enumerate(usable):
        for b in usable[i+1:]:
            if changes(a,b):
                conflicts.append({'leftVersion':a['versionId'],'rightVersion':b['versionId'],'changes':changes(a,b)})
    return {'status':'needs-review','selected':copy.deepcopy(previous),
            'reason':'conflicting-schedules-without-proven-supersession','conflicts':conflicts}


class History:
    """Bounded normalized history. Raw bodies are independently content-addressed."""
    def __init__(self,path,limit=64):
        self.path=Path(path);self.limit=limit
        self.data=json.loads(self.path.read_text()) if self.path.is_file() else {'schemaVersion':1,'sources':{},'events':{}}
    def observe(self,v):
        state=self.data['sources'].setdefault(v['url'],{'versions':[],'checks':[],'prunedVersions':0})
        old=state['versions'][-1] if state['versions'] else None
        # Raw markup and parsed schedule versions have separate identities.
        raw_changed=not old or old.get('rawSha256')!=v.get('rawSha256')
        semantic_changed=not old or old['semanticHash']!=v['semanticHash'] or old['revision']!=v['revision']
        diff=changes(old,v) if semantic_changed else []
        if raw_changed or semantic_changed:
            state['versions'].append(copy.deepcopy(v))
            if len(state['versions'])>self.limit:
                state['prunedVersions']+=len(state['versions'])-self.limit
                state['versions']=state['versions'][-self.limit:]
        state['checks'].append({'retrievedAt':v['retrievedAt'],'rawSha256':v.get('rawSha256'),
                                'versionId':v['versionId'],'complete':v['complete'],
                                'rawChanged':raw_changed,'scheduleChanged':semantic_changed,'changes':diff})
        state['checks']=state['checks'][-256:]
        return {'source':v['url'],'previousVersionId':old['versionId'] if old else None,
                'versionId':v['versionId'],'rawChanged':raw_changed,'scheduleChanged':semantic_changed,'changes':diff}
    def resolve(self,event_id,versions):
        prior=self.data['events'].get(event_id,{}).get('selected')
        updates=[self.observe(v) for v in versions]
        decision=choose(versions,prior)
        decision['retainedPrevious']=bool(prior and decision['selected'] and prior['versionId']==decision['selected']['versionId'])
        decision['stale']=bool(decision['retainedPrevious'] and not any(v['versionId']==prior['versionId'] and v['complete'] for v in versions))
        if decision['stale'] and decision['status']=='resolved':
            decision['status']='retained-fallback'
            decision['reason']='no-fresh-complete-authoritative-source; previous-local-snapshot-retained'
        decision['sourceChanges']=updates
        decision['selectedChanges']=changes(prior,decision['selected']) if decision['status']=='resolved' and decision['selected'] else []
        self.data['events'][event_id]={'selected':copy.deepcopy(decision['selected']),'status':decision['status'],'reason':decision['reason']}
        return decision
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.data,ensure_ascii=False,separators=(',',':'))+'\n');temp.replace(self.path)
