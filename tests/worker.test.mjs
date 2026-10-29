import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker/index.mjs';
const get=(path,env={},headers={})=>worker.fetch(new Request('https://pilot.example'+path,{headers}),env);
test('read-only health exposes no writes',async()=>{
 assert.equal((await get('/health')).status,200);
 assert.equal((await worker.fetch(new Request('https://pilot.example/v1/pilot/latest',{method:'POST'}),{})).status,405);
});
test('approved endpoint disabled by default; missing DB returns fallback',async()=>{
 assert.equal((await get('/v1/calendar')).status,503);
 assert.equal((await get('/v1/pilot/latest')).status,503);
});
test('serves candidate only, bounded indexed query and ETag',async()=>{
 const env={DB:{prepare(sql){assert.match(sql,/WHERE state = \?/);return {bind(state){assert.equal(state,'candidate');return {first:async()=>({body:'{"approvedForWebsite":false}',sha256:'abc'})}}}}}};
 const response=await get('/v1/pilot/latest',env,{Origin:'https://sorttreks.lv'});
 assert.equal(response.status,200);assert.equal(response.headers.get('Access-Control-Allow-Origin'),'https://sorttreks.lv');
 assert.equal((await get('/v1/pilot/latest',env,{'If-None-Match':'"abc"'})).status,304);
 assert.equal((await get('/v1/pilot/latest',env,{Origin:'https://evil.example'})).headers.get('Access-Control-Allow-Origin'),null);
});
test('DB outage fails closed',async()=>{
 const env={DB:{prepare(){throw Error('quota')}}};assert.equal((await get('/v1/pilot/latest',env)).status,503);
});
