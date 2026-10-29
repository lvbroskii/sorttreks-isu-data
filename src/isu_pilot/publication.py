"""Independent publication stages. Tab visibility never verifies race times."""
from datetime import datetime
from .timezones import display

TRACKED_ATHLETES=('Roberts Krūzbergs','Reinis Bērziņš')


def assess(event,page,api,first=None,later=None,sessions=None):
    identity=page.get('identityVerified',False)
    visible=identity and bool(page.get('tabs',{}).get('schedule')) and page.get('tabStates',{}).get('schedule') is not False
    accepted=[]
    for session in sessions or []:
        # Explicit normalized session evidence only; never infer sessions from rounds.
        try:
            stamp=datetime.fromisoformat(session['startsAt'])
            if (session.get('verificationStatus')!='verified' or session.get('timeBasis')!='session-start'
                or not session.get('sourceUrl') or not session.get('title') or stamp.tzinfo is None
                or not event['startDate']<=session['startsAt'][:10]<=event['endDate'] or not identity):continue
            accepted.append({**session,'latvianTime':{'lv':display(session['startsAt']),'en':display(session['startsAt'],lang='en')}})
        except (ValueError,KeyError,TypeError):continue
    availability=api.get('availability')
    if identity and api.get('programmeComplete'):
        round_status='published'
    elif identity and api.get('scheduleRows',0):
        round_status='partial-or-unverified'
    elif availability=='unpublished' and identity:
        round_status='unpublished'
    else:round_status='not-verified'
    people=api.get('participants',[])
    athletes={}
    for name in TRACKED_ATHLETES:
        starts=[r for r in first or [] if r['athlete']==name and r.get('confirmed')
                and api.get('programmeComplete') and api.get('preRaceStartListsVerified')
                and any(p.get('matchedAthlete')==name and p.get('evidenceKind')=='start-list'
                        and p.get('openingDayCoverageComplete')
                        and all(p.get(k)==r.get(k) for k in ('gender','distance','round','occurrence'))
                        and p.get('date')==r['startsAt'][:10] for p in people)]
        observations=[p for p in people if p.get('matchedAthlete')==name]
        # Canonical names come from the existing exact alias matcher, never fuzzy profiles.
        if starts:status='confirmed-first-rounds'
        elif any(p.get('evidenceKind')=='start-list' for p in observations):status='assignments-first-round-unverified'
        elif observations:status='retrospective-only'
        else:status='not-verified'
        later_starts=[r for r in later or [] if r['athlete']==name and r.get('confirmed')
                      and api.get('programmeComplete') and any(p.get('matchedAthlete')==name
                          and p.get('evidenceKind')=='start-list' and p.get('date')==r['startsAt'][:10]
                          and all(p.get(k)==r.get(k) for k in ('gender','distance','round','occurrence')) for p in people)]
        athletes[name]={'status':status,'firstStarts':starts,'laterStarts':later_starts}
    return {'eventId':event['id'],'stages':{
                'scheduleTab':{'status':'visible' if visible else 'not-observed' if identity else 'not-verified'},
                'sessions':{'status':'published' if accepted else 'not-verified','rows':accepted},
                'roundTimes':{'status':round_status,'rowCount':api.get('scheduleRows',0)},
                'athleteDraws':athletes},
            'drawDiscovery':api.get('drawDiscovery',{'status':'queried-from-programme-identifiers'}),
            'retainVerifiedFallback':True,'approvedForWebsite':False,
            'notes':['Session starts/end times are not inferred from the first/last race round.',
                     'Unverified draws do not mean an athlete is absent or withdrawn.']}


def changes(previous,current):
    if previous and previous['eventId']!=current['eventId']:
        raise ValueError('Cannot compare publication stages across events')
    before=(previous or {}).get('stages',{})
    return [{'stage':name,'previous':before.get(name),'current':value}
            for name,value in current['stages'].items() if before.get(name)!=value]


def check(event,client,aliases,previous=None):
    """Focused one-off publication check; no PDF search, polling or publication."""
    from .html import discover,Page,flight_objects,walk
    from .live_api import collect_live
    from .pipeline import build_rows
    from .matching import name_key
    raw,record=client.get(event['infoUrl'])
    page=discover(raw.decode('utf-8',errors='replace'),event['infoUrl'],event) if raw else {'identityVerified':False,'tabs':{}}
    pages=[record];result_objects=[]
    for kind in ('schedule','result'):
        url=page['tabs'].get(kind)
        if not url:continue
        body,source=client.get(url);pages.append(source)
        if body is not None:
            parsed=discover(body.decode('utf-8',errors='replace'),url,event)
            if kind=='schedule' and parsed['identityVerified']:page=parsed
            if kind=='result':
                result_objects=[o for value in flight_objects(Page(body.decode('utf-8',errors='replace'))) for o in walk(value)]
    ids={int(m['id']) for m in page.get('metadata',[]) if str(m.get('id','')).isdigit()}
    cms_id=next(iter(ids)) if page.get('identityVerified') and len(ids)==1 else None
    rows,people,api=collect_live(event,client,page.get('identityVerified'),cms_id)
    alias_map={name_key(raw):name for raw,name in aliases.items()}
    for person in people:person['matchedAthlete']=alias_map.get(name_key(person['name']))
    report=build_rows(event,rows,people,aliases,issues=api['issues'])
    # A read-only check reports candidates without emitting a website patch.
    report['calendarPatchCandidate']=None
    report['liveApi']=api
    report['publication']=assess(event,page,api,report['athleteFirstStarts'],report['athleteRoundStarts'])
    report['publicationChanges']=changes(previous,report['publication'])
    report['pageEvidence']=pages
    report['resultsPageIdentifierObservation']={
        'eventResultIds':sorted({o['event_result_id'] for o in result_objects if type(o.get('event_result_id')) is int}),
        'eventResultRoundIds':sorted({o['event_result_round_id'] for o in result_objects if type(o.get('event_result_round_id')) is int}),
        'note':'Observed identifiers only; never used without matching event identity and programme metadata.'}
    report['fallback']='existing-verified-data-retained; no website writes'
    return report
