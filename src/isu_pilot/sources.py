"""Bounded official-source HTTP client with conditional requests and local evidence."""
import hashlib
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import urllib.error
from .security import public_body
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode

HOSTS = {'isu-skating.com', 'www.isu-skating.com', 'isu.org', 'www.isu.org',
         'front-api.isu.org', 'isu-d8g8b4b7ece7aphs.a03.azurefd.net', 'isudam.blob.core.windows.net'}
MAX_BYTES = 12 * 1024 * 1024


def official(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None, 443):
        raise ValueError(f'Not an allowed official source: {url}')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, state_dir, previous=None, transport=None, byte_budget=None, raw_sink=None):
        self.root = Path(state_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.previous = previous or {}
        self.records = {}
        self.byte_budget=byte_budget
        self.raw_sink=raw_sink
        self.history_lock=threading.Lock()
        self.history_path=self.root/'source-history.json'
        self.history=json.loads(self.history_path.read_text()) if self.history_path.is_file() else {}
        self.deadline = time.monotonic() + 300
        self.transport = transport or urllib.request.build_opener(Redirect()).open

    def query(self, path, fields):
        """Read-only POST queries used by the public ISU results component."""
        allowed = {
            '/events/get-event-result-round': {'event_result_id'},
            '/events/get-event-result-round-heats-stk-single':
                {'event_result_id', 'event_result_round_id', 'country_code'},
        }
        if path not in allowed or set(fields) != allowed[path]:
            raise ValueError('Unsupported read-only timing query')
        if any(not str(v).isdigit() or int(v) <= 0 for k,v in fields.items() if k != 'country_code'):
            raise ValueError('Invalid timing identifier')
        if fields.get('country_code', '') != '':
            raise ValueError('Completeness requires the all-country response')
        encoded = urlencode(sorted(fields.items())).encode()
        return self._request('https://front-api.isu.org'+path, encoded)

    def query_many(self, requests):
        # Bounded parallel read queries keep complete programmes inside the run budget.
        with ThreadPoolExecutor(max_workers=3) as pool:
            return list(pool.map(lambda request: self.query(*request), requests))

    def get(self, url):
        return self._request(url)

    def _request(self, url, data=None):
        official(url)
        source_url = url
        request_data = data
        # A POST body is part of the source identity, not a shared URL cache entry.
        if data is not None:
            url += '?' + data.decode()

        if url in self.records:
            rec = self.records[url]
            return self.body(rec), rec
        prev = {**self.previous.get(url, {}), 'method': 'POST' if request_data is not None else 'GET',
                'requestUrl': source_url, 'requestBody': request_data.decode() if request_data is not None else None}
        if self.byte_budget is not None and self.byte_budget<=0:
            return self.failure(url,prev,datetime.now(timezone.utc).isoformat(),'Run download budget exhausted')
        if time.monotonic() > self.deadline:
            return self.failure(url, prev, datetime.now(timezone.utc).isoformat(), 'Run network budget exhausted')
        headers = {'User-Agent': 'sorttreks-isu-readonly-pilot/0.3', 'Accept-Encoding': 'identity', 'language_code': 'en'}
        if data is not None: headers['Content-Type'] = 'application/x-www-form-urlencoded'
        # Send validators only if the corresponding local body is retained.
        cached = self.root / (prev.get('sha256', '') + '.body')
        if cached.is_file():
            for k, h in [('etag', 'If-None-Match'), ('lastModified', 'If-Modified-Since')]:
                if prev.get(k): headers[h] = prev[k]
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            with self.transport(urllib.request.Request(source_url, data=data, headers=headers), timeout=30) as res:
                official(res.url)
                status = res.status
                if status != 200: raise ValueError(f'HTTP {status}')
                data = self.read_bounded(res)
                if len(data) > MAX_BYTES: raise ValueError('Source exceeds 12 MiB cap')
                mime = res.headers.get('Content-Type', '').split(';')[0]
                if not (mime in ('application/pdf', 'text/html', 'application/json') or data.startswith(b'%PDF-')):
                    raise ValueError(f'Unsupported content type: {mime}')
                original_digest=hashlib.sha256(data).hexdigest()
                data=public_body(data)
                digest = hashlib.sha256(data).hexdigest()
                rec = {'url': url, 'finalUrl': res.url, 'contentType': mime, 'sha256': digest,
                       'originalResponseSha256':original_digest,'credentialsRedacted':digest!=original_digest,
                       'fetchedAt': now, 'firstSeenAt': prev.get('firstSeenAt', now),
                       'etag': res.headers.get('ETag'), 'lastModified': res.headers.get('Last-Modified'),
                       'method': 'POST' if request_data is not None else 'GET',
                       'requestUrl': source_url, 'requestBody': request_data.decode() if request_data is not None else None,
                       'changed': digest != prev.get('sha256'), 'status': 'fetched', 'httpStatus': 200}
                (self.root / (digest + '.body')).write_bytes(data)
                if self.raw_sink:self.raw_sink(data)
        except urllib.error.HTTPError as err:
            if err.code == 304 and cached.is_file():
                rec = {**prev, 'fetchedAt': now, 'changed': False, 'status': 'not-modified', 'httpStatus': 304}
                data = cached.read_bytes()
            else:
                try:error_body=self.read_bounded(err)
                except (OSError,ValueError):error_body=None
                return self.failure(url, prev, now, f'HTTP {err.code}',err.code,error_body)
        except (OSError, ValueError) as err:
            return self.failure(url, prev, now, str(err))
        self.records[url] = rec
        self.record_version(url,rec)
        return data, rec

    def read_bounded(self,response):
        # Reserve across the three concurrent requests, not independently per thread.
        with self.history_lock:
            allowance=MAX_BYTES if self.byte_budget is None else min(MAX_BYTES,max(0,self.byte_budget))
            if not allowance:raise ValueError('Run download budget exhausted')
            if self.byte_budget is not None:self.byte_budget-=allowance
        data=b''
        try:
            data=response.read(allowance+1)
        finally:
            with self.history_lock:
                if self.byte_budget is not None:self.byte_budget+=allowance-len(data)
        if len(data)>allowance:raise ValueError('Source exceeds per-response or remaining run download budget; incomplete response discarded')
        return data

    def failure(self, url, prev, now, error, http_status=None, error_body=None):
        rec = {**prev, 'url': url, 'fetchedAt': now, 'status': 'unavailable',
               'changed': False, 'error': error[:300], 'stale': True}
        rec.pop('httpStatus',None);rec.pop('errorBodySha256',None)
        if http_status is not None:rec['httpStatus']=http_status
        if error_body is not None and len(error_body)<=MAX_BYTES:
            rec['originalErrorResponseSha256']=hashlib.sha256(error_body).hexdigest()
            error_body=public_body(error_body)
            rec['errorBodySha256']=hashlib.sha256(error_body).hexdigest()
            (self.root/(rec['errorBodySha256']+'.body')).write_bytes(error_body)
            if self.raw_sink:self.raw_sink(error_body)
        self.records[url] = rec
        self.record_version(url,rec)
        # A stale body is retained for audit only; callers must not re-verify it.
        return None, rec

    def body(self, rec):
        path = self.root / (rec.get('sha256', '') + '.body')
        return path.read_bytes() if rec.get('status') != 'unavailable' and path.is_file() else None

    def record_version(self,url,rec):
        with self.history_lock:
            self._record_version(url,rec)

    def _record_version(self,url,rec):
        entries=self.history.setdefault(url,[])
        # Keep retrieval attempts even on 304/failure, retaining raw hash/revision linkage.
        entries.append({k:rec.get(k) for k in ('url','finalUrl','sha256','fetchedAt','firstSeenAt','etag','lastModified','status','error','httpStatus','errorBodySha256','originalResponseSha256','originalErrorResponseSha256','credentialsRedacted','changed','method','requestUrl','requestBody')})
        self.history[url]=entries[-256:]
        temp=self.history_path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.history,ensure_ascii=False,separators=(',',':'))+'\n')
        temp.replace(self.history_path)
