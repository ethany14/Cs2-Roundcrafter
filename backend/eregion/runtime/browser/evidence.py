"""Compact observations, not model-authored summaries or inferred vacancies."""
from urllib.parse import urlsplit


def observed_links(result, limit=6):
    query=(result.get('query') or '').casefold().split()
    rows={}
    for control in result.get('controls', []):
        url, label=control.get('href') or '', (control.get('label') or '').strip()
        if not url.startswith('https://') or not label:
            continue
        path=urlsplit(url).path
        score=(sum(word in label.casefold() for word in query)*20 +
               (8 if control.get('content_link') else 0) + min(path.count('/'), 4) +
               (2 if len(label.split()) >= 3 else 0))
        row={'url':url,'label':label,'context':(control.get('context') or '')[:180]}
        if url not in rows or score > rows[url][0]:rows[url]=(score,row)
    return [row for _,row in sorted(rows.values(),key=lambda v:v[0],reverse=True)[:limit]]


def research_page(result, archive=None):
    page={k:result.get(k) for k in ('url','title','blocked')}
    page['links']=observed_links(result)
    page['excerpt']=(result.get('text') or '')[:400]
    if archive is not None:page.update(archive.reference(result))
    return page
