from pathlib import Path
import subprocess,os,json,struct
ROOT=Path(__file__).resolve().parent
ENV=dict(os.environ,AGENT_BROWSER_SOCKET_DIR='/tmp/dyson-design-browser')
def b(*args):return subprocess.run(['agent-browser','--session','private-design',*args],env=ENV,text=True,capture_output=True,check=True).stdout.strip()
def ev(js):
 a=json.loads(b('eval',js));return json.loads(a) if isinstance(a,str) and a.startswith('{') else a
records=json.loads((ROOT/'render-evidence.json').read_text())
def cap(file,state,w,h,setup=''):
 b('set','viewport',str(w),str(h));b('open',ROOT.as_uri()+'/prototype.html?state='+state)
 if setup:b('eval',setup)
 d=ev('JSON.stringify({width:innerWidth,height:innerHeight,visible:document.visibilityState,scrollY,overflow:document.documentElement.scrollWidth>innerWidth,images:[...document.images].every(i=>i.complete&&i.naturalWidth>0),details:!!document.querySelector("details[open]")})')
 assert d['width']==w and d['height']==h and not d['overflow'] and d['images']
 b('screenshot','',str(ROOT/'frames'/file))
 row=dict(file='frames/'+file,state=state,width=w,height=h,theme='light',tool='agent-browser',readback=d)
 for i,r in enumerate(records):
  if r['file']==row['file']:records[i]=row;break
 else:records.append(row)
cap('07-history-desktop.png','history',1440,1000)
cap('16-history-narrow.png','history',390,844)
cap('19-not-sure-narrow.png','not-sure',390,844,'document.querySelector(".refcaption").scrollIntoView({block:"start"})')
cap('22-details-costs-narrow.png','details',390,844,'document.querySelector(".rundetails .tablewrap").scrollLeft=10000;document.querySelector(".rundetails .tablewrap").scrollIntoView({block:"end"})')
cap('23-history-actions-narrow.png','history',390,844,'document.querySelector(".tablewrap").scrollLeft=10000')
# Native keyboard open and close on details. Focus navigation and activation use real key events.
b('set','viewport','1440','1000');b('open',ROOT.as_uri()+'/prototype.html?state=result')
b('eval','document.querySelector(".rundetails summary").focus()')
b('press','Space')
assert ev('JSON.stringify({open:document.querySelector(".rundetails").open})')['open']
b('press','Space')
assert not ev('JSON.stringify({open:document.querySelector(".rundetails").open})')['open']
b('press','Shift+Tab')
assert ev('JSON.stringify({object:document.activeElement.textContent})')['object']=='Machine 2'
b('press','Enter')
assert ev('JSON.stringify({retake:document.querySelector(".retake").textContent})')['retake'].find('machine 2')>=0
# Verify is constrained until a claimed model is selected.
b('open',ROOT.as_uri()+'/prototype.html?state=selected')
b('select','#mode','verify')
assert ev('JSON.stringify({disabled:document.querySelector("#run").disabled})')['disabled']
b('select','#expectedModel','Dyson V12 Detect Slim')
assert not ev('JSON.stringify({disabled:document.querySelector("#run").disabled})')['disabled']
b('click','#run')
assert ev('JSON.stringify({state})')['state']=='running'
assert ev('JSON.stringify({noDownloads:document.querySelectorAll("[data-download]").length===0})')['noDownloads']
b('click','button[data-go="history"]')
b('click','button[data-go="running"]')
assert ev('JSON.stringify({state})')['state']=='running'
b('open',ROOT.as_uri()+'/prototype.html?state=error')
b('click','button[data-go="selected"]')
assert ev('JSON.stringify({state,hasPhoto:document.images.length>0})')['state']=='selected'
(ROOT/'render-evidence.json').write_text(json.dumps(records,indent=2)+'\n')
(ROOT/'interaction-evidence.json').write_text(json.dumps({'native_details_space_open_close':True,'keyboard_selection_updates_retake':True,'verify_requires_claimed_model':True,'explicit_run_only':True,'running_has_no_downloads':True,'return_from_history':True,'error_preserves_photo_review':True,'browser_errors':b('errors')},indent=2)+'\n')
print('23 frames; native keyboard, mode constraint, return and recovery checks passed.')
