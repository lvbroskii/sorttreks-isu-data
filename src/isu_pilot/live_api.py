"""Public ISU programme/results API. No credentials, browser execution or writes.

Routes are taken from ISU's shipped programme/results components. Source snapshots
are observations; generic import timestamps are NOT schedule revision authority.
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit,parse_qs
from .pdf import ROUNDS

BASE = 'https://front-api.isu.org'
ROUND_PATH = '/events/get-event-result-round'
DRAW_PATH = '/events/get-event-result-round-heats-stk-single'
MAX_ROUNDS = 80


def payload(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('status') != 200:
        raise ValueError('API did not return status 200')
    for container in (value, value.get('data')):
        if isinstance(container,dict) and any(k in container for k in ('pagination','next','next_page','has_more','hasMore','page','total_pages')):
            raise ValueError('Unvalidated API pagination envelope')
    return value['data']


def positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Invalid API identifier')
    return value


def instant(value, event):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('API timestamp has no offset')
    local = dt.astimezone(ZoneInfo(event['timeZone']))
    if not event['startDate'] <= local.date().isoformat() <= event['endDate']:
        raise ValueError('API timestamp outside event venue dates')
    return local.isoformat()


def schedule(raw, event, url, identity_verified):
    rows = []; issues = []
    if not identity_verified:
        return [], ['live-api-event-identity-unverified']
    try:
        data = payload(raw)
        if data['discipline']['discipline_id'] != 3 or not isinstance(data['value'], list):
            raise ValueError('Not a short-track schedule')
        if not data['value']:
            return [], ['live-api-programme-unpublished']
        if len(data['value']) > MAX_ROUNDS:
            raise ValueError('API schedule exceeds round budget')
        ids = set(); keys = set()
        for item in data['value']:
            result_id = positive(item['event_result_id'])
            round_id = positive(item['event_result_round_id'])
            if round_id in ids: raise ValueError('Duplicate API round ID')
            ids.add(round_id)
            title = item['event_schedule_title']
            race = re.fullmatch(r'(Men|Women) (500|1000|1500|3000|5000) m( Relay)?', title)
            if title == 'Mixed Team Relay': sex, distance, relay = 'mixed', 2000, True
            elif race: sex, distance, relay = race[1].lower(), int(race[2]), bool(race[3])
            else: raise ValueError('Unsupported API event title: '+str(title))
            rd = ROUNDS.get(item['round_information'])
            if not rd: raise ValueError('Unsupported API round: '+str(item['round_information']))
            start = instant(item['start_time'], event)
            key = (start[:10], sex, distance, relay, rd)
            # Repeated junior distances cannot silently collapse to occurrence 1.
            if key in keys: raise ValueError('Repeated API distance/round requires an explicit occurrence mapping')
            keys.add(key)
            rows.append({'kind':'race', 'date':start[:10], 'startsAt':start,
                         'localTime':start[11:16], 'gender':sex, 'distance':distance,
                         'discipline':'relay' if relay else 'individual', 'round':rd,
                         'occurrence':1, 'cancelled':False, 'heatCount':None,
                         'sourceUrl':url, 'sourceText':title+' | '+item['round_information'],
                         'timeBasis':'round-start', 'eventResultId':result_id,
                         'eventResultRoundId':round_id, 'apiUtcStart':item['start_time']})
        groups = {}
        for row in rows:
            groups.setdefault((row['gender'],row['distance'],row['discipline']),set()).add(row['eventResultId'])
        if any(len(ids)>1 for ids in groups.values()):
            issues.append('live-api-repeated-distance-occurrence-unverified')
        if not {event['startDate'], event['endDate']} <= {r['date'] for r in rows}:
            issues.append('live-api-programme-date-coverage-incomplete')
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        issues.append('live-api-schedule-invalid: '+str(err))
    return sorted(rows, key=lambda r:datetime.fromisoformat(r['startsAt'])), issues


def rounds(raw, event, cms_id, result_id, schedule_rows):
    data = payload(raw)
    if not isinstance(data, list) or not data:
        raise ValueError('Round metadata unpublished')
    seen = set()
    for item in data:
        rid = positive(item['event_result_round_id'])
        if rid in seen: raise ValueError('Duplicate metadata round ID')
        seen.add(rid)
        if item['event_id'] != cms_id or item['event_result_id'] != result_id:
            raise ValueError('Round metadata belongs to another event/result')
        instant(item['date'], event)
        matched = [r for r in schedule_rows if r['eventResultRoundId'] == rid]
        if len(matched) != 1 or matched[0]['eventResultId'] != result_id or ROUNDS.get(item['name']) != matched[0]['round']:
            raise ValueError('Metadata round not mapped to programme')
        if item['status'] != 'Finished' and instant(item['date'],event) != matched[0]['startsAt']:
            raise ValueError('Unfinished round time conflicts with programme')
    expected = {r['eventResultRoundId'] for r in schedule_rows if r['eventResultId'] == result_id}
    if seen != expected:
        raise ValueError('Programme/metadata round coverage differs')
    return data


def draw(raw, row, metadata, url, event):
    """All-country heat assignments, never generic entries/qualification lists.

    Only explicit pre-race draw states can confirm future participation. Unknown
    states fail closed; Finished captures validate retrospective matching only.
    """
    data = payload(raw)
    if not isinstance(data, list) or not data:
        raise ValueError('Heat draw unpublished')
    people = []; heat_ids = set(); athletes = set(); orders = set(); pre_race = True
    for heat in data:
        hid = positive(heat['event_result_round_heats_id'])
        if hid in heat_ids or heat['display_order'] in orders:
            raise ValueError('Duplicate heat identity/order')
        heat_ids.add(hid); orders.add(heat['display_order'])
        if heat['event_result_id'] != row['eventResultId'] or heat['event_result_round_id'] != row['eventResultRoundId']:
            raise ValueError('Heat belongs to another result/round')
        heat_time = instant(heat['date'], event) if heat.get('date') else None
        if heat_time and heat_time[:10] != row['date']:
            raise ValueError('Heat date differs from programme round')
        competitors = heat['event_result_round_heats_competitors']
        if not isinstance(competitors, list) or not competitors:
            raise ValueError('Incomplete/empty heat assignment')
        retrospective = heat.get('status') == 'Finished' or metadata.get('status') == 'Finished'
        explicit_draw = heat.get('status') in ('Scheduled', 'Start List') and metadata.get('status') in ('Scheduled', 'Start List')
        if not retrospective and not explicit_draw:
            raise ValueError('Unvalidated pre-race heat/round state')
        pre_race &= explicit_draw and not retrospective
        positions = set()
        for c in competitors:
            athlete_id = positive(c['skaters_id'])
            if c['event_result_round_heats_id'] != hid or c['skaters']['id'] != athlete_id:
                raise ValueError('Competitor identity/heat mismatch')
            if athlete_id in athletes: raise ValueError('Athlete assigned to multiple heats')
            athletes.add(athlete_id)
            lane = c.get('starting_position')
            # Finished result records can contain penalties/zero lanes; never use those as draws.
            if explicit_draw and not retrospective:
                if type(lane) is not int or lane <= 0 or lane in positions:
                    raise ValueError('Invalid starting positions')
                if any(c.get(k) for k in ('final_rank','final_rank_index','final_result','final_points','qualification_code','record_flag','lap')):
                    raise ValueError('Result fields present in purported start list')
            positions.add(lane)
            nation = c.get('started_for_nf_code')
            if not isinstance(nation,str) or not re.fullmatch('[A-Z]{3}',nation):
                raise ValueError('Missing event-specific federation')
            if nation != 'LAT': continue
            name = c['skaters'].get('full_name')
            if not name: raise ValueError('LAT athlete name missing')
            people.append({'name':name, 'nation':nation, 'gender':row['gender'],
                           'distance':row['distance'], 'round':row['round'], 'date':row['date'],
                           'occurrence':row['occurrence'], 'sourceUrl':url,
                           'evidenceKind':'historical-result' if retrospective else 'start-list',
                           'status':c.get('result_status',''), 'openingDayCoverageComplete':False,
                           'athleteId':athlete_id, 'heatId':hid, 'heatName':heat['name'],
                           'heatStartsAt':heat_time, 'startingPosition':lane,
                           'sourceRoundId':row['eventResultRoundId']})
    if orders != set(range(1,len(data)+1)):
        raise ValueError('Non-contiguous heat sequence')
    return people, {'complete':True, 'preRace':bool(pre_race), 'heatCount':len(data),
                    'competitorCount':len(athletes), 'roundId':row['eventResultRoundId']}


def queries(client, requests):
    if hasattr(client, "query_many"):
        return client.query_many(requests)
    return [client.query(*request) for request in requests]


def discover_draw_ids(event,client,cms_id,result_tab=None):
    """Independent public inventory probe; empty programme does not prove no draws.

    Never increment IDs or borrow another competition's identifiers. The current
    real Montreal inventory response is unavailable; an unseen populated schema
    requires validation before it can supply a confirmed starting round.
    """
    slug=event['infoUrl'].rstrip('/').split('/')[-1]
    urls=[BASE+'/events/get-event-result/'+slug]
    if result_tab and result_tab.split('?')[0]==event['infoUrl']:
        child=parse_qs(urlsplit(result_tab).query).get('tab',[''])[0]
        if re.fullmatch(r'results_[0-9]+',child) and child=='results_'+str(cms_id):
            urls.append(BASE+'/events/get-event-result/'+child)
    attempts=[];body=None;source={}
    for url in urls:
        candidate,record=client.get(url);attempts.append(record)
        if candidate is not None:
            body,source=candidate,record;break
        source=attempts[0]
    result={'source':source,'attempts':attempts,'resultIds':[],'status':'identifiers-unavailable',
            'confirmedFirstStarts':False}
    if body is None:
        result['reason']='Public result inventory unavailable; heat queries cannot be made without verified event-specific result/round IDs.'
        return result
    try:
        data=payload(body)
        if not isinstance(data,list):raise ValueError('Unsupported result inventory schema')
        if not data:
            result['status']='inventory-empty'
            result['reason']='Empty event result inventory; this does not establish that athletes are absent.'
            return result
        ids=[]
        for item in data:
            if item.get('event_id')!=cms_id:raise ValueError('Inventory event identity unverified')
            ids.append(positive(item['event_result_id']))
        if len(set(ids))!=len(ids):raise ValueError('Duplicate inventory result ID')
        if len(ids)>20:raise ValueError('Inventory exceeds result-group budget')
        result.update(status='inventory-published-needs-validation',resultIds=ids,
                      reason='Identifiers can be probed, but no first round is confirmed without a validated programme and draw.')
        candidates=[]
        for result_id,(round_body,round_source) in zip(ids,queries(client,[(ROUND_PATH,{'event_result_id':i}) for i in ids])):
            attempts.append(round_source)
            if round_body is None:continue
            items=payload(round_body)
            if not isinstance(items,list):raise ValueError('Unsupported inventory round metadata')
            for item in items:
                if item.get('event_id')!=cms_id or item.get('event_result_id')!=result_id:
                    raise ValueError('Independent round probe belongs to another event/result')
                rid=positive(item['event_result_round_id'])
                if item.get('date'):instant(item['date'],event)
                candidates.append({'eventResultId':result_id,'eventResultRoundId':rid,'name':item.get('name'),'sourceUrl':round_source['url']})
        if len(candidates)>MAX_ROUNDS or len({c['eventResultRoundId'] for c in candidates})!=len(candidates):
            raise ValueError('Duplicate/excessive discovered round identifiers')
        result['roundCandidates']=candidates
        result['heatProbes']=[]
        # Archive actual responses for review; do not manufacture distance/time mappings.
        requests=[(DRAW_PATH,{'event_result_id':c['eventResultId'],'event_result_round_id':c['eventResultRoundId'],'country_code':''}) for c in candidates]
        for candidate,(heat_body,heat_source) in zip(candidates,queries(client,requests)):
            attempts.append(heat_source)
            probe={**candidate,'source':heat_source,'status':'unavailable','confirmedFirstStarts':False}
            if heat_body is not None:
                heats=payload(heat_body)
                if not isinstance(heats,list):raise ValueError('Unsupported heat probe schema')
                if any(h.get('event_result_id')!=candidate['eventResultId'] or h.get('event_result_round_id')!=candidate['eventResultRoundId'] for h in heats):
                    raise ValueError('Independent heat probe belongs to another result/round')
                probe.update(status='unvalidated-records' if heats else 'empty',heatCount=len(heats))
            result['heatProbes'].append(probe)
    except (ValueError,KeyError,TypeError) as err:
        result.update(status='inventory-needs-review',reason=str(err))
    return result


def collect_live(event, client, identity_verified, cms_id, result_tab=None):
    slug = event['infoUrl'].rstrip('/').split('/')[-1]
    url = BASE+'/events/getschedule/'+slug
    raw, rec = client.get(url)
    rec.setdefault('url',url)
    rows, issues = schedule(raw,event,url,identity_verified) if raw is not None else ([],['live-api-programme-unavailable'])
    observations = []; participants = []; coverage = {}; metadata = {}
    evidence = {'programmeSource':rec, 'scheduleRows':len(rows), 'issues':issues,
                'availability':'unpublished' if 'live-api-programme-unpublished' in issues else 'available' if rows and not issues else 'needs-review',
                'rounds':observations, 'completenessScope':'Structural coverage of returned programme groups and unpaginated heat arrays; no independent total-group or total-heat count is provided.', 'revisionEvidence':'No schedule-specific revision marker in API; retrieval/import timestamps do not establish supersession.'}
    if issues or not cms_id:
        if not cms_id: issues.append('live-api-cms-event-id-unverified')
        evidence['drawDiscovery']=discover_draw_ids(event,client,cms_id,result_tab)
        return rows, participants, evidence
    result_ids = sorted({r['eventResultId'] for r in rows})
    requests = [(ROUND_PATH, {'event_result_id':rid}) for rid in result_ids]
    responses = queries(client, requests)
    for result_id, (body, source) in zip(result_ids, responses):
        try:
            if body is None: raise ValueError('Round metadata unavailable')
            items = rounds(body,event,cms_id,result_id,rows)
            for item in items: metadata[item['event_result_round_id']] = item
            observations.append({'kind':'round-metadata', 'source':source, 'roundCount':len(items),
                                 'importTimestamps':[{'roundId':i['event_result_round_id'],'updatedAt':i.get('updated_at'),'status':i.get('status'),'roundTimestamp':i['date'],'programmeTime':next(r['startsAt'] for r in rows if r['eventResultRoundId']==i['event_result_round_id'])} for i in items]})
        except (ValueError,KeyError,TypeError) as err:
            issues.append('live-api-round-metadata: '+str(err))
            observations.append({'kind':'round-metadata','source':source,'error':str(err)})
    draw_rows = [r for r in rows if r['discipline']=='individual' and r['eventResultRoundId'] in metadata]
    requests = [(DRAW_PATH, {'event_result_id':r['eventResultId'], 'event_result_round_id':r['eventResultRoundId'], 'country_code':''}) for r in draw_rows]
    responses = queries(client, requests)
    for row, (body, source) in zip(draw_rows, responses):
        rid = row['eventResultRoundId']
        try:
            if body is None: raise ValueError('Heat source unavailable')
            people, check = draw(body,row,metadata[rid],source['url'],event)
            coverage[rid] = check; participants.extend(people)
            observations.append({'kind':'heat-draw','source':source,**check})
        except (ValueError,KeyError,TypeError) as err:
            observations.append({'kind':'heat-draw','source':source,'roundId':rid,'complete':False,'error':str(err)})
    # Prove all earlier/equal opening-day rounds in this distance have full draws.
    for person in participants:
        earlier = [r for r in rows if r['date']==event['startDate'] and
                   all(r[k]==person[k] for k in ('gender','distance','occurrence')) and
                   r['discipline']=='individual' and datetime.fromisoformat(r['startsAt']) <= next(datetime.fromisoformat(r['startsAt']) for r in rows if r['eventResultRoundId']==person['sourceRoundId'])]
        person['openingDayCoverageComplete'] = bool(earlier) and all(coverage.get(r['eventResultRoundId'],{}).get('preRace') for r in earlier)
    incomplete = [o for o in observations if o.get('complete') is False]
    evidence['programmeComplete'] = not issues and len(metadata)==len(rows)
    evidence['drawCoverageComplete'] = len(coverage)==sum(r['discipline']=='individual' for r in rows) and bool(draw_rows)
    evidence['unpublishedOrIncompleteDraws'] = len(incomplete)
    evidence['participants'] = participants
    evidence['preRaceStartListsVerified'] = any(p['evidenceKind']=='start-list' and p['openingDayCoverageComplete'] for p in participants)
    return rows, participants, evidence
