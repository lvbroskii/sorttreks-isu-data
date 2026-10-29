import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .html import discover
from .pdf import timetable, race_participation, pdf_text
from .matching import match_athletes, compare
from .timezones import display
from .programme import programme,pdf_revision
from .revisions import History,version
from .live_api import collect_live
from .publication import assess,changes as publication_changes

# A calendar-only boundary: homepage windows/estimates/selection are never exported.
PATCH_FIELDS={'id','athleteFirstStarts','athleteRoundStarts','conditionalRounds','startListsUrl','startListsVerified'}


def build(event,text,source_url,aliases,reference=None):
    schedule,issues=timetable(text,event,source_url)
    participants=race_participation(text,event,source_url) if schedule else []
    return build_rows(event,schedule,participants,aliases,reference,issues)


def build_rows(event,schedule,participants,aliases,reference=None,issues=None):
    issues=list(issues or [])
    first,later,matching_issues=match_athletes(schedule,participants,aliases,event)
    issues += matching_issues
    if not participants:issues.append('no-event-specific-start-lists-or-results')
    if participants and not any(p['evidenceKind']=='start-list' for p in participants):
        issues.append('historical-results-only-not-pre-race-start-lists')
    comparisons=compare(reference or {},schedule,first)
    if any(c['status']!='match' for c in comparisons):issues.append('manual-reference-discrepancy')
    confirmed_first=[r for r in first if r['confirmed']]
    confirmed_later=[r for r in later if r['confirmed']]
    patch={'id':event['id'],'athleteFirstStarts':confirmed_first,'athleteRoundStarts':confirmed_later,
           'conditionalRounds':[{'distance':r['distance'],'round':r['round'],'startsAt':r['startsAt'],'occurrence':r['occurrence'],
                                 'confirmed':True,'sourceUrl':r['sourceUrl']} for r in schedule if r['kind']=='race' and
                                r.get('discipline')=='individual' and r['date']>event['startDate'] and not r.get('cancelled')]}
    assert set(patch)<=PATCH_FIELDS
    return {'schemaVersion':1,'event':event,'verificationStatus':'needs-review' if issues else 'validated-candidate',
            'issues':issues,'schedule':schedule,'athleteFirstStarts':first,'athleteRoundStarts':later,
            'comparison':comparisons,'calendarPatchCandidate':patch,'approvedForWebsite':False,
            'counts':{'scheduleRows':len(schedule),'latParticipants':len(participants),'firstStarts':len(first)},
            'notes':['Times are round starts, not individual heat times.','Protocol observations are retrospective; source publication before racing is not established.']}


def offline(root):
    root=Path(root)
    events=json.loads((root/'config/events.json').read_text())
    aliases=json.loads((root/'config/athletes.json').read_text())
    reference=json.loads((root/'config/site-reference.json').read_text())
    meta=json.loads((root/'fixtures/real/manifest.json').read_text())
    event=events[0]
    data=build(event,(root/'fixtures/real/vancouver-protocol-extract.txt').read_text(),meta['protocolUrl'],aliases,reference['events'][0])
    def restore_pages(value):
        if isinstance(value,dict):
            if 'sourcePage' in value:value['sourcePage']=meta['originalPdfPages'][value['sourcePage']-1]
            for v in value.values():restore_pages(v)
        elif isinstance(value,list):
            for v in value:restore_pages(v)
    restore_pages(data)
    data['fixtureProvenance']=meta
    data['revisionValidation']=vancouver_archive(root,event,data)
    for comparison in data['comparison']:
        comparison['assessment']='unresolved-schedule-revision; not a finding that the website time was wrong'
    return data


def vancouver_archive(root,event,sample):
    root=Path(root)
    text=(root/'fixtures/real/vancouver-protocol-extract.txt').read_text()
    html=(root/'fixtures/real/vancouver-programme-shell.html').read_text()
    url=event['infoUrl']+'?tab=schedule_16230'
    rows,revision,errors=programme(html,event,url,True)
    return {'status':'needs-review','supersessionEstablished':False,
            'ownerExplanation':'The owner reports that the online programme was revised after the original C08; the website was manually updated with those newer times.',
            'pdfRevision':pdf_revision(text,event),'onlineArchivedRowCount':len(rows),
            'onlineArchivedEvidenceIssues':errors,
            'archiveLimitation':'The saved online capture contains a loading shell, not the revised timetable or a schedule-specific revision stamp. No archived evidence establishes the exact superseding version.',
            'retrievalDateIsNotRevisionDate':True,'websiteTimesIncorrect':None,
            'action':'Retain the existing manually verified website data; do not apply the older C08 over it.',
            'timeDifferences':[{'athlete':c['athlete'],'distance':c['distance'],'round':c['expectedRound'],
                                'olderC08Time':c['actual'],'manuallyUpdatedWebsiteTime':c['expected'],
                                'source':sample['fixtureProvenance']['protocolUrl'],
                                'updatedTimeProvenance':'manual site reference; revised online content not captured'} for c in sample['comparison']]}


