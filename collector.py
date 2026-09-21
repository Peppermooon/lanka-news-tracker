"""RSS collector. Run using GitHub Actions, or locally with pip install -r requirements.txt."""
import json, hashlib, re, os, calendar
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests, feedparser

ROOT = Path(__file__).parent
DB = ROOT / 'data' / 'news.json'
# Publisher RSS endpoints; availability and terms may change. Add additional VERIFIED feeds here.
SOURCES = [
    {'name':'Daily Mirror', 'url':'https://www.dailymirror.lk/rss/breaking_news/108'},
    {'name':'The Island', 'url':'https://island.lk/feed/'},
    {'name':'EconomyNext', 'url':'https://economynext.com/feed/'},
]
SL = timezone(timedelta(hours=5, minutes=30))
STOP = {'the','a','an','and','or','of','to','in','on','at','for','from','with','as','by','after','before','is','are','was','were','has','have','had','sri','lanka','says','said','new','latest','report','reports','over','amid','into','about','under','more','its','their','will','not','this','that','his','her','first','today'}

def date_iso(entry, key):
    parsed = entry.get(key + '_parsed')
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc).isoformat()
    raw = entry.get(key, '')
    if raw:
        try:
            d = parsedate_to_datetime(raw)
            return (d if d.tzinfo else d.replace(tzinfo=SL)).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, IndexError):
            try:
                d=datetime.fromisoformat(raw)
                return (d if d.tzinfo else d.replace(tzinfo=SL)).astimezone(timezone.utc).isoformat()
            except ValueError: pass
    return None

def normalize_url(url):
    p=urlsplit(url.strip())
    query=urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), query, ''))

def tokens(title):
    return set(x for x in re.findall(r'[^\W_]+', title.lower(), re.UNICODE) if len(x)>2 and x not in STOP)

def cluster(rows):
    """Conservative headline matching only; review clusters, especially across languages."""
    groups=[]
    for row in sorted(rows, key=lambda a:a.get('published_at') or a['first_seen_at']):
        ta=tokens(row['title'])
        if len(ta)<3:
            groups.append({'members':[row], 'tokens':ta}); continue
        best=None; best_score=0
        for group in groups:
            head=group['members'][0]
            try:
                age=abs((datetime.fromisoformat(row.get('published_at') or row['first_seen_at'])-datetime.fromisoformat(head.get('published_at') or head['first_seen_at'])).total_seconds())
            except ValueError: continue
            if age>72*3600: continue
            tb=group['tokens']; intersection=len(ta & tb)
            # Require 3 matching meaningful tokens and high overlap to avoid merging unrelated incidents.
            score=intersection/min(len(ta),len(tb)) if tb else 0
            if intersection>=3 and score>=0.76 and score>best_score:
                best=group; best_score=score
        if best is None: groups.append({'members':[row], 'tokens':ta})
        else: best['members'].append(row)
    out=[]
    for group in groups:
        members=sorted(group['members'],key=lambda a:a.get('published_at') or a['first_seen_at'])
        first=members[0]
        latest=max((m.get('published_at') or m['first_seen_at']) for m in members)
        out.append({'id':first['id'],'title':first['title'],'earliest_published_at':first.get('published_at'), 'earliest_first_seen_at':first['first_seen_at'],'latest_at':latest,'articles':members})
    return sorted(out,key=lambda a:a['latest_at'],reverse=True)

def run():
    now=datetime.now(timezone.utc).isoformat()
    old=json.loads(DB.read_text(encoding='utf-8')) if DB.exists() else {}
    articles={a['id']:a for a in old.get('articles', [])}
    statuses=[]
    for source in SOURCES:
        try:
            resp=requests.get(source['url'],headers={'User-Agent':'LankaNewsTracker/1.0 (RSS reader; contact repository owner)'},timeout=22)
            resp.raise_for_status()
            feed=feedparser.parse(resp.content)
            if not feed.entries: raise ValueError('Feed contains no entries')
            found=0
            for e in feed.entries[:100]:
                title=re.sub(r'<[^>]+>','',e.get('title','')).strip()
                link=normalize_url(e.get('link',''))
                if not title or not link.startswith('https://'): continue
                uid=hashlib.sha256((source['name']+'|'+link).encode()).hexdigest()[:24]
                pub=date_iso(e,'published') or date_iso(e,'updated')
                if uid in articles:
                    # Never overwrite the originally observed timestamp; preserve any edited publication times separately.
                    articles[uid]['last_seen_at']=now
                    if pub and pub!=articles[uid].get('published_at'):
                        articles[uid]['latest_claimed_published_at']=pub
                else:
                    articles[uid]={'id':uid,'source':source['name'],'title':title,'url':link,'published_at':pub,'first_seen_at':now,'last_seen_at':now}
                    found+=1
            statuses.append({'source':source['name'],'status':'ok','new_articles':found,'checked_at':now})
        except Exception as exc:
            statuses.append({'source':source['name'],'status':'error','message':str(exc)[:160],'checked_at':now})
    # Keep all previously collected records to preserve historic earliest-detection evidence.
    ordered=sorted(articles.values(),key=lambda a:a.get('published_at') or a['first_seen_at'],reverse=True)
    output={'updated_at':now,'sources':statuses,'article_count':len(ordered),'articles':ordered,'stories':cluster(ordered)}
    DB.parent.mkdir(parents=True,exist_ok=True)
    DB.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Collected',len(ordered),'articles;',statuses)
    # When all sources fail, do not commit a misleading empty fresh snapshot.
    if not any(s['status']=='ok' for s in statuses): raise SystemExit('All feeds failed; retaining prior article history')

if __name__=='__main__': run()
