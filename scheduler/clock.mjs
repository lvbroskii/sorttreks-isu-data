// OPTIONAL independent clock. Disabled by default; never handles HTTP writes or ISU data.
import campaign from '../config/monitoring.json' with {type:'json'};
export const STATE='https://raw.githubusercontent.com/lvbroskii/sorttreks-isu-data/pilot-data/state/monitor-state.json';
export const DISPATCH='https://api.github.com/repos/lvbroskii/sorttreks-isu-data/actions/workflows/pilot.yml/dispatches';
export async function tick(controller,env,{fetcher=fetch,now=()=>Date.now()}={}){
 const at=controller.scheduledTime,clock=now(),start=Date.parse(campaign.startsAt),end=Date.parse(campaign.endsAt);
 const result={scheduledAt:new Date(at).toISOString(),checkedAt:new Date(clock).toISOString(),source:'cloudflare-scheduled-handler'};
 const done=status=>({...result,status});
 if(env.ENABLE_CLOCK!=='true')return done('disabled');
 if(!(start<=at&&at<end&&start<=clock&&clock<end))return done('outside-campaign-window');
 if(!env.GITHUB_DISPATCH_TOKEN)return done('missing-secret');
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),8000);
 try{
  const response=await fetcher(STATE,{signal:abort.signal,redirect:'error',cache:'no-store'});
  if(!response.ok)return done('archive-state-unavailable');
  if(Number(response.headers.get('Content-Length')||0)>262144)return done('archive-state-too-large');
  const reader=response.body.getReader(),chunks=[];let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>262144){await reader.cancel();return done('archive-state-too-large')}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
  const state=JSON.parse(new TextDecoder().decode(bytes)),last=Date.parse(state.lastCheckAt);
  if(state.eventId!==campaign.eventId||!Number.isFinite(last)||last>clock+60000)return done('archive-state-invalid');
  if(clock-last<(campaign.intervalMinutes*60-60)*1000)return done('collector-not-due');
  const dispatched=await fetcher(DISPATCH,{method:'POST',signal:abort.signal,redirect:'error',headers:{Accept:'application/vnd.github+json','Content-Type':'application/json','User-Agent':'sorttreks-isu-clock','X-GitHub-Api-Version':'2026-03-10',Authorization:'Bearer '+env.GITHUB_DISPATCH_TOKEN},body:JSON.stringify({ref:'main'})});
  // Never log credential values, request headers or response bodies.
  return {...done(dispatched.status===204?'dispatch-accepted':'dispatch-rejected'),httpStatus:dispatched.status};
 }catch{return done('clock-request-failed')}finally{clearTimeout(timer)}
}
export default {
 async fetch(request,env){return new Response(JSON.stringify({mode:'optional-read-only-collector-clock',enabled:env.ENABLE_CLOCK==='true',endsAt:campaign.endsAt}),{status:request.method==='GET'?200:405,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})},
 scheduled(controller,env,ctx){ctx.waitUntil(tick(controller,env).then(result=>console.log(JSON.stringify(result))))}
};
