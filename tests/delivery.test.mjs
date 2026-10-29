import test from 'node:test';import assert from 'node:assert/strict';
import {createDelivery} from '../worker/delivery.mjs';
const origin='https://sorttreks.lv';
const request=(path='/v1/calendar',method='GET',headers={})=>new Request('https://disabled-worker.example'+path,{method,headers});
test('disabled production path never reads GitHub or cache, even with a matching conditional ETag',async()=>{
 let calls=0;const worker=createDelivery({fetcher:async()=>{calls++;throw Error('must not fetch')},cache:{match:async()=>{calls++;throw Error('must not read cache')}}});
 for(const method of ['GET','HEAD'])for(const source of [origin,'https://www.sorttreks.lv','https://evil.example']){
  const r=await worker.fetch(request('/v1/calendar',method,{Origin:source,'If-None-Match':'"old-enabled-feed"'}),{SERVE_APPROVED:'false'});
  assert.equal(r.status,503);assert.equal(r.headers.get('Cache-Control'),'no-store');assert.equal(r.headers.get('ETag'),null);
  assert.equal(r.headers.get('Access-Control-Allow-Origin'),source==='https://evil.example'?null:source);
  if(method==='HEAD')assert.equal(await r.text(),'');else assert.deepEqual(await r.json(),{error:'integration-disabled-use-bundled-fallback'});
 }
 assert.equal(calls,0);
});
test('browser conditional request preflight succeeds without enabling data delivery',async()=>{
 const w=createDelivery({fetcher:()=>{throw Error('must not fetch')}});
 for(const source of [origin,'https://www.sorttreks.lv']){
  const r=await w.fetch(request('/v1/calendar','OPTIONS',{Origin:source,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'if-none-match'}),{});
  assert.equal(r.status,204);assert.equal(r.headers.get('Access-Control-Allow-Origin'),source);assert.equal(r.headers.get('Access-Control-Allow-Headers'),'If-None-Match');assert.equal(r.headers.get('Access-Control-Allow-Credentials'),null);
  assert.equal((await w.fetch(request('/v1/calendar','GET',{Origin:source,'If-None-Match':'"previous"'}),{})).status,503);
 }
});
test('preflight rejects unknown origin, headers, write methods and paths',async()=>{
 const w=createDelivery();const headers={Origin:origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'if-none-match'};
 for(const patch of [{Origin:'https://evil.example'},{'Access-Control-Request-Method':'POST'},{'Access-Control-Request-Headers':'Authorization'}, {'Access-Control-Request-Headers':'if-none-match, x-extra'}])assert.equal((await w.fetch(request('/v1/calendar','OPTIONS',{...headers,...patch}),{})).status,403);
 assert.equal((await w.fetch(request('/unknown','OPTIONS',headers),{})).status,403);
});
test('health and all disabled error responses are not cached; HEAD remains bodyless',async()=>{
 const w=createDelivery();const r=await w.fetch(request('/health'),{});assert.deepEqual(await r.json(),{mode:'approved-feed-delivery',enabled:false,storage:'public-github',database:false});
 for(const [path,method,status] of [['/health','HEAD',200],['/v1/calendar','HEAD',503],['/unknown','HEAD',404],['/v1/calendar','POST',405]]){const r=await w.fetch(request(path,method),{});assert.equal(r.status,status);assert.equal(r.headers.get('Cache-Control'),'no-store');if(method==='HEAD')assert.equal(await r.text(),'');}
});
