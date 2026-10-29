// Shared Worker/browser contract. No HTML, executable markup or arbitrary event patches.
export const SCHEMA = 'sorttreks.calendar.v1';
export const MAX_BYTES = 262144;
export const MAX_AGE = 6 * 3600000;
const rounds = new Set(['preliminaries','heats','quarterfinals','semifinals','finals','repechage-heats','repechage-quarterfinals','repechage-semifinals']);
const hosts = new Set(['www.isu-skating.com','isu-skating.com','front-api.isu.org','www.isu.org','isu.org','isu-d8g8b4b7ece7aphs.a03.azurefd.net']);
export const instant = s => typeof s === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/.test(s) ? Date.parse(s) : NaN;
function require(ok, why) { if (!ok) throw Error(why); }
function keys(o, allowed) { require(o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).every(k=>allowed.includes(k)), 'unknown field'); }
export function official(s) { try { const u=new URL(s); return u.protocol==='https:' && !u.username && !u.password && hosts.has(u.hostname); } catch { return false; } }
const formatters=new Map();
function formatter(zone){if(!formatters.has(zone))formatters.set(zone,new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}));return formatters.get(zone);}
export function localDate(s, zone) { const p=formatter(zone).formatToParts(new Date(s)); return ['year','month','day'].map(k=>p.find(x=>x.type===k).value).join('-'); }
export function venueTime(s, zone) { const p=formatter(zone).formatToParts(new Date(s)); const g=k=>p.find(x=>x.type===k).value; const wall=`${g('year')}-${g('month')}-${g('day')}T${g('hour')}:${g('minute')}:${g('second')}`; const delta=(Date.parse(wall+'Z')-Date.parse(s))/60000; const a=Math.abs(delta); return wall+(delta<0?'-':'+')+String(Math.floor(a/60)).padStart(2,'0')+':'+String(a%60).padStart(2,'0'); }
export function roundKey(r, zone) { return [localDate(r.startsAt,zone),r.gender,r.distance,r.round,r.occurrence].join('|'); }
export function validateFeed(f, {now=Date.now(), allowSynthetic=false, baselineDigest}={}) {
 keys(f,['schemaVersion','kind','revision','issuedAt','validUntil','baselineDigest','events']);
 require(f.schemaVersion===SCHEMA && (f.kind==='approved' || allowSynthetic && f.kind==='synthetic-not-official'),'unapproved feed');
 require(Number.isSafeInteger(f.revision)&&f.revision>0,'invalid revision');
 const issued=instant(f.issuedAt),until=instant(f.validUntil);
 require(issued<=now+60000 && until>now && until>issued && until-issued<=MAX_AGE,'expired or invalid lifetime');
 require(/^[a-f0-9]{64}$/.test(f.baselineDigest) && (!baselineDigest || baselineDigest===f.baselineDigest),'baseline mismatch');
 require(Array.isArray(f.events)&&f.events.length>0&&f.events.length<=32,'empty/oversized feed');
 require(new TextEncoder().encode(JSON.stringify(f)).length<=MAX_BYTES,'oversized feed');
 const ids=new Set();
 for(const e of f.events) {
  keys(e,['id','timeZone','startDate','endDate','approval','sources','rounds','firstStarts','laterStarts','sessions','links']);
  require(/^[a-z0-9-]+$/.test(e.id)&&!ids.has(e.id),'event id'); ids.add(e.id);
  require(/^\d{4}-\d\d-\d\d$/.test(e.startDate)&&e.endDate>=e.startDate,'event dates');
  localDate(f.issuedAt,e.timeZone);
  keys(e.approval,['reviewer','reviewedAt','reportSha256','authorityVersionId','basis']);
  require(typeof e.approval.reviewer==='string'&&e.approval.reviewer.trim()&&instant(e.approval.reviewedAt)<=issued&&/^[a-f0-9]{64}$/.test(e.approval.reportSha256),'approval evidence');
  require(['resolved-official-programme','verified-website-baseline'].includes(e.approval.basis)&&e.approval.authorityVersionId,'authority evidence');
  require(Array.isArray(e.sources)&&e.sources.length>0&&e.sources.length<=64,'sources');
  const sources=new Set();
  for(const s of e.sources) { keys(s,['url','sha256','retrievedAt','revision']); require(official(s.url)&&/^[a-f0-9]{64}$/.test(s.sha256)&&instant(s.retrievedAt)<=issued&&s.revision&&typeof s.revision==='object','source evidence'); sources.add(s.url); }
  const stamp=r=>{require(Number.isFinite(instant(r.startsAt))&&sources.has(r.sourceUrl),'time/source');const date=localDate(r.startsAt,e.timeZone);require(date>=e.startDate&&date<=e.endDate,'outside event');};
  require(Array.isArray(e.rounds)&&e.rounds.length>0&&e.rounds.length<=500,'empty/incomplete programme');
  const known=new Map();
  for(const r of e.rounds) { keys(r,['gender','distance','round','occurrence','startsAt','sourceUrl','timeBasis']); stamp(r); require(['men','women'].includes(r.gender)&&[500,1000,1500].includes(r.distance)&&rounds.has(r.round)&&Number.isSafeInteger(r.occurrence)&&r.occurrence>0&&r.timeBasis==='round-start','round identity'); const k=roundKey(r,e.timeZone); require(!known.has(k),'duplicate round'); known.set(k,r); }
  for(const field of ['firstStarts','laterStarts']) {
   require(Array.isArray(e[field])&&e[field].length<=256,'draws'); const seen=new Set();
   for(const a of e[field]) { keys(a,['athlete','gender','distance','round','occurrence','startsAt','sourceUrl','roundSourceUrl','timeBasis','evidenceKind','openingDayCoverageComplete']); stamp(a); const r=known.get(roundKey(a,e.timeZone)); require(r&&instant(r.startsAt)===instant(a.startsAt)&&a.roundSourceUrl===r.sourceUrl&&a.timeBasis==='round-start'&&a.evidenceKind==='start-list'&&typeof a.athlete==='string'&&a.athlete.length>0&&a.athlete.length<=100,'unconfirmed assignment'); const k=a.athlete+'|'+(field==='firstStarts'?[a.gender,a.distance,a.occurrence].join('|'):roundKey(a,e.timeZone)); require(!seen.has(k),'duplicate athlete'); seen.add(k); if(field==='firstStarts')require(a.openingDayCoverageComplete===true&&localDate(a.startsAt,e.timeZone)===e.startDate,'first start coverage'); }
  }
  require(Array.isArray(e.sessions)&&e.sessions.length<=32,'sessions'); const sessionIds=new Set();
  for(const s of e.sessions) { keys(s,['id','label','startsAt','endsAt','sourceUrl','timeBasis']); stamp(s); require(/^[a-z0-9-]+$/.test(s.id)&&!sessionIds.has(s.id)&&s.timeBasis==='session-start'&&typeof s.label?.lv==='string'&&typeof s.label?.en==='string','session evidence'); sessionIds.add(s.id); if(s.endsAt!==null)require(instant(s.endsAt)>instant(s.startsAt)&&localDate(s.endsAt,e.timeZone)<=e.endDate,'session end'); }
  keys(e.links,['infoUrl','scheduleUrl','resultsUrl','entriesUrl','startListsUrl']); for(const u of Object.values(e.links))require(official(u),'official link');
 }
 return f;
}

