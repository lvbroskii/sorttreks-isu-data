// Stage D scaffold. Read-only routes, no public write endpoint or scheduled handler.
const ORIGINS = new Set(['https://sorttreks.lv','https://www.sorttreks.lv']);
export default {
 async fetch(request, env) {
  const origin=request.headers.get('Origin');
  const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Vary':'Origin'};
  if(origin && ORIGINS.has(origin))headers['Access-Control-Allow-Origin']=origin;
  const respond=(body,status=200)=>new Response(JSON.stringify(body),{status,headers});
  if(request.method!=='GET')return respond({error:'read-only'},405);
  const path=new URL(request.url).pathname;
  if(path==='/health')return respond({mode:'read-only-pilot',websiteUpdatesEnabled:false});
  if(!['/v1/pilot/latest','/v1/calendar'].includes(path))return respond({error:'not-found'},404);
  if(path==='/v1/calendar' && env.SERVE_APPROVED!=='true')return respond({error:'integration-disabled-use-bundled-fallback'},503);
  if(!env.DB)return respond({error:'database-not-configured'},503);
  const state=path==='/v1/calendar'?'approved':'candidate';
  try {
   const row=await env.DB.prepare('SELECT body, sha256, created_at FROM snapshots WHERE state = ? ORDER BY id DESC LIMIT 1').bind(state).first();
   if(!row)return respond({error:'no-snapshot-use-bundled-fallback'},503);
   const etag='"'+row.sha256+'"';
   if(request.headers.get('If-None-Match')===etag)return new Response(null,{status:304,headers:{...headers,ETag:etag}});
   // No approval or fallback promotion takes place in a read request.
   return new Response(row.body,{headers:{...headers,ETag:etag,'Cache-Control':'public, max-age=60'}});
  } catch {return respond({error:'storage-unavailable-use-bundled-fallback'},503)}
 }
};
