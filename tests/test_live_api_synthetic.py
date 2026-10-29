"""Synthetic mutations/positive draw states; NOT live-source validation."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs
from isu_pilot.live_api import schedule,rounds,draw,collect_live,BASE
from isu_pilot.synthetic import SyntheticClient as SyntheticFixtureClient,api_case,encode
from isu_pilot.sources import Client,official
from isu_pilot.matching import match_athletes

ROOT=Path(__file__).resolve().parents[1]
EVENT=json.loads((ROOT/'config/events.json').read_text())[0]



def load(name):return api_case(name)
def encoded(x):return json.dumps(x).encode()
def row():return next(r for r in schedule(encode(api_case('vancouver-schedule.json')),EVENT,BASE,True)[0] if r['eventResultRoundId']==22870)
def synthetic_draw():
    raw=load('vancouver-draw-22870.json')
    for heat in raw['data']:
        heat['status']='Scheduled';heat['result_status']=''
        for c in heat['event_result_round_heats_competitors']:
            c['final_rank']=None;c['final_rank_index']=None;c['final_result']=None;c['qualification_code']='';c['final_points']=0;c['record_flag']='';c['lap']=[]
    meta=load('vancouver-rounds-15939.json')['data'][0]
    meta['status']='Scheduled'
    return raw,meta


class SyntheticApiTests(unittest.TestCase):
    def test_explicit_draw_can_confirm_participation_but_needs_earlier_coverage(self):
        raw,meta=synthetic_draw();people,coverage=draw(encoded(raw),row(),meta,BASE,EVENT)
        self.assertTrue(coverage['preRace'])
        self.assertTrue(all(p['evidenceKind']=='start-list' for p in people))
        aliases=json.loads((ROOT/'config/athletes.json').read_text())
        first,_,_=match_athletes([row()],people,aliases,EVENT)
        self.assertFalse(first[0]['confirmed'])
        people[0]['openingDayCoverageComplete']=True
        first,_,_=match_athletes([row()],people,aliases,EVENT)
        self.assertTrue(first[0]['confirmed'])
    def test_seeded_first_round_requires_both_preliminaries_and_heats(self):
        class SyntheticClient(SyntheticFixtureClient):
            missing_prelim=False
            def get(self,url):
                body,record=super().get(url)
                if body is None:return body,record
                if 'get-event-result-round?' in url and url.endswith('=15939'):
                    value=json.loads(body)
                    programme_rows=schedule(encode(api_case('vancouver-schedule.json')),EVENT,BASE,True)[0]
                    for item in value['data']:
                        item['status']='Scheduled'
                        item['date']=next(r['apiUtcStart'] for r in programme_rows if r['eventResultRoundId']==item['event_result_round_id'])
                    return encoded(value),record
                if 'get-event-result-round-heats-stk-single?' in url and any(url.endswith('='+str(rid)) for rid in (22870,22872)):
                    if self.missing_prelim and url.endswith('=22870'):
                        return None,{'url':url,'status':'unavailable'}
                    value=json.loads(body)
                    for heat in value['data']:
                        heat['status']='Scheduled';heat['result_status']=''
                        for c in heat['event_result_round_heats_competitors']:
                            for k in ('final_rank','final_rank_index','final_result','final_points','qualification_code','record_flag','lap'):c[k]=None
                    return encoded(value),record
                return body,record
        aliases=json.loads((ROOT/'config/athletes.json').read_text())
        for missing,confirmed in [(False,True),(True,False)]:
            c=SyntheticClient(ROOT);c.missing_prelim=missing
            rows,people,_=collect_live(EVENT,c,True,16230)
            first,_,_=match_athletes(rows,people,aliases,EVENT)
            roberts=next(p for p in first if p['athlete']=='Roberts Krūzbergs' and p['distance']==500)
            self.assertEqual(roberts['round'],'heats')
            self.assertEqual(roberts['confirmed'],confirmed)
    def test_profile_nationality_does_not_override_event_federation(self):
        raw,meta=synthetic_draw()
        for h in raw['data']:
            for c in h['event_result_round_heats_competitors']:
                c['started_for_nf_code']='NED';c['skaters']['nationality_code']='LAT'
        self.assertEqual(draw(encoded(raw),row(),meta,BASE,EVENT)[0],[])
    def test_unknown_draw_status_fails_closed(self):
        raw,meta=synthetic_draw();raw['data'][0]['status']='Ready'
        with self.assertRaisesRegex(ValueError,'Unvalidated'):draw(encoded(raw),row(),meta,BASE,EVENT)
    def test_result_fields_in_scheduled_draw_rejected(self):
        raw,meta=synthetic_draw();raw['data'][0]['event_result_round_heats_competitors'][0]['final_rank']=1
        with self.assertRaisesRegex(ValueError,'Result fields'):draw(encoded(raw),row(),meta,BASE,EVENT)
    def test_cross_event_metadata_rejected(self):
        raw=load('vancouver-rounds-15939.json');raw['data'][0]['event_id']=16272
        with self.assertRaisesRegex(ValueError,'another event'):rounds(encoded(raw),EVENT,16230,15939,[row()])
    def test_truncated_schedule_disagrees_with_metadata(self):
        rows=schedule(encode(api_case('vancouver-schedule.json')),EVENT,BASE,True)[0]
        rows=[r for r in rows if r['eventResultRoundId']!=22870]
        with self.assertRaises(ValueError):rounds(encode(api_case('vancouver-rounds-15939.json')),EVENT,16230,15939,rows)
    def test_partial_draw_with_heat_gap_rejected(self):
        raw,meta=synthetic_draw();del raw['data'][1]
        with self.assertRaisesRegex(ValueError,'Non-contiguous'):draw(encoded(raw),row(),meta,BASE,EVENT)
    def test_wrong_round_draw_rejected(self):
        raw,meta=synthetic_draw();raw['data'][0]['event_result_round_id']=1
        with self.assertRaisesRegex(ValueError,'another result'):draw(encoded(raw),row(),meta,BASE,EVENT)
    def test_duplicate_competitor_rejected(self):
        raw,meta=synthetic_draw();raw['data'][1]['event_result_round_heats_competitors'][0]=copy.deepcopy(raw['data'][0]['event_result_round_heats_competitors'][0])
        with self.assertRaises(ValueError):draw(encoded(raw),row(),meta,BASE,EVENT)
    def test_naive_or_out_of_event_timestamp_rejected(self):
        for stamp in ['2026-10-23T16:00:00','2026-11-23T16:00:00Z']:
            raw=load('vancouver-schedule.json');raw['data']['value'][0]['start_time']=stamp
            self.assertTrue(schedule(encoded(raw),EVENT,BASE,True)[1])
    def test_duplicate_round_and_repeated_occurrence_need_review(self):
        raw=load('vancouver-schedule.json');raw['data']['value'].append(copy.deepcopy(raw['data']['value'][0]))
        self.assertTrue(schedule(encoded(raw),EVENT,BASE,True)[1])
        raw['data']['value'][-1]['event_result_round_id']=999999
        self.assertTrue(schedule(encoded(raw),EVENT,BASE,True)[1])
    def test_pagination_envelope_needs_review(self):
        raw=load('vancouver-schedule.json');raw['pagination']={'has_more':True}
        self.assertTrue(schedule(encoded(raw),EVENT,BASE,True)[1])
    def test_same_distance_different_result_ids_needs_occurrence_mapping(self):
        raw=load('vancouver-schedule.json')
        for item in raw['data']['value']:
            if item['event_schedule_title']=='Men 500 m' and item['round_information']=='Finals':item['event_result_id']=999999
        self.assertIn('live-api-repeated-distance-occurrence-unverified',schedule(encoded(raw),EVENT,BASE,True)[1])
    def test_identity_required(self):
        self.assertEqual(schedule(encode(api_case('vancouver-schedule.json')),EVENT,BASE,False)[0],[])


class QueryTransportTests(unittest.TestCase):
    def test_post_bodies_have_distinct_cache_history_and_raw_evidence(self):
        requests=[]
        class Response(io.BytesIO):
            status=200;url=BASE+'/events/get-event-result-round';headers={'Content-Type':'application/json'}
        def transport(req,**kwargs):
            requests.append(req)
            return Response(b'{"status":200,"data":[]}')
        with tempfile.TemporaryDirectory() as td:
            client=Client(td,transport=transport)
            for value in (15939,15940,15939):client.query('/events/get-event-result-round',{'event_result_id':value})
            self.assertEqual(len(requests),2);self.assertEqual(len(client.records),2)
            self.assertEqual(requests[0].get_method(),'POST')
            self.assertEqual(parse_qs(requests[0].data.decode()),{'event_result_id':['15939']})
            records=list(client.records.values())
            self.assertNotEqual(records[0]['url'],records[1]['url'])
            self.assertEqual(records[0]['requestBody'],'event_result_id=15939')
            self.assertEqual(len(json.loads((Path(td)/'source-history.json').read_text())),2)
    def test_no_arbitrary_post_or_filtered_completeness(self):
        with tempfile.TemporaryDirectory() as td:
            c=Client(td)
            for path,fields in [('/events/delete',{}),('/events/get-event-result-round',{'event_result_id':'../1'}),('/events/get-event-result-round-heats-stk-single',{'event_result_id':1,'event_result_round_id':2,'country_code':'LAT'})]:
                with self.assertRaises(ValueError):c.query(path,fields)
    def test_bounded_parallel_queries_retain_all_history(self):
        class Response(io.BytesIO):
            status=200;url=BASE+'/events/get-event-result-round';headers={'Content-Type':'application/json'}
        with tempfile.TemporaryDirectory() as td:
            c=Client(td,transport=lambda *a,**k:Response(b'{"status":200,"data":[]}'))
            responses=c.query_many([('/events/get-event-result-round',{'event_result_id':i}) for i in range(1,16)])
            self.assertEqual(len(responses),15)
            self.assertEqual(len(json.loads((Path(td)/'source-history.json').read_text())),15)
    def test_exact_official_api_host_only(self):
        self.assertEqual(official(BASE),BASE)
        with self.assertRaises(ValueError):official(BASE+'.evil.test')
