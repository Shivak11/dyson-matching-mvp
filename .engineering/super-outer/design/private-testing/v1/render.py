"""Render package-only fixture states with an isolated browser session."""
from pathlib import Path
import subprocess, os, json, struct
ROOT=Path(__file__).resolve().parent
ENV=dict(os.environ,AGENT_BROWSER_SOCKET_DIR='/tmp/dyson-design-browser')
CMD=['agent-browser','--session','private-design']
def browser(*args):
 p=subprocess.run(CMD+list(args),env=ENV,text=True,capture_output=True,check=True)
 return p.stdout.strip()
def evaluate(js):
 out=browser('eval',js)
 value=json.loads(out)
 return json.loads(value) if isinstance(value,str) and value.startswith('{') else value
records=[]
def capture(name,state,width,height,scroll='',setup=''):
 browser('set','viewport',str(width),str(height))
 browser('open',ROOT.as_uri()+'/prototype.html?state='+state)
 if setup: browser('eval',setup)
 if scroll: browser('eval',scroll)
 data=evaluate('JSON.stringify({width:innerWidth,height:innerHeight,visible:document.visibilityState,scrollY,overflow:document.documentElement.scrollWidth>innerWidth,images:[...document.images].every(i=>i.complete&&i.naturalWidth>0),details:!!document.querySelector("details[open]")})')
 assert data['width']==width and data['height']==height,data
 assert data['images'] and not data['overflow'],data
 target=ROOT/'frames'/name
 assert not target.exists(), 'Unexpected frame collision'
 browser('screenshot','',str(target))
 with target.open('rb') as f:
  f.seek(16); dimensions=struct.unpack('>II',f.read(8))
 assert dimensions==(width,height),dimensions
 records.append(dict(file='frames/'+name,state=state,width=width,height=height,theme='light',tool='agent-browser',readback=data))
# Main working result is captured first.
capture('01-result-desktop.png','result',1440,1000)
capture('02-result-guidance-desktop.png','result',1440,1000,'document.querySelector(".retake").scrollIntoView({block:"center"})')
capture('03-details-desktop.png','details',1440,1000,'document.querySelector(".rundetails").scrollIntoView({block:"end"})')
for i,state in enumerate(['empty','running','error','history','selected'],4):
 capture(f'{i:02d}-{state}-desktop.png',state,1440,1000)
capture('09-verify-desktop.png','selected',1440,1000,setup='mode="verify";render();document.querySelector("#expectedModel").value="Dyson V12 Detect Slim";document.querySelector("#expectedModel").dispatchEvent(new Event("change"))')
capture('10-result-narrow.png','result',390,844)
capture('11-result-guidance-narrow.png','result',390,844,'document.querySelector(".retake").scrollIntoView({block:"center"})')
capture('12-details-narrow.png','details',390,844,'document.querySelector(".rundetails").scrollIntoView({block:"start"})')
for i,state in enumerate(['empty','running','error','history','selected'],13):
 capture(f'{i:02d}-{state}-narrow.png',state,390,844)
capture('18-verify-narrow.png','selected',390,844,'document.querySelector(".runcontrols").scrollIntoView({block:"start"})','mode="verify";render()')
capture('19-not-sure-narrow.png','not-sure',390,844,'document.querySelector(".refcaption").scrollIntoView({block:"start"})')
capture('20-outside-desktop.png','outside',1440,1000,'document.querySelector(".retake").scrollIntoView({block:"center"})')
browser('set','media','light','reduced-motion')
capture('21-keyboard-reduced-motion.png','result',1440,1000,'document.querySelector(".rundetails").scrollIntoView({block:"end"})','document.querySelector(".rundetails summary").focus()')
assert evaluate('JSON.stringify({reduced:matchMedia("(prefers-reduced-motion: reduce)").matches})')['reduced']
(ROOT/'render-evidence.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'frames':len(records),'errors':browser('errors')},indent=2))
