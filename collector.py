"""Lanka Puvath live collector.

No paid news API is required. The collector reads RSS/Atom feeds where available and
uses conservative homepage link discovery as a fallback. It stores the first time
this app saw every article so later runs cannot erase first-report evidence.
"""
from __future__ import annotations
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
DB = ROOT / "data" / "news.json"
SL = timezone(timedelta(hours=5, minutes=30))
UA = "LankaPuvath/2.0 (+GitHub Pages personal news reader)"

# RSS is preferred because it normally carries a publisher-supplied timestamp.
# When rss is None, homepage discovery is used. Publisher layouts can change,
# so source status is visible in the app.
SOURCES = [
    {"name":"Ada Derana", "homepage":"https://sinhala.adaderana.lk/", "rss":None, "color":"#9C2637"},
    {"name":"Hiru News", "homepage":"https://www.hirunews.lk/", "rss":None, "color":"#D66B1D"},
    {"name":"News First", "homepage":"https://sinhala.newsfirst.lk/", "rss":None, "color":"#254A8A"},
    {"name":"ITN News", "homepage":"https://www.itnnews.lk/", "rss":None, "color":"#7A3D91"},
    {"name":"Lankadeepa", "homepage":"https://www.lankadeepa.lk/", "rss":None, "color":"#2F6F4E"},
    {"name":"Daily Mirror", "homepage":"https://www.dailymirror.lk/", "rss":"https://www.dailymirror.lk/rss/breaking_news/108", "color":"#A5222D"},
    {"name":"EconomyNext", "homepage":"https://economynext.com/", "rss":"https://economynext.com/feed/", "color":"#B77A1D"},
    {"name":"The Island", "homepage":"https://island.lk/", "rss":"https://island.lk/feed/", "color":"#3B5F7A"},
]

STOP = {
    'the','a','an','and','or','of','to','in','on','at','for','from','with','as','by','after','before','is','are','was','were','has','have','had',
    'sri','lanka','says','said','new','latest','report','reports','over','amid','into','about','under','more','its','their','will','not','this','that',
    'his','her','first','today','yesterday','news','update','breaking'
}
CATEGORY_WORDS = {
    'politics': ['president','parliament','minister','cabinet','government','election','mp','politic','ජනාධිපති','පාර්ලිමේන්තු','අමාත්‍ය','ඇමති','රජය','මැතිවරණ','දේශපාලන'],
    'sports': ['cricket','match','test','odi','t20','football','sport','icc','lpl','ක්‍රිකට්','තරග','ක්‍රීඩා','පාපන්දු'],
    'business': ['economy','economic','business','market','cse','stock','rupee','dollar','bank','tax','price','fuel','ආර්ථික','ව්‍යාපාර','වෙළෙඳ','රුපියල්','ඩොලර්','බැංකු','බදු','මිල'],
    'world': ['world','international','us ','usa','india','china','russia','iran','israel','uk ','united nations','ලෝක','ඉන්දියා','චීන','රුසියා','ඉරාන','ඊශ්‍රායල','ඇමරිකා'],
}


def now_iso(): return datetime.now(timezone.utc).isoformat()

def normalize_url(url:str)->str:
    p=urlsplit(url.strip())
    query=urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), query, ''))

def date_iso(entry, key):
    parsed = entry.get(key + '_parsed')
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc).isoformat()
    raw = entry.get(key, '')
    if raw:
        try:
            d=parsedate_to_datetime(raw)
            return (d if d.tzinfo else d.replace(tzinfo=SL)).astimezone(timezone.utc).isoformat()
        except Exception:
            try:
                d=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
                return (d if d.tzinfo else d.replace(tzinfo=SL)).astimezone(timezone.utc).isoformat()
            except Exception: return None
    return None

def clean_title(s):
    s=BeautifulSoup(str(s or ''), 'html.parser').get_text(' ', strip=True)
    return re.sub(r'\s+',' ',s).strip()

def id_for(source,url): return hashlib.sha256((source+'|'+normalize_url(url)).encode()).hexdigest()[:24]

def classify(title):
    t=' '+title.lower()+' '
    for cat, words in CATEGORY_WORDS.items():
        if any(w in t for w in words): return cat
    return 'main'

def token_set(title):
    # Unicode word tokenization works for Sinhala and Latin scripts.
    return {x for x in re.findall(r'[^\W_]+', title.lower(), re.UNICODE) if len(x)>2 and x not in STOP}

def add_article(store, source, title, url, published_at, seen_at, discovery='rss'):
    title=clean_title(title); url=normalize_url(url)
    if not title or len(title)<8 or not url.startswith(('http://','https://')): return False
    uid=id_for(source['name'],url)
    if uid in store:
        store[uid]['last_seen_at']=seen_at
        if published_at and published_at != store[uid].get('published_at'):
            store[uid]['latest_claimed_published_at']=published_at
        return False
    store[uid]={
        'id':uid,'source':source['name'],'source_color':source['color'],'title':title,'url':url,
        'published_at':published_at,'first_seen_at':seen_at,'last_seen_at':seen_at,
        'category':classify(title),'discovery':discovery
    }
    return True

def collect_rss(source, store, seen_at):
    resp=requests.get(source['rss'],headers={'User-Agent':UA},timeout=22)
    resp.raise_for_status(); feed=feedparser.parse(resp.content)
    if not feed.entries: raise ValueError('Feed contains no entries')
    n=0
    for e in feed.entries[:100]:
        title=e.get('title',''); link=e.get('link','')
        pub=date_iso(e,'published') or date_iso(e,'updated')
        n += bool(add_article(store,source,title,link,pub,seen_at,'rss'))
    return n, len(feed.entries)

