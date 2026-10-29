"""Generate clearly synthetic authority examples, never historical proof."""
import copy
import html
import json
from pathlib import Path
from isu_pilot.pdf import timetable
from isu_pilot.programme import programme,pdf_revision
from isu_pilot.revisions import version,choose,changes
from isu_pilot.pipeline import build,retime_previous

ROOT=Path(__file__).resolve().parents[1]
event=json.loads((ROOT/'config/events.json').read_text())[0]
aliases=json.loads((ROOT/'config/athletes.json').read_text())
reference=json.loads((ROOT/'config/site-reference.json').read_text())['events'][0]
meta=json.loads((ROOT/'fixtures/real/manifest.json').read_text())
text=(ROOT/'fixtures/real/vancouver-protocol-extract.txt').read_text()
rows,errors=timetable(text,event,meta['protocolUrl'])
pdf=version(event,'pdf',meta['protocolUrl'],rows,{'sha256':meta['protocolSha256'],'fetchedAt':'2026-10-29T12:00:00Z'},pdf_revision(text,event),errors)
newrows=copy.deepcopy(rows)
for row in newrows:
 for old in reference['athleteFirstStarts']:
  if row.get('gender')=='men' and row.get('distance')==old['distance'] and row.get('round')==old['round'] and row['date']==event['startDate']:
   row['startsAt']=old['startsAt'];row['localTime']=old['startsAt'][11:16]
labels={v:k for k,v in __import__('isu_pilot.pdf',fromlist=['ROUNDS']).ROUNDS.items()}
page='<section data-isu-programme><p>SYNTHETIC TEST DATA. Revision date is invented for testing, not archived Vancouver evidence.</p><p>Programme revised: 2026-10-23</p><table data-complete="true"><tr><th>Date</th><th>Time</th><th>Event</th><th>Round</th></tr>'
for row in newrows:
 if row['kind']!='race':continue
 name='Mixed Team Relay' if row['gender']=='mixed' else row['gender'].title()+' '+str(row['distance'])+' m'+(' Relay' if row['discipline']=='relay' else '')
 page+='<tr>'+''.join('<td>'+html.escape(str(value))+'</td>' for value in [row['date'],row['localTime'],name,labels[row['round']]])+'</tr>'
page+='</table></section>'
(ROOT/'fixtures/synthetic/revised-programme.html').write_text(page)
parsed,rev,issues=programme(page,event,event['infoUrl']+'?tab=schedule_16230',True)
comparison_pdf=copy.deepcopy(pdf);comparison_pdf['rows']=[r for r in rows if r.get('kind')=='race']
online=version(event,'online',event['infoUrl']+'?tab=schedule_16230',parsed,{'sha256':'synthetic-online','fetchedAt':'2026-10-28T12:00:00Z'},rev,issues)
decision=choose([comparison_pdf,online])
# Demonstrate a PDF explicitly revised the next day superseding that programme.
revised_pdf=copy.deepcopy(comparison_pdf);revised_pdf['revision']={**revised_pdf['revision'],'number':'2.0','revisedAt':'2026-10-24'}
revised_pdf['versionId']='synthetic-revised-pdf-v2'
reverse=choose([online,revised_pdf])
result={'fixtureType':'SYNTHETIC - NOT HISTORICAL EVIDENCE','onlineSupersedesPdf':{'status':decision['status'],'selectedKind':decision['selected']['kind'],'reason':decision['reason'],'changes':changes(comparison_pdf,online)},
        'pdfSupersedesOnline':{'status':reverse['status'],'selectedKind':reverse['selected']['kind'],'reason':reverse['reason']}}
(ROOT/'examples/synthetic-revision-demo.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='fixtureType'},ensure_ascii=False,indent=2))
