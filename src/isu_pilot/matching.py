import re
import unicodedata
from datetime import datetime
from .timezones import display


def name_key(name):
    plain=''.join(c for c in unicodedata.normalize('NFKD',name) if not unicodedata.combining(c))
    return tuple(sorted(re.findall(r'[a-z]+',plain.casefold())))


def match_athletes(schedule,participants,aliases,event):
    known={}
    for raw,display_name in aliases.items():
        k=name_key(raw)
        if k in known and known[k]!=display_name: raise ValueError('Athlete alias collision')
        known[k]=display_name
    matched=[];issues=[]
    for p in participants:
        if p.get('nation')!='LAT' or p.get('status')=='DNS':continue
        athlete=known.get(name_key(p['name']))
        if not athlete:
            issues.append({'code':'unmatched-lat-athlete','name':p['name']});continue
        candidates=[r for r in schedule if r['kind']=='race' and r.get('discipline')=='individual' and not r.get('cancelled') and
                    all(r.get(k)==p.get(k) for k in ('date','gender','distance','round','occurrence'))]
        if len(candidates)!=1:
            issues.append({'code':'ambiguous-or-missing-round','athlete':athlete,'distance':p['distance'],'round':p['round'],'date':p['date']});continue
        r=candidates[0]
        matched.append({'athlete':athlete,'gender':p['gender'],'distance':p['distance'],'occurrence':p['occurrence'],'round':p['round'],
                        'startsAt':r['startsAt'],'confirmed':p['evidenceKind']=='start-list','timeBasis':'round-start',
                        'firstRoundProof':bool(p.get('openingDayCoverageComplete') or p.get('directEntryConfirmed')),'heatStartsAt':p.get('heatStartsAt'),'sourceUrl':p['sourceUrl'],'scheduleSourceUrl':r['sourceUrl'],
                        'sourcePage':p.get('sourcePage'),'evidenceKind':p['evidenceKind'],
                        'latvianTime':{'lv':display(r['startsAt']),'en':display(r['startsAt'],lang='en')}})
    unique={tuple(row[k] for k in ('athlete','distance','occurrence','round','startsAt')):row for row in matched}
    rows=sorted(unique.values(),key=lambda r:(datetime.fromisoformat(r['startsAt']),r['athlete'],r['distance']))
    first={}
    for r in rows:
        if r['startsAt'][:10]!=event['startDate']:continue
        key=(r['athlete'],r['distance'],r['occurrence'])
        first.setdefault(key,r)
    for key,r in list(first.items()):
        if r['confirmed'] and not r['firstRoundProof']:
            first[key]={**r,'confirmed':False}
            issues.append({'code':'opening-day-coverage-unverified','athlete':r['athlete'],'distance':r['distance']})
    later=[r for r in rows if r['startsAt'][:10]>event['startDate']]
    return list(first.values()),later,issues


def compare(reference,schedule,first):
    """Expected values are loaded only here, never used as extractor input."""
    comparisons=[]
    for expected in reference.get('athleteFirstStarts',[]):
        actual=next((r for r in first if r['athlete']==expected['athlete'] and r['distance']==expected['distance']),None)
        comparisons.append({'athlete':expected['athlete'],'distance':expected['distance'],'expected':expected['startsAt'],
                            'actual':actual['startsAt'] if actual else None,'expectedRound':expected['round'],
                            'actualRound':actual['round'] if actual else None,
                            'status':'missing' if not actual else 'match' if expected['startsAt']==actual['startsAt'] and expected['round']==actual['round'] else 'discrepancy',
                            'evidenceKind':actual['evidenceKind'] if actual else None})
    return comparisons
