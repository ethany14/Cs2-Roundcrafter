"""Public-only transport diagnostic; no model or private data."""
import json
from urllib.parse import urlencode, quote
from xml.etree import ElementTree as E
import httpx

rows = []
with httpx.Client(timeout=15) as client:
    for query in ['CS2 Mirage Window smoke', '"Mirage" "Window" smoke', 'site:csnades.gg mirage window']:
        for encoding in ['plus', 'percent']:
            params = {'q': query, 'format': 'rss'}
            url = 'https://www.bing.com/search?' + (urlencode(params) if encoding == 'plus' else urlencode(params, quote_via=quote))
            try:
                r = client.get(url)
                result = [{'title': i.findtext('title'), 'url': i.findtext('link')}
                          for i in E.fromstring(r.text).findall('./channel/item')]
                rows.append({'query': query, 'encoding': encoding, 'status': r.status_code, 'results': result})
            except Exception as exc:
                rows.append({'query': query, 'encoding': encoding, 'error': type(exc).__name__})
print(json.dumps(rows, ensure_ascii=False, indent=2))
