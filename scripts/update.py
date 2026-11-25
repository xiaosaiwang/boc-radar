import json,re,time
from pathlib import Path
from datetime import datetime,date,timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'
BASE='https://www.boc.cn/sourcedb/srfd6_2024/index.html'
def load(name,default):
 p=DATA/name; return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def save(name,obj):
 p=DATA/name; tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); tmp.replace(p)
def number(s):
 try:return float(s.replace('%','').replace(',',''))
 except:return None
def parse(html,url):
 soup=BeautifulSoup(html,'html.parser'); out=[]
 for tr in soup.select('tr'):
  c=[x.get_text(' ',strip=True) for x in tr.select('td')]
  if len(c)<8 or not re.fullmatch(r'[A-Za-z0-9]{5,35}',c[0]):continue
  m=re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',c[7]); v=number(c[2]); a=number(c[3])
  if not m or v is None or v<=0:continue
  day=datetime.strptime(m.group().replace('-','/'),'%Y/%m/%d').date().isoformat()
  out.append((c[0],c[1],day,v,a,number(c[6])))
 links={urljoin(url,x.get('href','')) for x in soup.select('a[href]') if re.search(r'(?:^|/)index(?:_\d+)?\.html$',x['href'])}
 return out,{x for x in links if x.startswith(BASE.rsplit('/',1)[0]+'/')}
def metrics(hist):
 h=sorted(hist.items()); last,p=h[-1]; result={'date':last,'nav':p[0],'daily':None,'gap':None,'dd':None,'historyDays':(date.fromisoformat(last)-date.fromisoformat(h[0][0])).days}
 wealth=[1.0]; returns=[]
 for (d0,p0),(d1,p1) in zip(h,h[1:]):
  gap=(date.fromisoformat(d1)-date.fromisoformat(d0)).days
  ret=None if p0[1] is None or p1[1] is None else (p1[0]+((p1[1]-p1[0])-(p0[1]-p0[0])))/p0[0]-1
  wealth.append(wealth[-1]*(1+ret) if ret is not None and ret>-1 and wealth[-1] is not None else None)
  returns.append((gap,ret))
 if returns:
  gap,ret=returns[-1]; result['gap']=gap
  if ret is not None and ret>-1 and gap>0:result['daily']=10000*((1+ret)**(1/gap)-1)
 if p[2] is not None:result['publishedDaily']=p[2]*100
 if len(h)>1 and all(w is not None for w in wealth):
  peak=1; dd=0
  for w in wealth:peak=max(peak,w); dd=max(dd,1-w/peak)
  result['dd']=dd*100
  for n in (7,30,90,180,365):
   for i in range(len(h)-2,-1,-1):
    span=(date.fromisoformat(last)-date.fromisoformat(h[i][0])).days
    if span>=n:
     if span<=n+3:
      ratio=wealth[-1]/wealth[i]; result['avg'+str(n)]=10000*(ratio-1)/span; result['annual'+str(n)]=100*(ratio-1)*365/span
     break
 return result
def main():
 history=load('history.json',{}); meta=load('metadata.json',{}); names=load('names.json',{}); pending=[BASE]; seen=set(); count=0; errors=[]; session=requests.Session();session.headers['User-Agent']='Mozilla/5.0 (compatible; personal public NAV tracker)'
 while pending and len(seen)<200:
  url=pending.pop(0)
  if url in seen:continue
  seen.add(url)
  try:
   r=session.get(url,timeout=25);r.raise_for_status(); r.encoding=r.apparent_encoding; rows,links=parse(r.text,url)
   if not rows:raise ValueError('未识别净值表')
   for code,name,day,v,a,g in rows:
    names[code]=name; history.setdefault(code,{})[day]=[v,a,g];count+=1
   pending.extend(sorted(links-seen-set(pending)))
  except Exception as e:errors.append(f'{url}: {e}')
  time.sleep(0.5)
 if not count:raise RuntimeError('没有获取数据；保留旧快照。'+str(errors))
 if pending:errors.append('分页达到200页上限')
 products=[]
 for code in sorted(set(history)|set(meta)):
  h=history.get(code,{})
  products.append({'code':code,'name':names.get(code,code),**(metrics(h) if h else {}),**meta.get(code,{})})
 save('history.json',history);save('names.json',names);save('products.json',{'updated':datetime.now(timezone.utc).isoformat(),'source':BASE,'pages':len(seen),'rows':count,'errors':errors,'products':products})
 print(f'Collected {count} rows from {len(seen)} pages; errors: {errors}')
if __name__=='__main__':main()