// Overlay known events only; absence never deletes bundled or previously accepted rows.
export function mergeFeed(baseline, f, options={}) {
 validateFeed(f,options); const data=structuredClone(baseline);
 for(const e of f.events) {
  const event=data.events.find(x=>x.id===e.id);
  require(event&&event.timeZone===e.timeZone&&event.startDate===e.startDate&&event.endDate===e.endDate,'unknown/mismatched event');
  const time=r=>venueTime(r.startsAt,e.timeZone), date=r=>localDate(r.startsAt,e.timeZone);
  const match=(old,r)=>old.distance===r.distance&&old.round===r.round&&(old.occurrence||1)===r.occurrence&&date(old)===date(r)&&(!old.gender||old.gender===r.gender);
  for(const field of ['athleteFirstStarts','athleteRoundStarts']) for(const old of event[field]||[]) {
   const matches=e.rounds.filter(r=>match(old,r)); require(matches.length<=1,'ambiguous legacy athlete round'); if(matches.length){old.startsAt=time(matches[0]);old.scheduleSourceUrl=matches[0].sourceUrl;}
  }
  const conditional=event.conditionalRounds||[];
  for(const old of [...conditional,...(event.athleteFirstStarts||[]),...(event.athleteRoundStarts||[])])require(e.rounds.some(r=>match(old,r)),'programme reduction would hide verified rows');
  for(const r of e.rounds.filter(r=>date(r)>event.startDate)) {
   const matches=conditional.filter(old=>match(old,r)); require(matches.length<=1,'ambiguous legacy round');
   const row={...r,startsAt:time(r),confirmed:true,verifiedAt:e.approval.reviewedAt};
   if(matches.length)Object.assign(matches[0],row);else conditional.push(row);
  }
  event.conditionalRounds=conditional;
  // Full round inventory also includes opening-day rounds without implying LAT participation.
  const inventory=new Map((event.verifiedProgramme||[]).map(r=>[roundKey(r,e.timeZone),r]));for(const r of e.rounds)inventory.set(roundKey(r,e.timeZone),{...r,startsAt:time(r),confirmed:true});event.verifiedProgramme=[...inventory.values()];
  for(const [field,source] of [['athleteFirstStarts','firstStarts'],['athleteRoundStarts','laterStarts']]) {
   const rows=event[field]||[];
   for(const a of e[source]) {const old=rows.find(x=>x.athlete===a.athlete&&match(x,a));const row={...a,startsAt:time(a),confirmed:true,verifiedAt:e.approval.reviewedAt};if(old)Object.assign(old,row);else rows.push(row);} event[field]=rows;
  }
  const sessions=event.sessions||[];
  for(const s of e.sessions) {
   const old=sessions.find(x=>x.id===s.id);
   const row={...s,label:s.label.lv,labelTranslations:s.label,startsAt:time(s),startVerified:true,verifiedAt:e.approval.reviewedAt};
   if(s.endsAt){row.endsAt=venueTime(s.endsAt,e.timeZone);row.endVerified=true;row.endSourceUrl=s.sourceUrl;}
   // Existing owner estimates stay estimates; a new start cannot extend them or create overlap.
   if(old){if(!s.endsAt){row.endsAt=old.endsAt||null;row.endVerified=old.endVerified===true;}Object.assign(old,row);}else sessions.push({...row,endVerified:Boolean(s.endsAt)});
  }
  sessions.sort((a,b)=>instant(a.startsAt)-instant(b.startsAt));
  for(let i=0;i<sessions.length;i++) {const s=sessions[i],end=s.endVerified?s.endsAt:s.estimatedEndsAt;if(end)require(instant(end)>instant(s.startsAt)&&(!sessions[i+1]||instant(end)<=instant(sessions[i+1].startsAt)),'invalid/overlapping homepage window');}
  if(e.sessions.length){event.sessions=sessions;if(localDate(sessions[0].startsAt,e.timeZone)===event.startDate){event.startsAt=sessions[0].startsAt;event.startPrecision='time';}}
  if(e.firstStarts.length||e.laterStarts.length){event.latvianParticipationConfirmed=true;event.latvianEntries=[...new Set([...(event.latvianEntries||[]),...e.firstStarts.map(a=>a.athlete),...e.laterStarts.map(a=>a.athlete)])];}
  Object.assign(event,e.links);
  event.feedUpdatedAt=f.issuedAt;
 }
 return data;
}

// An accepted feed is cumulative across reloads, not an incremental patch.
export function noReduction(previous,next){
 if(!previous)return;
 for(const old of previous.events){
  const current=next.events.find(e=>e.id===old.id);require(current,'event reduction');
  const keys=rows=>new Set(rows.map(r=>roundKey(r,old.timeZone)));
  const rounds=keys(current.rounds);for(const k of keys(old.rounds))require(rounds.has(k),'round reduction');
  for(const field of ['firstStarts','laterStarts'])for(const a of old[field])require(current[field].some(r=>r.athlete===a.athlete&&roundKey(r,old.timeZone)===roundKey(a,old.timeZone)),'draw reduction');
  for(const s of old.sessions)require(current.sessions.some(r=>r.id===s.id),'session reduction');
 }
}
