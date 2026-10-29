"""Hand-authored synthetic contracts. Never official captures or live evidence."""
import copy
import hashlib
from datetime import datetime,timedelta
import json
from pathlib import Path
from urllib.parse import urlencode

KIND='synthetic-not-official'
BASE='https://front-api.isu.org'
# Test-only constants intentionally isolated from production discovery.
GROUPS={15939:(500,[(22870,'Preliminaries','2026-10-23T16:21:00Z'),(22872,'Heats','2026-10-23T20:46:00Z'),(22877,'Finals','2026-10-25T20:00:00Z')]),
        15940:(1000,[(22886,'Preliminaries','2026-10-23T17:00:00Z'),(22888,'Heats','2026-10-23T21:54:00Z'),(22891,'Finals','2026-10-24T20:00:00Z')]),
        15942:(1500,[(22894,'Heats','2026-10-23T18:00:00Z'),(22896,'Quarterfinals','2026-10-23T23:16:00Z'),(22905,'Finals','2026-10-25T21:00:00Z')])}


def encode(value):return json.dumps(value,ensure_ascii=False).encode()


def programme():
    return {'status':200,'message':'SYNTHETIC TEST PROGRAMME - NOT OFFICIAL','data':{'discipline':{'discipline_id':3},'value':[
        {'start_time':stamp,'event_schedule_title':f'Men {distance} m','round_information':name,
         'event_result_id':result,'event_result_round_id':rid,'discipline_type':'Singles'}
        for result,(distance,items) in GROUPS.items() for rid,name,stamp in items]}}


def empty():
    return {'status':200,'message':'SYNTHETIC EMPTY PROGRAMME - NOT OFFICIAL',
            'data':{'discipline':{'discipline_id':3,'title':'SHORT TRACK'},'value':[]}}


def metadata(result):
    return {'status':200,'message':'SYNTHETIC ROUND METADATA','data':[
        {'event_result_id':result,'event_result_round_id':rid,'event_id':16230,'name':name,
         'date':stamp,'status':'Finished','updated_at':'2026-10-29T00:00:00Z'}
        for rid,name,stamp in GROUPS[result][1]]}


def heats(rid):
    result=next(k for k,(_,items) in GROUPS.items() if any(r[0]==rid for r in items))
    stamp=next(r[2] for r in GROUPS[result][1] if r[0]==rid)
    rows=[]
    # Three explicit heats exercise sequence gaps and duplicate assignment checks.
    for order in (1,2,3):
        hid=rid*10+order
        competitor={'event_result_round_heats_id':hid,'skaters_id':hid,'starting_position':1,
                    'started_for_nf_code':'NED','final_rank':1,'final_rank_index':1,
                    'final_result':'42.000','qualification_code':'Q','lap':[],
                    'skaters':{'id':hid,'full_name':'SYNTHETIC Example Athlete','nationality_code':'NED'}}
        if order==1 and rid in (22870,22888,22896):
            competitor.update(skaters_id=111,started_for_nf_code='LAT',skaters={'id':111,'full_name':'Reinis BERZINS','nationality_code':'LAT'})
        if order==2 and rid in (22872,22888,22896):
            competitor.update(skaters_id=222,started_for_nf_code='LAT',skaters={'id':222,'full_name':'Roberts KRUZBERGS','nationality_code':'LAT'})
        rows.append({'event_result_round_heats_id':hid,'event_result_id':result,'event_result_round_id':rid,
                     'display_order':order,'name':f'Heat {order}','date':(datetime.fromisoformat(stamp.replace('Z','+00:00'))+timedelta(minutes=order)).isoformat(),'status':'Finished',
                     'result_status':'Official','event_result_round_heats_competitors':[competitor]})
    return {'status':200,'message':'SYNTHETIC HEAT RECORDS','data':rows}


def event_html(event,index=0):
    cms=[16230,16272,16223,16244][index]
    meta={'id':str(cms),'slug':event['infoUrl'].rstrip('/').split('/')[-1],'season':'2026/2027',
          'from_date':event['startDate']+'T00:00:00Z','to_date':event['endDate']+'T23:59:59Z'}
    tabs=[{'slug':f'{prefix}_{cms}','event_type':kind,'is_active':True,'event_id':cms}
          for kind,prefix in [('schedule','schedule'),('result','results'),('entries','entries'),('documents','documents')]]
    data={'synthetic':True,'event':meta,'tabs':tabs,'document':{'file_url':C08_URL,'label':'Synthetic protocol'}}
    frame='0:'+json.dumps(data)+'\n'
    return '<!doctype html><p>SYNTHETIC TEST PAGE - NOT OFFICIAL</p><p>loading_schedule</p><script>self.__next_f.push('+json.dumps([1,frame])+')</script>'


