"""Swiss Timing C08 timetable and C73A race-participation adapters."""
import re
import subprocess
from pathlib import Path
from .timezones import local_instant

MONTHS = {m:i+1 for i,m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
ROUNDS = {'Preliminaries':'preliminaries','Heats':'heats','Quarterfinals':'quarterfinals',
          'Semifinals':'semifinals','Finals':'finals', 'Rep. Heats':'repechage-heats',
          'Rep. Quarterfinals':'repechage-quarterfinals','Rep. Semifinals':'repechage-semifinals'}
ROUND_RE = '|'.join(re.escape(s) for s in sorted(ROUNDS,key=len,reverse=True))


def pdf_text(path):
    """No OCR: empty/scanned/unsupported PDFs fail closed."""
    res = subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,timeout=45,check=True)
    if len(res.stdout.strip()) < 100: raise ValueError('PDF has no usable text; manual review required')
    if len(res.stdout) > 4_000_000: raise ValueError('PDF text exceeds cap')
    return res.stdout


def document_identity(text, event):
    # C08 dates alone are insufficient: verify city plus all competition dates/year.
    city = {'2026-27-wt1':'Vancouver','2026-27-wt2':'Montreal','2026-27-jwc1':'Bormio','2026-27-jwc2':'Bormio'}[event['id']]
    pages = [p for p in text.split('\f') if 'DETAILED TIME SCHEDULE' in p]
    dates = set()
    for p in pages:
        for d,m,y in re.findall(r'\b(\d{1,2}) ([A-Z]{3}) (20\d{2})\s+\d{2}:\d{2}',p):
            if m in MONTHS: dates.add(f'{y}-{MONTHS[m]:02d}-{int(d):02d}')
    return bool(pages) and all(city.lower() in p.lower() for p in pages) and event['startDate'] in dates and event['endDate'] in dates


def timetable(text, event, url):
    rows=[]; issues=[]
    if not document_identity(text,event): return [],['document-identity-unverified']
    for page_no,page in enumerate(text.split('\f'),1):
        if 'DETAILED TIME SCHEDULE' not in page: continue
        day=None
        for line in page.splitlines():
            m=re.match(r'^\s*(?:(\d{1,2}) ([A-Z]{3}) (20\d{2})\s+)?(\d{2}:\d{2})\s{2,}(.*?)\s*$',line)
            if not m: continue
            d,mon,year,clock,content=m.groups()
            if d and mon in MONTHS: day=f'{year}-{MONTHS[mon]:02d}-{int(d):02d}'
            if not day: continue
            if not event['startDate'] <= day <= event['endDate']:
                issues.append('schedule-outside-event');continue
            try: instant=local_instant(day,clock,event['timeZone'])
            except ValueError as err: issues.append(str(err));continue
            base={'date':day,'startsAt':instant,'localTime':clock,'sourceUrl':url,'sourcePage':page_no,'sourceText':line.strip(),'timeBasis':'round-start'}
            race=re.match(r'^(Women|Men)\s+(500|1000|1500|3000|5000) m( Relay)?\s+('+ROUND_RE+r')\b(.*)',content)
            mixed=re.match(r'^Mixed Team Relay\s+('+ROUND_RE+r')\b(.*)',content)
            if race:
                sex,dist,relay,rd,info=race.groups()
                base.update(kind='race',gender=sex.lower(),distance=int(dist),discipline='relay' if relay else 'individual',round=ROUNDS[rd],occurrence=1)
            elif mixed:
                rd,info=mixed.groups()
                base.update(kind='race',gender='mixed',distance=2000,discipline='relay',round=ROUNDS[rd],occurrence=1)
            else:
                kind=next((k for label,k in [('Lunch Break','break'),('End of Day','end'),('Ice Resurfacing','resurfacing'),('Short break','short-break')] if content.startswith(label)),None)
                if kind: rows.append({**base,'kind':kind})
                continue
            # Junior formats may have repeated same-distance contests: retain explicit suffix.
            occurrence=re.search(r'\b(?:Race|Distance|Event)\s*#?([12])\b',info,re.I)
            if occurrence: base['occurrence']=int(occurrence[1])
            heats=re.search(r'Heats:\s*(\d+)',info)
            base['heatCount']=int(heats[1]) if heats else None
            base['cancelled']=bool(re.search(r'CANCEL',info,re.I))
            rows.append(base)
    for a,b in zip(rows,rows[1:]):
        if a['startsAt'] > b['startsAt']: issues.append('non-chronological-source')
    # Same round twice is ambiguous unless occurrence is explicitly present.
    keys={}
    for r in rows:
        if r['kind']!='race':continue
        key=tuple(r.get(k) for k in ('date','gender','distance','discipline','round','occurrence'))
        if key in keys: issues.append('ambiguous-duplicate-round')
        keys[key]=r
    return rows,sorted(set(issues))


def race_participation(text,event,url):
    """Retrospective results prove participation, NOT a published pre-race start list."""
    rows=[]
    for page_no,page in enumerate(text.split('\f'),1):
        if not re.search(r'\b(RESULTS|START LIST)\b',page) or 'EVENT CLASSIFICATION' in page or 'TIME ANALYSIS' in page: continue
        title=re.search(r'\b(Men|Women) (500|1000|1500) m - ('+ROUND_RE+r')\b',page)
        date=re.search(r'(?:FRI|SAT|SUN|MON|TUE|WED|THU) (\d{1,2}) ([A-Z]{3}) (20\d{2})',page)
        if not title or not date:continue
        sex,dist,rd=title.groups();d,m,y=date.groups()
        day=f'{y}-{MONTHS[m]:02d}-{int(d):02d}'
        if not event['startDate']<=day<=event['endDate']:continue
        for line in page.splitlines():
            # C73A/C51 rows: athlete name then country. No matching surname alone.
            match=re.search(r'\b([A-Z][A-Za-zÀ-ž\x27 -]+?)\s{2,}LAT\b',line)
            if match:
                name=match[1].strip()
                if not re.search(r'[A-Za-z]',name):continue
                rows.append({'name':name,'nation':'LAT','gender':sex.lower(),'distance':int(dist),'round':ROUNDS[rd],
                             'date':day,'occurrence':1,'sourceUrl':url,'sourcePage':page_no,
                             'evidenceKind':'start-list' if 'START LIST' in page and 'RESULTS' not in page else 'retrospective-result',
                             'status':'DNS' if re.search(r'\bDNS\b',line) else 'listed','sourceText':line.strip()})
    return rows
