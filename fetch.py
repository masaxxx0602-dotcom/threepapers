#!/usr/bin/env python3
"""Public metadata collector. Never bypasses paywalls or access controls."""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
DATA = BASE / 'docs' / 'data'
JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(JST)
SOURCES = {
 '朝日': {'政治':'https://www.asahi.com/politics/', '経済':'https://www.asahi.com/business/', '国際':'https://www.asahi.com/international/'},
 '毎日': {'政治':'https://mainichi.jp/seiji/', '経済':'https://mainichi.jp/biz/', '国際':'https://mainichi.jp/world/'},
 '読売': {'共通':'https://news.yahoo.co.jp/media/yom'}
}
HEADERS={'User-Agent':'ThreePapersNewsReader/1.0 (public HTML metadata; personal reader)','Accept-Language':'ja,en;q=0.7'}
SEEN = {}

def get(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_000)
        encoding = response.headers.get_content_charset() or 'utf-8'
        return raw.decode(encoding, errors='replace')

def soup_of(url):
    return BeautifulSoup(get(url), 'html.parser')

def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()

def meta(soup, *, name=None, prop=None):
    tag = soup.find('meta', attrs={'name':name}) if name else soup.find('meta', attrs={'property':prop})
    return clean(tag.get('content')) if tag else ''

def flatten(obj):
    if isinstance(obj,list):
        for entry in obj: yield from flatten(entry)
    elif isinstance(obj,dict):
        yield obj
        for key in ('@graph','mainEntity','itemListElement'):
            if key in obj: yield from flatten(obj[key])

def structured(soup):
    found=[]
    for tag in soup.select('script[type="application/ld+json"]'):
        try: found.extend(flatten(json.loads(tag.string or tag.get_text())))
        except (TypeError,ValueError): pass
    return found

def article_data(url,paper,category,listing_title=''):
    if url in SEEN:
        r=dict(SEEN[url]);r['category']=category
        return r
    s=soup_of(url)
    objects=structured(s)
    news=[]
    for obj in objects:
        typ=obj.get('@type',[])
        if isinstance(typ,str): typ=[typ]
        if any(t in ('NewsArticle','Article','ReportageNewsArticle') for t in typ): news.append(obj)
    article=news[0] if news else {}
    title=clean(article.get('headline') or meta(s,prop='og:title') or (s.title.get_text() if s.title else '') or listing_title)
    description=clean(article.get('description') or meta(s,name='description') or meta(s,prop='og:description'))
    published=clean(article.get('datePublished') or meta(s,prop='article:published_time'))
    author=article.get('author',[])
    if isinstance(author,dict): author=[author]
    authors=' '.join(clean(a.get('name') if isinstance(a,dict) else a) for a in author)
    if paper=='読売':
        if '読売新聞オンライン' not in authors:
            # Yahoo publishing metadata may not include an author; do not assert provenance without evidence.
            publisher=article.get('publisher',{})
            publisher_name=clean(publisher.get('name') if isinstance(publisher,dict) else publisher)
            if '読売新聞オンライン' not in publisher_name:
                raise ValueError('Yahoo記事で著者「読売新聞オンライン」を確認できず')
    pay='確認できず'
    if paper=='毎日':
        entitlement=meta(s,name='cXenseParse:mai-entitlement')
        if entitlement=='paid-member': pay='有料'
        elif entitlement in ('free','free-member','non-member'): pay='無料'
    elif paper=='朝日':
        indicator=meta(s,name='article:paywall')
        if indicator in ('true','1'): pay='有料'
        elif indicator in ('false','0'):pay='無料'
    # Do not conclude free from the absence of a paywall marker.
    item={'paper':paper,'category':category,'title':title[:200] or listing_title,
          'url':url,'description':description[:240] or '確認できず',
          'published':published or '確認できず','paid':pay,
          'date_source':'Yahoo配信日時' if paper=='読売' else '記事公開日時'}
    SEEN[url]=item
    return item

def classify_yahoo(title):
    # Conservative topical routing: ambiguous stories are skipped, not miscategorized.
    rules={
      '政治': r'首相|内閣|国会|衆院|参院|選挙|政党|自民|立憲|議員|閣僚|官房長官|与党|野党|総裁|政治資金|政策|外交|防衛相',
      '経済': r'日銀|円相場|為替|株価|東証|企業|決算|景気|物価|賃金|金利|銀行|市場|経済|貿易|関税|半導体|GDP|投資|消費税|雇用',
      '国際': r'米国|アメリカ|中国|台湾|韓国|北朝鮮|ロシア|ウクライナ|イスラエル|ガザ|イラン|欧州|国連|トランプ|海外|国際|NATO|インド|中東|フランス|ドイツ'
    }
    matches=[k for k,p in rules.items() if re.search(p,title,re.I)]
    return matches[0] if len(matches)==1 else None

