import {validateFeed,mergeFeed,noReduction,MAX_BYTES} from './feed.mjs';
// Poll one feed per visible tab. No credentials, background automation or candidate URLs.
export function createFeedClient({baseline,baselineDigest,url,enabled=false,allowSynthetic=false,fetcher=globalThis.fetch,storage=globalThis.localStorage,onUpdate=()=>{},onStatus=()=>{},now=()=>Date.now(),timeoutMs=5000}) {
 let accepted=null,busy=false,etag=null,currentData=structuredClone(baseline); const key='sorttreks-approved-v1:'+url;
 const options=()=>({baselineDigest,allowSynthetic,now:now()});
 function commit(feed){validateFeed(feed,options());noReduction(accepted,feed);if(accepted&&(feed.revision<accepted.revision||feed.revision===accepted.revision&&JSON.stringify(feed)!==JSON.stringify(accepted)))throw Error('rollback or reused revision');const merged=mergeFeed(currentData,feed,options());currentData=merged;accepted=feed;onUpdate(merged);try{storage?.setItem(key,JSON.stringify(feed))}catch{}onStatus('current',feed.issuedAt);}
 function fallback(){if(accepted&&Date.parse(accepted.validUntil)>now())onStatus('retained',accepted.issuedAt);else{accepted=null;etag=null;currentData=structuredClone(baseline);onUpdate(currentData);onStatus('fallback');}}
 if(enabled){try {const saved=storage?.getItem(key);if(saved)commit(JSON.parse(saved))}catch{try{storage?.removeItem(key)}catch{}}}
 async function refresh(){
  if(!enabled||busy)return;busy=true;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
  try {
   if(!allowSynthetic&&new URL(url).protocol!=='https:')throw Error('HTTPS required');
   const res=await fetcher(url,{credentials:'omit',cache:'no-cache',signal:controller.signal,headers:etag?{'If-None-Match':etag}:{}});
   if(res.status===304){if(!accepted)throw Error('304 without snapshot');validateFeed(accepted,options());onStatus('current',accepted.issuedAt);return;}
   if(!res.ok||Number(res.headers.get('Content-Length')||0)>MAX_BYTES)throw Error('feed unavailable');
   const reader=res.body.getReader(),chunks=[];let length=0;
   while(true){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>MAX_BYTES){await reader.cancel();throw Error('oversized feed')}chunks.push(value);}
   const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
   commit(JSON.parse(new TextDecoder().decode(bytes)));etag=res.headers.get('ETag');
  }catch{fallback()}finally{clearTimeout(timer);busy=false;}
 }
 return {refresh,expire:fallback,get current(){return accepted}};
}
export function startFeedRefresh(client,{view=window,root=document,intervalMs=300000}={}) {
 const refresh=()=>{client.expire();if(!root.hidden)void client.refresh()};
 const timer=view.setInterval(refresh,intervalMs);root.addEventListener('visibilitychange',refresh);view.addEventListener('pageshow',refresh);view.addEventListener('online',refresh);refresh();
 return()=>{view.clearInterval(timer);root.removeEventListener('visibilitychange',refresh);view.removeEventListener('pageshow',refresh);view.removeEventListener('online',refresh)};
}