C08_URL='https://www.isu-skating.com/synthetic-test-only/C08.pdf'
C08='''SYNTHETIC TEST DATA - NOT OFFICIAL; NOT A VANCOUVER CAPTURE
Vancouver
DETAILED TIME SCHEDULE
23 OCT 2026 09:00  Men 500 m Preliminaries (Heats: 3)
            13:39  Men 500 m Heats (Heats: 3)
            14:30  Men 1000 m Heats (Heats: 3)
            15:00  Men 1500 m Quarterfinals (Heats: 3)
            15:30  Lunch Break
            17:00  End of Day
24 OCT 2026 09:00  Men 500 m Quarterfinals (Heats: 3)
            17:00  End of Day
25 OCT 2026 09:00  Men 500 m Finals (Heats: 2)
            17:00  End of Day
STK_TEST_C08 1.0
Print Date: WED 21 OCT 2026 Print Time: 21:32
'''
for distance,rd,names in [(500,'Preliminaries',['BERZINS Reinis']),(500,'Heats',['KRUZBERGS Roberts']),
                          (1000,'Heats',['BERZINS Reinis','KRUZBERGS Roberts']),
                          (1500,'Quarterfinals',['BERZINS Reinis','KRUZBERGS Roberts'])]:
    C08+='\fSYNTHETIC TEST DATA - NOT OFFICIAL\nMen '+str(distance)+' m - '+rd+'\nRESULTS\nFRI 23 OCT 2026\n'
    C08+='\n'.join(name+'  LAT' for name in names)+'\n'


def api_case(name):
    if name=='vancouver-schedule.json':return programme()
    if name.startswith('vancouver-rounds-'):return metadata(int(name.removeprefix('vancouver-rounds-').removesuffix('.json')))
    if name.startswith('vancouver-draw-'):return heats(int(name.removeprefix('vancouver-draw-').removesuffix('.json')))
    if name.endswith('-schedule.json'):return empty()
    raise ValueError('Unknown synthetic fixture '+name)


class SyntheticClient:
    """In-memory offline transport. It never performs HTTP or reads captures."""
    def __init__(self,root):
        self.root=Path(root);self.events=json.loads((self.root/'config/events.json').read_text())
        self.records={};self.calls=[]
    def get(self,url):
        self.calls.append(url);value=None
        for index,event in enumerate(self.events):
            slug=event['infoUrl'].rstrip('/').split('/')[-1]
            if url.split('?')[0]==event['infoUrl']:value=event_html(event,index).encode();break
            if url==BASE+'/events/getschedule/'+slug:value=encode(programme() if index==0 else empty());break
        if url.startswith(BASE+'/events/get-event-result-round?'):
            value=encode(metadata(int(url.rsplit('=',1)[-1])))
        if '/get-event-result-round-heats-stk-single?' in url:
            from urllib.parse import parse_qs,urlsplit
            rid=int(parse_qs(urlsplit(url).query)['event_result_round_id'][0]);value=encode(heats(rid))
        if value is None:return None,{'url':url,'status':'unavailable','error':'Synthetic missing response'}
        record={'url':url,'sha256':hashlib.sha256(value).hexdigest(),'fetchedAt':'2026-10-29T00:00:00Z','status':'fetched','fixtureKind':KIND}
        self.records[url]=record;return value,record
    def query(self,path,fields):return self.get(BASE+path+'?'+urlencode(sorted(fields.items())))


def demo(root):
    from .pipeline import build_rows
    from .live_api import collect_live
    events=json.loads((Path(root)/'config/events.json').read_text());aliases=json.loads((Path(root)/'config/athletes.json').read_text())
    client=SyntheticClient(root);rows,people,evidence=collect_live(events[0],client,True,16230)
    result=build_rows(events[0],rows,people,aliases,issues=evidence['issues'])
    result.update(validationType=KIND,calendarPatchCandidate=None,liveApi=evidence)
    return {'mode':KIND,'events':[result],'approvedForWebsite':False,'warning':'Offline synthetic regression only. No real source validation or live monitoring.'}
