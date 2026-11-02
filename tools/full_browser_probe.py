"""Real browser diagnostic for the preserved full workbench."""
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from browser_check import start

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/evidence/full';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='solsol-full-ui-') as data,sync_playwright() as p:
    process,url=start(data);browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[];failed=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:failed.append(dict(url=r.url,status=r.status)) if r.status>=400 else None)
    ready=False
    try:
        page.goto(url)
        try:
            page.wait_for_function("document.querySelector('#modelBundle') && document.querySelector('#calculate').disabled===false && document.querySelector('#mainMap svg') && !document.querySelector('#notice').textContent.includes('Cannot read')",timeout=25000)
            ready=True
        except Exception:pass
        page.screenshot(path=str(out/'browser-probe.png'),full_page=True)
        report=dict(status='PASS' if ready and not errors else 'FAIL',ready=ready,errors=errors,failed=failed,
            notice=page.locator('#notice').inner_text(),settings=page.locator('#settingsBody').inner_text()[:3000])
        (out/'browser-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True,indent=2))
        if report['status']!='PASS':raise SystemExit(1)
    finally:
        browser.close();process.terminate();process.wait(timeout=10)