def retime_previous(report,selected):
    """Keep athlete/round identity; update only its matched round's scheduled time."""
    import copy
    result=copy.deepcopy(report)
    result['schedule']=selected['rows']
    missing=[]
    for field in ('athleteFirstStarts','athleteRoundStarts'):
        for old in result.get(field,[]):
            matches=[r for r in selected['rows'] if r.get('kind')=='race' and r.get('discipline')=='individual' and not r.get('cancelled') and
                     r.get('gender')==old.get('gender') and r.get('distance')==old['distance'] and r.get('round')==old['round'] and
                     r.get('occurrence',1)==old.get('occurrence',1) and r['date']==old['startsAt'][:10]]
            if len(matches)==1:
                old['startsAt']=matches[0]['startsAt'];old['scheduleSourceUrl']=selected['url']
                old['latvianTime']={'lv':display(old['startsAt']),'en':display(old['startsAt'],lang='en')}
            else:missing.append({'code':'retained-athlete-round-not-in-revised-schedule','athlete':old['athlete'],'round':old['round']})
    # Retained athlete evidence is never silently upgraded by a schedule revision.
    if result.get('calendarPatchCandidate'):
        result['calendarPatchCandidate']['athleteFirstStarts']=[r for r in result.get('athleteFirstStarts',[]) if r.get('confirmed')]
        result['calendarPatchCandidate']['athleteRoundStarts']=[r for r in result.get('athleteRoundStarts',[]) if r.get('confirmed')]
    result['issues']=list(result.get('issues',[]))+missing
    if missing:result['verificationStatus']='needs-review'
    result['approvedForWebsite']=False
    return result


