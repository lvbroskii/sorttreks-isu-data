"""Explicit scoped HTML timetable adapter; unsupported client shells stay in review.

Supports rendered programme tables with Date/Time/Event/Round columns. It does
not infer schedule revision from unrelated CMS updated_at or HTTP headers.
"""
import re
from datetime import datetime
from html.parser import HTMLParser
from .pdf import ROUNDS,ROUND_RE,MONTHS
from .timezones import local_instant


class Tables(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True);self.tables=[];self.table=None;self.row=None;self.cell=None;self.scope=[];self.depth=0;self.current_scope=None
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'data-isu-programme' in a:
            self.current_scope={'attrs':a,'text':[]};self.scope.append(self.current_scope);self.depth=1
        elif self.current_scope:self.depth+=1 if tag not in ('meta','br','hr','img','input','link') else 0
        if tag=='table':self.table={'rows':[],'attrs':a,'text':[]};self.tables.append(self.table)
        if tag=='tr' and self.table:self.row=[];self.table['rows'].append(self.row)
        if tag in ('td','th') and self.row is not None:self.cell=[]
        if tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr':self.row=None
        if tag=='table':self.table=None
        if self.current_scope:
            self.depth-=1
            if self.depth<=0:self.current_scope=None
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
        if self.table:self.table['text'].append(data)
        if self.current_scope:self.current_scope['text'].append(data)


def evidence(text,zone,series=None):
    """Only schedule-scoped revision wording supplied by a scoped adapter."""
    result={'scope':'whole-event'}
    if series:result['series']=series
    pattern=r'(?:Schedule|Programme|Timetable)\s+(?:revised|updated)\s*(?:at|on)?\s*:?\s*(20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))?)'
    stamps=set(re.findall(pattern,text,re.I))
    if len(stamps)==1:result.update(revisedAt=next(iter(stamps)),evidenceText=re.search(pattern,text,re.I)[0])
    elif len(stamps)>1:result['ambiguousRevisionStamps']=sorted(stamps)
    # A PDF's explicitly stated revised date is different from its print date.
    rev=re.search(r'\bRevision\s*:?\s*(\d+(?:\.\d+)*)\b',text,re.I)
    if rev:result['number']=rev[1]
    return result


def pdf_revision(text,event):
    pages=[p for p in text.split('\f') if 'DETAILED TIME SCHEDULE' in p]
    scoped='\n'.join(pages)
    rev=evidence(scoped,event['timeZone'],event['id']+':C08')
    numbers=set(re.findall(r'_C08\s+(\d+(?:\.\d+)*)',scoped))
    if len(numbers)==1:rev['number']=next(iter(numbers))
    elif len(numbers)>1:rev['mixedPageRevisions']=sorted(numbers)
    printed=set()
    for d,m,y,t in re.findall(r'Print Date:\s*[A-Z]{3}\s+(\d{1,2}) ([A-Z]{3}) (20\d{2})\s+Print Time:\s*(\d{1,2}:\d{2})',scoped):
        if m in MONTHS:
            printed.add(f'{y}-{MONTHS[m]:02d}-{int(d):02d}T{t.zfill(5)}:00')
    if len(printed)==1:
        rev['printedAt']=next(iter(printed));rev['printedTimeZone']='unspecified'
    if len(printed)>1:rev['mixedPagePrintTimes']=sorted(printed)
    return rev


def programme(text,event,url,identity_verified):
    p=Tables(text);rows=[];issues=[];revision={};coverage=None
    if not identity_verified:return [],{},['online-event-identity-unverified']
    for table in p.tables:
        data=table['rows']
        if not data:continue
        header=[h.lower().strip() for h in data[0]]
        if not all(h in header for h in ('date','time','event','round')):continue
        if rows:issues.append('multiple-online-programme-tables');continue
        scoped=' '.join(table['text'])+' '+' '.join(' '.join(s['text']) for s in p.scope)
        revision=evidence(scoped,event['timeZone'],event['id']+':online-programme')
        coverage=table['attrs'].get('data-complete')
        for cells in data[1:]:
            if len(cells)!=len(header):issues.append('incomplete-online-row');continue
            item=dict(zip(header,cells));day=item['date'];clock=item['time']
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or not event['startDate']<=day<=event['endDate']:
                issues.append('online-date-outside-event');continue
            race=re.fullmatch(r'(Men|Women) (500|1000|1500|3000|5000) m( Relay)?',item['event'])
            mixed=item['event']=='Mixed Team Relay'
            if not race and not mixed:issues.append('unsupported-online-event');continue
            rd=re.fullmatch('('+ROUND_RE+r')(?:\s+(?:Race|Event)\s*#?([12]))?(?:\s+(CANCELLED))?',item['round'])
            if not rd:issues.append('unsupported-online-round');continue
            try:start=local_instant(day,clock,event['timeZone'])
            except ValueError:issues.append('invalid-online-time');continue
            sex,dist,relay=race.groups() if race else ('Mixed','2000',' Relay')
            rows.append({'kind':'race','date':day,'startsAt':start,'localTime':clock,'gender':sex.lower(),'distance':int(dist),
                         'discipline':'relay' if relay else 'individual','round':ROUNDS[rd[1]],'occurrence':int(rd[2] or 1),
                         'cancelled':bool(rd[3]),'heatCount':None,'sourceUrl':url,'sourceText':' | '.join(cells),'timeBasis':'round-start'})
    if not rows:issues.append('online-programme-shell-or-unsupported-format')
    # Never treat a filtered/partial table as a whole programme. Native adapter
    # must prove completeness; synthetic fixtures explicitly mark their extent.
    dates={r['date'] for r in rows}
    if coverage!='true' or not {event['startDate'],event['endDate']}<=dates:issues.append('online-completeness-unverified')
    if revision.get('ambiguousRevisionStamps'):issues.append('ambiguous-online-revision')
    return rows,revision,sorted(set(issues))