def discover_feed(homepage_html, base):
    soup=BeautifulSoup(homepage_html,'html.parser')
    for el in soup.select('link[rel~=alternate]'):
        typ=(el.get('type') or '').lower()
        href=el.get('href')
        if href and ('rss' in typ or 'atom' in typ): return urljoin(base,href)
    return None

def likely_article_link(source, href, text):
    if not href or not text: return False
    u=urljoin(source['homepage'],href)
    p=urlsplit(u)
    if p.netloc and urlsplit(source['homepage']).netloc.replace('www.','') not in p.netloc.replace('www.',''): return False
    path=p.path.lower()
    if path in ('','/') or any(x in path for x in ['/contact','/about','/privacy','/terms','/advert','/category/','/tag/','/author/','/video','/photo','/live']): return False
    # Avoid menu labels and tiny anchors. Article headlines are typically descriptive.
    if len(text.strip()) < 18 or len(text.split()) < 3: return False
    # Many publisher article URLs contain digits/date/slug. Accept deep paths as fallback.
    return bool(re.search(r'\d{3,}',path) or path.count('/')>=2 or len(path)>28)

def collect_homepage(source, store, seen_at):
    r=requests.get(source['homepage'],headers={'User-Agent':UA},timeout=22)
    r.raise_for_status(); html=r.text
    # If publisher advertises a feed, use it even when not hard-coded.
    feed=discover_feed(html,source['homepage'])
    if feed:
        temp=dict(source); temp['rss']=feed
        try: return (*collect_rss(temp,store,seen_at), 'auto-rss')
        except Exception: pass
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]; seen=set()
    for a in soup.find_all('a',href=True):
        text=clean_title(a.get_text(' ',strip=True)); href=a.get('href')
        if likely_article_link(source,href,text):
            url=normalize_url(urljoin(source['homepage'],href))
            if url not in seen:
                seen.add(url); candidates.append((text,url))
    n=0
    for title,url in candidates[:80]:
        n += bool(add_article(store,source,title,url,None,seen_at,'homepage'))
    if not candidates: raise ValueError('No article links discovered on homepage')
    return n, len(candidates), 'homepage'

def parse_time(s):
    try: return datetime.fromisoformat(s.replace('Z','+00:00'))
    except Exception: return datetime.min.replace(tzinfo=timezone.utc)

def cluster(rows):
    # Conservative incident grouping: same-language headline overlap within 72h.
    groups=[]
    for row in sorted(rows,key=lambda a:parse_time(a.get('published_at') or a['first_seen_at'])):
        ta=token_set(row['title']); rt=parse_time(row.get('published_at') or row['first_seen_at'])
        best=None; score_best=0
        for g in groups:
            first=g['members'][0]; ft=parse_time(first.get('published_at') or first['first_seen_at'])
            if abs((rt-ft).total_seconds())>72*3600: continue
            tb=g['tokens']; inter=len(ta & tb)
            if not ta or not tb: continue
            score=inter/min(len(ta),len(tb))
            # 2 token overlap is allowed for short Sinhala headlines; 3 otherwise.
            required=2 if min(len(ta),len(tb))<=5 else 3
            if inter>=required and score>=0.62 and score>score_best:
                best=g; score_best=score
        if best: best['members'].append(row); best['tokens'] |= ta
        else: groups.append({'members':[row],'tokens':set(ta)})
    stories=[]
    for g in groups:
        ms=sorted(g['members'],key=lambda a:parse_time(a.get('published_at') or a['first_seen_at']))
        # Earliest publisher-claimed publication when present; otherwise earliest app detection.
        first=min(ms,key=lambda a:parse_time(a.get('published_at') or a['first_seen_at']))
        first_seen=min(ms,key=lambda a:parse_time(a['first_seen_at']))
        stories.append({
            'id':first['id'],'title':first['title'],'article_count':len(ms),
            'first_report':first,'first_detected':first_seen,
            'earliest_at':first.get('published_at') or first['first_seen_at'],
            'latest_at':max((a.get('published_at') or a['first_seen_at']) for a in ms),
            'articles':ms
        })
    return sorted(stories,key=lambda s:parse_time(s['latest_at']),reverse=True)

def run():
    seen_at=now_iso()
    old=json.loads(DB.read_text(encoding='utf-8')) if DB.exists() else {}
    store={a['id']:a for a in old.get('articles',[])}
    statuses=[]
    for source in SOURCES:
        try:
            if source.get('rss'):
                new,total=collect_rss(source,store,seen_at); method='rss'
            else:
                new,total,method=collect_homepage(source,store,seen_at)
            statuses.append({'source':source['name'],'status':'ok','method':method,'new_articles':new,'items_seen':total,'checked_at':seen_at})
        except Exception as e:
            statuses.append({'source':source['name'],'status':'error','message':str(e)[:180],'checked_at':seen_at})
    ordered=sorted(store.values(),key=lambda a:parse_time(a.get('published_at') or a['first_seen_at']),reverse=True)
    # Keep history but cap browser payload; 3000 records is plenty for first-report tracking on GitHub Pages.
    ordered=ordered[:3000]
    stories=cluster(ordered)
    out={'updated_at':seen_at,'sources':statuses,'article_count':len(ordered),'articles':ordered,'stories':stories}
    DB.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'articles':len(ordered),'stories':len(stories),'sources':statuses},ensure_ascii=False))
    if not any(s['status']=='ok' for s in statuses): raise SystemExit('All sources failed')

if __name__=='__main__': run()
