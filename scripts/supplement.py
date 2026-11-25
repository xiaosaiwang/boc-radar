"""Public product catalogue and verified issuer NAV pilot. No login or private API."""
import re,json,time
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup
DATA=Path(__file__).resolve().parents[1]/'data'
CAT='https://e.boc.cn/ezcms/if/ifwb.html'
PILOT={'CYQWFZQQQPZ7DA':'https://www.bocwm.cn/html/2/netWorth/8295.html'}
def norm(s):return re.sub(r'\s+','',s)
def num(s):
 try:return float(s.replace(',','').replace('%',''))
 except:return None
def day(s):
 m=re.search(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}',s)
 return datetime.strptime(re.sub(r'[-.]','/',m.group()),'%Y/%m/%d').date().isoformat() if m else None
def catalog_rows(tables):
 out={}
 for table in tables:
  header=table['header']; rows=table['rows']
  if not all(k in header for k in ['产品代码','风险等级','产品销售状态']):continue
  for cells in rows:
   if len(cells)!=len(header):continue
   d=dict(zip(header,cells));code=norm(d.get('产品代码',''))
   if not re.fullmatch(r'[A-Za-z0-9]{4,40}',code):continue
   if d.get('产品类型') not in ('代销理财产品','自有理财产品','理财产品','代销理财'):continue
   risk=norm(d.get('风险等级',''))
   rm={'中低风险':'R2','低风险':'R1','中等风险':'R3','中风险':'R3','中高风险':'R4','高风险':'R5'}
   risk=rm.get(risk,risk if risk in rm.values() else None)
   cur=norm(d.get('币种',''))
   currency={'人民币':'CNY','人民币元':'CNY','CNY':'CNY','美元':'USD','USD':'USD','港币':'HKD','HKD':'HKD','EUR':'EUR','欧元':'EUR'}.get(cur)
   status=norm(d.get('产品销售状态',''))
   status={'在售':'公开在售','待售':'待售','暂停申购':'暂停申购','停止销售':'停止销售','停售':'停止销售','已售罄':'公开标注售罄'}.get(status,status or '未知')
   x={'issuer':d.get('发行机构'),'risk':risk,'currency':currency,'status':status,'termText':d.get('期限'),'offering':d.get('募集类型'),'audience':d.get('销售对象'),'saleStart':d.get('产品销售开始时间'),'saleEnd':d.get('产品销售截止时间'),'benchmark':d.get('业绩比较基准'),'fees':d.get('收费标准（具体请以产品说明书及公告为准）'),'metadataSource':CAT,'metadataChecked':datetime.now(timezone.utc).isoformat()}
   out[code]={k:v for k,v in x.items() if v not in (None,'')}
 return out
def catalogue():
 from playwright.sync_api import sync_playwright
 out={}
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page()
  try:
   page.goto(CAT,wait_until='domcontentloaded',timeout=45000)
   page.wait_for_timeout(7000)
   seen=set()
   for i in range(30):
    tables=page.evaluate("""() => Array.from(document.querySelectorAll('table')).map(t=>({header:Array.from(t.querySelectorAll('thead tr:last-child th')).map(x=>x.innerText.replace(/\\s+/g,'')),rows:Array.from(t.querySelectorAll('tbody tr')).map(r=>Array.from(r.querySelectorAll('td')).map(x=>x.innerText.trim()))}))""")
    signature=json.dumps(tables,ensure_ascii=False)
    if signature in seen:break
    seen.add(signature);out.update(catalog_rows(tables))
    # Standard public pagination controls only.
    nxt=page.locator('button.btn-next:not([disabled]), li.ant-pagination-next:not(.ant-pagination-disabled) button, button[aria-label="Next page"]:not([disabled])').first
    if not nxt.count() or not nxt.is_visible():break
    nxt.click(timeout=5000);page.wait_for_timeout(1500)
  finally:browser.close()
 return out
def issuer_history(session,code,url):
 r=session.get(url,timeout=25);r.raise_for_status();r.encoding=r.apparent_encoding
 soup=BeautifulSoup(r.text,'html.parser')
 body=norm(soup.get_text(' ',strip=True))
 if not re.search(r'产品代码[:：]'+re.escape(code)+r'(?![A-Za-z0-9])',body):raise ValueError('issuer product code not verified')
 out={}
 for table in soup.select('table'):
  header=None
  for tr in table.select('tr'):
   cells=[x.get_text(' ',strip=True) for x in tr.select('td,th')]
   hh=[norm(x) for x in cells]
   if all(k in hh for k in ['净值日期','份额净值','份额累计净值']):
    header=hh;continue
   if not header or len(cells)!=len(header):continue
   d=dict(zip(header,cells));dt=day(d['净值日期']);v=num(d['份额净值']);a=num(d['份额累计净值'])
   if dt and v is not None and v>0 and a is not None and a>0:out[dt]=[v,a,None]
 if not out:raise ValueError('no verified historical NAV rows')
 return out
def supplement(history,meta):
 report={'catalogueMatched':0,'historyRows':0,'errors':[]}
 try:
  matches=catalogue()
  for code,row in matches.items():
   if code in history or code in meta:
    meta.setdefault(code,{}).update(row);report['catalogueMatched']+=1
  if not report['catalogueMatched']:report['errors'].append('Catalogue: no matching public product rows; existing data retained')
 except Exception as e:report['errors'].append('Catalogue: '+str(e)[:250])
 with requests.Session() as s:
  for code,url in PILOT.items():
   try:
    rows=issuer_history(s,code,url)
    h=history.setdefault(code,{})
    for dt,row in rows.items():h.setdefault(dt,row)
    meta.setdefault(code,{})['historySource']=url
    report['historyRows']+=len(rows)
   except Exception as e:report['errors'].append(code+': '+str(e)[:250])
 print('SUPPLEMENT '+json.dumps(report,ensure_ascii=False))
 return report
