"""Read-only live smoke test. Never requests an enabled feed or changes Cloudflare."""
import argparse,json,sys,urllib.request,urllib.error
from datetime import datetime,timezone
from urllib.parse import urlsplit
p=argparse.ArgumentParser();p.add_argument('origin');p.add_argument('--local',action='store_true',help='Explicit local-runtime rehearsal only');a=p.parse_args();u=urlsplit(a.origin)
if u.path not in ('','/') or u.query or u.fragment or u.username or u.password: p.error('Use the exact deployed origin, without path/query/credentials')
if not (u.scheme=='https' and u.hostname.endswith('.workers.dev') or a.local and u.scheme=='http' and u.hostname in ('localhost','127.0.0.1')):p.error('Expected actual HTTPS workers.dev origin, or explicit local runtime')
origin=a.origin.rstrip('/');checks=[]
def query(name,path,method='GET',headers=None,status=200,allowed=None):
 req=urllib.request.Request(origin+path,method=method,headers=headers or {})
 try:r=urllib.request.urlopen(req,timeout=10)
 except urllib.error.HTTPError as e:r=e
 body=r.read(262145);h=r.headers
 assert r.status==status,(name,r.status,body[:200])
 assert h.get('Cache-Control')=='no-store',(name,'response must not be cached')
 assert h.get('Access-Control-Allow-Origin')==allowed,(name,'CORS origin')
 assert h.get('Access-Control-Allow-Credentials') is None,(name,'credentials forbidden')
 if method=='HEAD':assert body==b'',(name,'HEAD body')
 if path=='/v1/calendar' and method in ('GET','HEAD'):assert h.get('ETag') is None,(name,'disabled ETag')
 checks.append({'check':name,'status':r.status,'passed':True})
 return json.loads(body) if body else None,h
try:
 data,_=query('disabled health','/health');assert data['enabled'] is False and data['database'] is False and data['mode']=='approved-feed-delivery'
 for site in ['https://sorttreks.lv','https://www.sorttreks.lv']:
  data,_=query('disabled feed '+site,'/v1/calendar',headers={'Origin':site},status=503,allowed=site);assert data=={'error':'integration-disabled-use-bundled-fallback'}
  _,h=query('conditional GET preflight '+site,'/v1/calendar','OPTIONS',headers={'Origin':site,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'if-none-match'},status=204,allowed=site);assert h.get('Access-Control-Allow-Headers').lower()=='if-none-match'
  query('conditional disabled feed '+site,'/v1/calendar',headers={'Origin':site,'If-None-Match':'"test-only-no-approved-data"'},status=503,allowed=site)
 query('unknown origin has no CORS','/v1/calendar',headers={'Origin':'https://untrusted.invalid'},status=503)
 query('unknown origin preflight rejected','/v1/calendar','OPTIONS',headers={'Origin':'https://untrusted.invalid','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'if-none-match'},status=403)
 query('bodyless HEAD','/v1/calendar','HEAD',status=503)
 query('unknown route','/not-a-feed',status=404)
 query('write route rejected','/v1/calendar','POST',status=405)
 query('repeat remains disabled and not cached','/v1/calendar',status=503)
except Exception as err:
 print(json.dumps({'kind':'local-runtime-rehearsal' if a.local else 'live-cloudflare-disabled-smoke','origin':origin,'checkedAt':datetime.now(timezone.utc).isoformat(),'passed':False,'checks':checks,'error':str(err)},indent=2));sys.exit(1)
print(json.dumps({'kind':'local-runtime-rehearsal' if a.local else 'live-cloudflare-disabled-smoke','origin':origin,'checkedAt':datetime.now(timezone.utc).isoformat(),'passed':True,'checks':checks,'successfulFeedCaching':'not-tested-live-while-disabled; covered by offline regression tests'},indent=2))
