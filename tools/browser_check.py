"""Real Edge browser workflow plus fresh-process restoration. No source workspace access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'evidence'
OUT.mkdir(parents=True,exist_ok=True)


def start(data):
    process=subprocess.Popen([sys.executable,'-B','-m','solsol','serve','--port','0','--data-dir',str(data)],
        cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    line=process.stdout.readline().strip()
    if not line.startswith('SOLSOL workspace: '):raise RuntimeError(line+process.stderr.read())
    return process,line.split('SOLSOL workspace: ')[1]


def main():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='solsol-browser-') as data, sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        process,url=start(data)
        page=browser.new_page(viewport=dict(width=1440,height=900));errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(url);page.wait_for_function("document.querySelector('#sensors tbody').children.length===3")
            page.get_by_label('sensors 0 radius',exact=True).fill('260')
            page.locator('#population').fill('12');page.locator('#generations').fill('3')
            page.locator('#prep-budget').fill('16')
            page.locator('#validate').click();page.wait_for_function("document.querySelector('#validation').textContent.includes('확인됨')")
            page.locator('#run').click();page.wait_for_function("document.querySelector('#status').textContent==='계산 · 저장 완료'",timeout=120000)
            page.wait_for_function("document.querySelectorAll('#results tbody tr').length>0")
            page.locator('#results tbody tr').first.click()
            assert '원시' in page.locator('#identity').inner_text()
            map_before=page.locator('#map').inner_html()
            page.locator('#expand').click();assert page.locator('#map-wrap').evaluate("e=>e.classList.contains('expanded')")
            assert page.locator('#map').inner_html()==map_before
            page.locator('#close-map').click();checks.append('normal/enlarged map exact DOM binding')
            page.locator('#show-los').check();checks.append('selected-installation LOS layer')
            page.locator('#checkpoint').select_option('0');assert '세대' in page.locator('#checkpoint option:checked').inner_text()
            page.locator('#checkpoint').select_option('all')
            page.locator('#sort').select_option('coverage');page.locator('#hamming').fill('2');page.locator('#hamming').dispatch_event('change')
            page.locator('#hamming').fill('0');page.locator('#hamming').dispatch_event('change');checks.append('checkpoint, sort and posthoc Hamming selection')
            page.locator('#replay').click();page.wait_for_function("document.querySelector('#verification').textContent.includes('재생 PASS')",timeout=120000)
            checks.append('parameter edit, condition check, MOEA, auto-save, all-row replay')
            with page.expect_download() as dl:page.locator('#download').click()
            dl.value.save_as(Path(data)/'download.json')
            exported=json.loads((Path(data)/'download.json').read_text(encoding='utf-8'))
            assert exported['config']['sensors'][0]['radius']==260
            assert exported['verification']['checked_rows']==len(exported['rows'])
            checks.append('download contains exact confirmed radius and all raw rows')
            page.locator('#copy-config').click();assert page.get_by_label('sensors 0 radius',exact=True).input_value()=='260'
            assert '미리보기' in page.locator('#identity').inner_text()
            page.locator('#restore').click();page.wait_for_function("document.querySelector('#identity').textContent.includes('원시 행')")
            for w,h in [(1920,1080),(1440,900),(1280,720)]:
                page.set_viewport_size(dict(width=w,height=h));page.evaluate('window.scrollTo(0,0);document.querySelector("aside").scrollTop=0')
                page.screenshot(path=str(OUT/f'workspace-{w}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            checks.append('1920/1440/1280 screenshots and no horizontal document overflow')
            process.terminate();process.wait(timeout=10)
            process,url=start(data);page.goto(url)
            page.wait_for_function("document.querySelector('#saved').value!==''")
            page.locator('#restore').click();page.wait_for_function("document.querySelector('#identity').textContent.includes('원시 행')")
            page.locator('#replay').click();page.wait_for_function("document.querySelector('#verification').textContent.includes('재생 PASS')",timeout=120000)
            checks.append('fresh server process: checksum read, browser restore and all-row replay')
            page.locator('#generations').fill('2000');page.locator('#run').click()
            page.wait_for_function("document.querySelector('#stop').disabled===false")
            page.locator('#stop').click();page.wait_for_function("['중지됨','시간 예산 종료'].includes(document.querySelector('#status').textContent)",timeout=120000)
            checks.append('cooperative stop, verified partial result, auto-save')
            assert not errors,errors
            report=dict(status='PASS',browser='Microsoft Edge headless (real browser)',checks=checks,
                javascript_errors=errors,run_id=exported['run_id'],search_rows=len(exported['rows']),
                human_usability='NOT_MEASURED',field_validity='NOT_MEASURED')
            (OUT/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(report,ensure_ascii=True,indent=2))
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
            browser.close()


if __name__=='__main__':main()
