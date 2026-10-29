// Approved-feed delivery only. No database, tokens, write route or scheduled handler.
import {validateFeed, MAX_BYTES} from '../integration/feed.mjs';
export const UPSTREAM='https://raw.githubusercontent.com/lvbroskii/sorttreks-isu-data/approved-data/calendar.v1.json';
const ORIGINS=new Set(['https://sorttreks.lv','https://www.sorttreks.lv']);
export function createDelivery({fetcher=fetch,cache=globalThis.caches?.default,now=()=>Date.now()}={}) {
 return {async fetch(request,env={},ctx={waitUntil:()=>{}}) {
  const origin=request.headers.get('Origin');
  const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Vary':'Origin','X-Content-Type-Options':'nosniff'};
  if(ORIGINS.has(origin)){headers['Access-Control-Allow-Origin']=origin;headers['Access-Control-Expose-Headers']='ETag';}
  const respond=(o,status)=>new Response(JSON.stringify(o),{status,headers});
  const path=new URL(request.url).pathname;
  if(!['GET','HEAD'].includes(request.method))return respond({error:'read-only'},405);
  if(path==='/health')return respond({mode:'approved-feed-delivery',enabled:env.SERVE_APPROVED==='true',storage:'public-github',database:false},200);
  if(path!=='/v1/calendar')return respond({error:'not-found'},404);
  if(env.SERVE_APPROVED!=='true')return respond({error:'integration-disabled-use-bundled-fallback'},503);
  const key=new Request('https://approved-feed.internal/v1/calendar');
  try {
   let response=await cache?.match(key);let body;
   if(response){body=await response.text();try{validateFeed(JSON.parse(body),{now:now()});}catch{response=null;}}
   if(!response){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),4000);
    try {
     const upstream=await fetcher(UPSTREAM,{signal:controller.signal,redirect:'error',headers:{Accept:'application/json'}});
     if(!upstream.ok||Number(upstream.headers.get('Content-Length')||0)>MAX_BYTES)throw Error('upstream unavailable');
     const reader=upstream.body.getReader();const chunks=[];let length=0;
     while(true){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>MAX_BYTES){await reader.cancel();throw Error('oversized')}chunks.push(value);}
     const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
     body=new TextDecoder().decode(bytes);validateFeed(JSON.parse(body),{now:now()});
    }finally{clearTimeout(timer);}
    const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body));const tag='"'+Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('')+'"';
    response=new Response(body,{headers:{'Content-Type':'application/json','Cache-Control':'public, max-age=60',ETag:tag}});
    if(cache)ctx.waitUntil(cache.put(key,response.clone()));
   }
   const outgoing={...headers,ETag:response.headers.get('ETag'),'Cache-Control':'public, max-age=60, must-revalidate'};
   if(request.headers.get('If-None-Match')===outgoing.ETag)return new Response(null,{status:304,headers:outgoing});
   return new Response(request.method==='HEAD'?null:body,{headers:outgoing});
  }catch{return respond({error:'approved-feed-unavailable-use-verified-fallback'},503)}
 }};
}
export default createDelivery();
