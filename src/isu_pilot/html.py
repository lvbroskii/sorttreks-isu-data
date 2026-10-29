"""Parse public HTML / Next Flight JSON as data; never evaluate source JavaScript."""
import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from .sources import official


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.links = []; self.text = []; self.scripts = []; self.anchor = None; self.script = False
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'): self.anchor = [a['href'], '']
        if tag == 'script': self.script = True
    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor:
            self.links.append(tuple(self.anchor)); self.anchor = None
        if tag == 'script': self.script = False
    def handle_data(self, data):
        if self.script: self.scripts.append(data)
        else:
            self.text.append(data)
            if self.anchor: self.anchor[1] += data


def flight_objects(page):
    chunks = []
    for script in page.scripts:
        for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)', script, re.S):
            try:
                value = json.loads(match[1])
                if value[0] == 1 and isinstance(value[1], str): chunks.append(value[1])
            except (ValueError, IndexError, TypeError): pass
    objects = []
    decoder = json.JSONDecoder()
    stream = ''.join(chunks)
    for line in stream.splitlines():
        m = re.match(r'^[0-9a-f]+:(.*)', line)
        if m:
            try: objects.append(decoder.raw_decode(m[1])[0])
            except ValueError: pass
    return objects


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)


def discover(text, url, event):
    page = Page(text)
    objects = list(obj for value in flight_objects(page) for obj in walk(value))
    tabs = {}; tab_states = {}; documents = {}; metadata = []
    for obj in objects:
        slug = obj.get('slug', '')
        if obj.get('event_type') in ('schedule', 'entries', 'result', 'documents') and slug:
            tab_states[obj['event_type']] = obj.get('is_active') is True
            if obj.get('is_active') is not False:
                tabs[obj['event_type']] = url.split('?')[0] + '?tab=' + slug
        if obj.get('slug') == url.split('?')[0].rstrip('/').split('/')[-1] and obj.get('season'):
            metadata.append(obj)
        if obj.get('file_url'):
            try:
                link = official(obj['file_url'])
                documents[link] = {'url': link, 'label': obj.get('label', ''), 'publishedDate': obj.get('date')}
            except ValueError: pass
    # Rendered links supplement the structured document registry, not every global PDF.
    for href, label in page.links:
        try: link = official(urljoin(url, unescape(href)))
        except ValueError: continue
        if '.pdf' in link.lower() and re.search(r'protocol|entries|announcement|schedule|start list|classification', label, re.I):
            documents.setdefault(link, {'url': link, 'label': label.strip()})
        if '?tab=' in link and link.split('?')[0] == url.split('?')[0]:
            for key, prefix in [('schedule','schedule_'),('entries','entries_'),('result','results_'),('documents','documents_')]:
                if 'tab='+prefix in link: tabs[key] = link
    identity = any(str(m.get('season')) == '2026/2027' and
                   str(m.get('from_date', '')).startswith(event['startDate']) and
                   str(m.get('to_date', '')).startswith(event['endDate']) for m in metadata)
    return {'tabs': tabs, 'tabStates': tab_states, 'documents': list(documents.values()), 'identityVerified': identity,
            'metadata': [{k:m.get(k) for k in ('id','api_id','season','from_date','to_date','time_zone','slug')} for m in metadata],
            'programmeShell': 'loading_schedule' in text,
            'visibleText': '\n'.join(page.text)}
