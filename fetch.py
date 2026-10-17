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
    """Classify a Yahoo Yomiuri listing headline conservatively.

    Specific economic vocabulary is more reliable than generic country names,
    or the substring 政策 (which occurs in 政策金利). Ties remain unclassified.
    """
    title = clean(title)
    features = {
      '政治': (
        (5, r'首相|内閣|国会|衆院|参院|議員|閣僚|官房長官|知事|県議|市議|自民党|立憲民主党|公明党|国民民主党|与党|野党|政治資金|政権|議会|選挙|法案'),
        (2, r'外交|防衛相|厚労相|文科相|農相|閣議|総裁選'),
      ),
      '経済': (
        (6, r'日銀|政策金利|為替|円安|円高|株価|株式市場|日経平均|決算|売上高|営業利益|純利益|最終赤字|最終黒字|半導体|GDP|消費者物価|景気|賃上げ|雇用統計|物価高|企業業績|損害賠償|不正会計|経済成長'),
        (4, r'輸出|輸入|関税|貿易|生産|設備投資|投資|値上げ|値下げ|金融|倒産|企業買収|株主|市場|金利|給与|失業率|賃金'),
        (3, r'トヨタ|日産|ホンダ|ニデック|三菱自|三菱商事|ソニー|パナソニック|ボーイング|銀行|企業|メーカー|新型車|百貨店|小売り'),
      ),
      '国際': (
        (6, r'国連|NATO|米大統領|トランプ|プーチン|ゼレンスキー|ロシア軍|ウクライナ軍|米軍|イスラエル軍|北朝鮮軍|中国軍|ガザ|イラン|国際刑事裁判所|停戦|空爆|ミサイル攻撃'),
        (4, r'ロシア|ウクライナ|イスラエル|北朝鮮|欧州連合|EU|外国政府|中国政府|米政府|外交問題'),
        (1, r'中国|米国|アメリカ|韓国|台湾|海外|フランス|ドイツ|インド|フィリピン|国際'),
      )
    }
    scores = {key: sum(weight for weight,pattern in tests if re.search(pattern,title,re.I)) for key,tests in features.items()}
    ordered = sorted(scores, key=lambda key:scores[key], reverse=True)
    best, second = ordered[:2]
    if scores[best] < 3 or scores[best] - scores[second] < 2:
        return None
    return best

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

def yomiuri_next_page(s, base, visited):
    """Follow only a real, visible Yahoo listing next-page link."""
    for a in s.select('a[href]'):
        label=clean(a.get_text(' ',strip=True))
        if label not in ('次へ','次のページ','次の25件'):
            continue
        url=urllib.parse.urljoin(base,a['href'])
        u=urllib.parse.urlsplit(url)
        if u.scheme=='https' and u.netloc=='news.yahoo.co.jp' and url not in visited:
            return url
    return None

def fetch():
    groups={f'{p}|{c}':[] for p in ('朝日','毎日','読売') for c in ('政治','経済','国際')}
    errors=[]
    for paper in ('朝日','毎日'):
        for category,listing in SOURCES[paper].items():
            try:
                s=soup_of(listing)
                links=list(candidates(s,listing,paper))
                if not links: raise ValueError('一覧ページに取得可能な記事リンクなし（HTML構造変更の可能性）')
            except Exception as exc:
                errors.append({'paper':paper,'category':category,'reason':str(exc)[:250]});continue
            for url,title in links[:32]:
                if len(groups[f'{paper}|{category}'])>=7: break
                try:
                    item=article_data(url,paper,category,title)
                    if item['title']: groups[f'{paper}|{category}'].append(item)
                except Exception as exc:
                    errors.append({'paper':paper,'category':category,'url':url,'reason':str(exc)[:200]})
                time.sleep(.1)

    # Yomiuri comes from a combined Yahoo listing with no reliable topical
    # section. List and classify first, then verify author and article metadata.
    listing=SOURCES['読売']['共通']
    current=listing
    visited=set()
    stats={'pages':0,'listed':0,'classified':{'政治':0,'経済':0,'国際':0},'unclassified':0,'unclassified_examples':[], 'article_failures':{'政治':0,'経済':0,'国際':0}}
    for page in range(4):
        if not current or current in visited: break
        visited.add(current)
        try:
            s=soup_of(current)
            links=list(candidates(s,current,'読売'))
            if not links: raise ValueError('一覧ページに取得可能な記事リンクなし（HTML構造変更の可能性）')
        except Exception as exc:
            errors.append({'paper':'読売','category':'共通','reason':f'{page+1}ページ目：{str(exc)[:200]}'})
            break
        stats['pages']+=1
        stats['listed']+=len(links)
        for url,title in links:
            target=classify_yahoo(title)
            if target is None:
                stats['unclassified']+=1
                if len(stats['unclassified_examples'])<6: stats['unclassified_examples'].append(title[:90])
                continue
            stats['classified'][target]+=1
            if len(groups[f'読売|{target}'])>=7: continue
            try:
                item=article_data(url,'読売',target,title)
                if item['title']: groups[f'読売|{target}'].append(item)
            except Exception as exc:
                stats['article_failures'][target]+=1
                errors.append({'paper':'読売','category':target,'url':url,'reason':str(exc)[:200]})
            time.sleep(.1)
        if all(len(groups[f'読売|{c}'])>=7 for c in ('政治','経済','国際')): break
        current=yomiuri_next_page(s,current,visited)
    for cat in ('政治','経済','国際'):
        if len(groups[f'読売|{cat}'])==0:
            errors.append({'paper':'読売','category':cat,'reason':f"配信一覧{stats['pages']}ページ・全{stats['listed']}候補で{cat}分類{stats['classified'][cat]}件、記事確認失敗{stats['article_failures'][cat]}件、分類保留{stats['unclassified']}件。0件は当該分野のニュースが存在しない証明ではありません。"})
    return {'fetched_at':NOW.isoformat(timespec='minutes'),
            'articles':[a for g in groups.values() for a in g],
            'errors':errors,
            'counts':{k:len(v) for k,v in groups.items()},
            'diagnostics':{'yomiuri':stats},
            'sources':SOURCES,
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