def collect(events,aliases,reference,client,history=None):
    history=history or History(client.root/'schedules.json')
    output=[]
    for event in events:
        pages=[];docs={};issues=[];versions=[];participants=[]
        raw,rec=client.get(event['infoUrl'])
        main=discover(raw.decode('utf-8',errors='replace'),event['infoUrl'],event) if raw else {'tabs':{},'documents':[],'identityVerified':False,'programmeShell':False}
        if raw is None:issues.append('event-page-unavailable')
        else:pages.append(main)
        # Fall back to previously DISCOVERED same-event tab URLs on a transient shell/outage.
        prior_tabs=history.data['events'].get(event['id'],{}).get('tabs',{})
        tabs={**prior_tabs,**main['tabs']}
        for kind in ('documents','schedule','entries','result'):
            url=tabs.get(kind)
            if not url:continue
            body,source=client.get(url)
            if body is not None:
                page=discover(body.decode('utf-8',errors='replace'),url,event);pages.append(page)
                if kind=='schedule':
                    rows,revision,errors=programme(body.decode('utf-8',errors='replace'),event,url,page['identityVerified'])
                    versions.append(version(event,'online',url,rows,source,revision,errors))
            else:issues.append('source-unavailable:'+kind)
        for page in pages:
            for doc in page['documents']:docs[doc['url']]=doc
        prior_docs=history.data['events'].get(event['id'],{}).get('documents',[])
        # Recheck only known official timetable links if document discovery is unavailable.
        if not docs:
            for doc in prior_docs:docs[doc['url']]=doc
        cms_ids={int(m['id']) for m in main.get('metadata',[]) if str(m.get('id','')).isdigit() and int(m['id'])>0}
        cms_id=next(iter(cms_ids)) if len(cms_ids)==1 and main['identityVerified'] else None
        api_rows,api_people,api_evidence=collect_live(event,client,main['identityVerified'],cms_id,main['tabs'].get('result'))
        api_issues=api_evidence['issues']
        versions.append(version(event,'online',api_evidence['programmeSource']['url'],api_rows,
                                api_evidence['programmeSource'],{},api_issues))
        ranked=sorted(docs.values(),key=lambda d:0 if any(w in d['label'].lower() for w in ('protocol','schedule')) else 1)
        for doc in ranked[:4]:
            body,source=client.get(doc['url'])
            if not body or not body.startswith(b'%PDF-'):continue
            try:
                text=pdf_text(client.root/(source['sha256']+'.body'))
                if 'DETAILED TIME SCHEDULE' in text:
                    rows,errors=timetable(text,event,doc['url'])
                    revision=pdf_revision(text,event)
                    if revision.get('mixedPageRevisions') or revision.get('mixedPagePrintTimes'):errors.append('mixed-c08-page-revisions')
                    versions.append(version(event,'pdf',doc['url'],rows,source,revision,errors))
                    if rows and not errors:participants.extend(race_participation(text,event,doc['url']))
                doc['textStatus']='extracted'
            except (OSError,ValueError,subprocess.SubprocessError) as err:
                doc['textStatus']='needs-review';doc['error']=str(err)[:200];issues.append('pdf-extraction-incomplete')
        participants.extend(api_people)
        prior_state=history.data['events'].get(event['id'],{})
        prior_report=prior_state.get('report')
        decision=history.resolve(event['id'],versions)
        selected=decision['selected']
        if decision['status']=='resolved' and selected:
            ref=next((r for r in reference['events'] if r['id']==event['id']),{})
            fresh_lists=any(p.get('evidenceKind')=='start-list' for p in participants)
            result=retime_previous(prior_report,selected) if prior_report and not fresh_lists else build_rows(event,selected['rows'],participants,aliases,ref)
            result['comparison']=compare(ref,selected['rows'],result.get('athleteFirstStarts',[]))
            result['issues']=[issue for issue in result['issues'] if issue!='manual-reference-discrepancy']
            if any(c['status']!='match' for c in result['comparison']):result['issues'].append('unresolved-source-revision-against-manual-reference')
        elif prior_report:
            # Copy all previously verified athlete rows; never replace them with empty arrays.
            import copy
            result=copy.deepcopy(prior_report)
            result['verificationStatus']='needs-review'
            result['issues']=['previous-local-data-retained']
        else:
            result={'event':event,'verificationStatus':'needs-review','issues':[],
                    'calendarPatchCandidate':None,'approvedForWebsite':False,'fallback':'bundled-site-reference-retained'}
        if decision['status']!='resolved':issues.append(decision['reason'])
        if not any(v['kind']=='online' and v['complete'] for v in versions):issues.append('online-programme-incomplete; supersession-not-established')
        from .matching import name_key
        alias_map={name_key(raw):name for raw,name in aliases.items()}
        for person in api_people:person['matchedAthlete']=alias_map.get(name_key(person['name']))
        result['publication']=assess(event,main,api_evidence,result.get('athleteFirstStarts') if decision['status']=='resolved' and api_evidence.get('programmeComplete') and api_evidence.get('preRaceStartListsVerified') else [],
                                     result.get('athleteRoundStarts') if api_evidence.get('participants') else [])
        result['publicationChanges']=publication_changes((prior_report or {}).get('publication'),result['publication'])
        result['liveApi']=api_evidence
        result['issues']+=issues
        if issues or decision['status']!='resolved':result['verificationStatus']='needs-review'
        # Rows are stored once per source version in history, rather than duplicated in report.
        result['scheduleAuthority']={k:v for k,v in decision.items() if k!='selected'}
        for comparison in result.get('comparison',[]):
            if comparison['status']!='match':comparison['assessment']='unresolved source/revision difference; website correctness not determined'
        result['scheduleAuthority']['selectedVersionId']=selected['versionId'] if selected else None
        result['scheduleAuthority']['selectedSource']=selected['url'] if selected else None
        result['scheduleVersions']=[{k:v for k,v in item.items() if k!='rows'} for item in versions]
        result['discovery']={'tabs':tabs,'documents':list(docs.values()),'identityVerified':main['identityVerified'],
                             'programmeShellDetected':any(p['programmeShell'] for p in pages)}
        # Do not recursively nest prior authority/history inside retained reports.
        retained={k:v for k,v in result.items() if k not in ('scheduleAuthority','scheduleVersions','discovery','liveApi')}
        history.data['events'][event['id']].update(tabs=tabs,documents=list(docs.values()),report=retained)
        output.append(result)
    history.save()
    return output