def candidates(s,url,paper):
    seen=set()
    for a in s.select('a[href]'):
        href=urllib.parse.urljoin(url,a['href']).split('#')[0]
        host=urllib.parse.urlsplit(href).netloc.lower()
        path=urllib.parse.urlsplit(href).path
        if paper=='朝日': ok=host.endswith('asahi.com') and bool(re.search(r'/articles/[A-Z0-9]+',path,re.I))
        elif paper=='毎日': ok=host.endswith('mainichi.jp') and bool(re.search(r'/articles/\d{8}',path))
        else: ok=host=='news.yahoo.co.jp' and bool(re.search(r'/articles/[a-f0-9]{16,}',path))
        if not ok or href in seen:continue
        title=clean(a.get_text(' ',strip=True))
        if len(title)<9: title=clean(a.get('aria-label') or a.get('title'))
        if not title:continue
        seen.add(href)
        yield href,title

def fetch():
    groups={f'{p}|{c}':[] for p in ('朝日','毎日','読売') for c in ('政治','経済','国際')}
    errors=[]
    for paper,urls in SOURCES.items():
        for category,listing in urls.items():
            try:
                s=soup_of(listing)
                links=list(candidates(s,listing,paper))
                if not links: raise ValueError('一覧ページに取得可能な記事リンクなし（HTML構造変更の可能性）')
            except Exception as exc:
                errors.append({'paper':paper,'category':category,'reason':str(exc)[:250]});continue
            for url,title in links[:100 if paper=='読売' else 32]:
                target=category if paper!='読売' else classify_yahoo(title)
                if target is None or len(groups[f'{paper}|{target}'])>=7:continue
                try:
                    item=article_data(url,paper,target,title)
                    if item['title']:
                        groups[f'{paper}|{target}'].append(item)
                except (Exception) as exc:
                    # Individual articles may be inaccessible; preserve partial success.
                    errors.append({'paper':paper,'category':target,'url':url,'reason':str(exc)[:200]})
                time.sleep(.1)
            if paper=='読売':
                # Only traverse an actual visible pagination link, never manufacture a page URL.
                for anchor in s.select('a[href]'):
                    if all(len(groups[f'読売|{c}'])>=7 for c in ('政治','経済','国際')):break
                    label=clean(anchor.get_text(' ',strip=True))
                    if label not in ('次へ','次のページ','2'):continue
                    nexturl=urllib.parse.urljoin(listing,anchor['href'])
                    if urllib.parse.urlsplit(nexturl).netloc!='news.yahoo.co.jp': continue
                    try:
                        s2=soup_of(nexturl)
                        for url,title in list(candidates(s2,nexturl,paper))[:100]:
                            target=classify_yahoo(title)
                            if not target or len(groups[f'読売|{target}'])>=7:continue
                            try: groups[f'読売|{target}'].append(article_data(url,paper,target,title))
                            except Exception as exc: errors.append({'paper':'読売','category':target,'url':url,'reason':str(exc)[:200]})
                        break
                    except Exception as exc:errors.append({'paper':'読売','category':'共通','reason':'次ページ: '+str(exc)[:180]})
    return {'fetched_at':NOW.isoformat(timespec='minutes'),'articles':[a for g in groups.values() for a in g],
            'errors':errors,'counts':{k:len(v) for k,v in groups.items()},'sources':SOURCES,
            'note':'読売の記事リンクと日時はYahooニュース配信版。読売本体の公開日時や有料表示ではありません。'}

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    result=fetch()
    stamp=NOW.strftime('%Y%m%d_%H%M')
    (DATA/'latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    history=DATA/'history';history.mkdir(exist_ok=True)
    (history/f'{stamp}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    index_file=DATA/'index.json'
    index=json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else []
    index=[x for x in index if x.get('file')!=f'history/{stamp}.json']
    index.insert(0,{'file':f'history/{stamp}.json','fetched_at':result['fetched_at'],'count':len(result['articles'])})
    index=index[:100]
    index_file.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'fetched_at':result['fetched_at'],'articles':len(result['articles']),'errors':len(result['errors'])},ensure_ascii=False))
    return 0

if __name__=='__main__':sys.exit(main())
