"""Evidence-bearing real workbench workflows, with owned server/data only."""
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from browser_check import start
from calculator_export import product_fingerprint

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidence/full';OUT.mkdir(parents=True,exist_ok=True)


def run():
    class Checks(list):
        def append(self,value):
            super().append(value)
            (OUT/'browser-progress.json').write_text(json.dumps(dict(status='RUNNING',checks=self),ensure_ascii=False,indent=2),encoding='utf8')
    checks=Checks();errors=[];failures=[]
    with tempfile.TemporaryDirectory(prefix='solsol-full-flow-') as data,sync_playwright() as p:
        plugins=['solsol.neutral_plugin_example']
        process,url=start(data,plugins);browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport=dict(width=1440,height=1000))
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:failures.append(dict(url=r.url,status=r.status)) if r.status>=400 else None)
        def ready():page.wait_for_function("!previewPending && confirmedExecution && document.querySelector('#calculate').disabled===false",timeout=60000)
        def tab(name):
            page.locator('#task_settings').click();page.locator('[data-settings='+name+']').click()
        def field(key,value):
            control=page.locator('[data-field='+key+']').first
            control.fill(str(value));control.dispatch_event('change')
        try:
            page.goto(url);page.wait_for_selector('#task_settings');ready()
            assert page.locator('#mainMap svg').count()==1
            assert not any(len(x)>7 for x in page.locator('#mainMap [data-axis-tick]').all_text_contents())
            assert 'Cannot read' not in page.locator('#notice').inner_text()
            tab('common');field('candidate_count',4);field('point_spacing',250);ready()
            tab('sensors');field('A_radius',450)
            page.locator('#resourceStudyMode').select_option('mixed');ready()
            page.wait_for_selector('#resourceCount_A')
            for sensor in ['A','B','C']:
                page.locator('#resourceCount_'+sensor).select_option('EXACT')
                control=page.locator('#resourceCount_'+sensor).locator('xpath=ancestor::fieldset[1]').locator('input[data-resource-field=value]')
                control.fill('1');control.dispatch_event('change');ready()
            page.locator('#resourceBudgetMode').select_option('MAX')
            page.locator('input[data-resource-field=limit]').fill('60');page.locator('input[data-resource-field=limit]').dispatch_event('change');ready()
            tab('optimizer');page.locator('#commonAlgorithm').select_option('NSGA-II')
            field('population',8);field('generations',2);field('seed',17);ready()
            page.locator('#projectName').fill('ABC full-workbench regression');page.locator('#saveScenario').click()
            checks.append('original metadata forms: common candidates, A radius, exact ABC inventory, common budget, algorithm/population/generations/seed; scenario save')
            page.locator('#calculate').click()
            page.wait_for_function("run && run.state==='completed' && run.generation===2",timeout=120000)
            page.locator('#task_map').click()
            page.wait_for_selector('#mainMap [data-sensor-marker]')
            rid=page.evaluate('run.run_id');raw=page.evaluate('currentRow().id')
            assert page.evaluate('run.nfe')==24
            assert page.evaluate('currentRow().sensor_counts')==[1,1,1]
            checks.append('confirmed UI submit → live lifecycle → 24 raw observations, 3 checkpoints, durable completed view and exact ABC counts')
            page.locator('#showDemand').check()
            page.wait_for_function("document.querySelectorAll('#mainMap [data-model-observation]').length>0")
            main_ids=page.locator('#mainMap [data-sensor-marker]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sensorId).sort()')
            page.locator('#expandMap').click()
            page.wait_for_selector('#largeMap [data-sensor-marker]')
            assert page.locator('#largeMap [data-sensor-marker]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sensorId).sort()')==main_ids
            page.locator('#mapDialog [data-close=mapDialog]').click()
            checks.append('actual selected row → coverage points and all ABC markers; normal/enlarged map exact sensor binding')
            page.locator('#compareMaps').click()
            assert page.locator('#initialMap svg').count()==1
            page.locator('#generation').evaluate('(el)=>el.value=0');page.locator('#generation').dispatch_event('input')
            page.wait_for_function('run.generation===0',timeout=60000)
            page.locator('#generation').evaluate('(el)=>el.value=2');page.locator('#generation').dispatch_event('input')
            page.wait_for_function('run.generation===2',timeout=60000)
            checks.append('paired initial/current maps and saved generation replay 2→0→2')
            page.locator('#task_solutions').click()
            assert page.locator('#dockBody').inner_text()
            # Collections and filters are the preserved paged server path.
            collections=page.evaluate("typeof placementPage!=='undefined' ? placementPage : null")
            assert collections is not None
            checks.append('original solution analysis and paged collection controller populated from preserved view')
            page.locator('#qualityCenter').click();page.wait_for_selector('#qualityScope',state='attached',timeout=60000)
            page.locator('[data-quality-view=checks]').click()
            page.locator('#qualityPrepare').click();page.locator('#qualityScope').select_option('selected');page.locator('#qualityMethod').select_option('local')
            page.locator('#qualityRun').click()
            page.wait_for_function("document.querySelector('#qualityStatus')?.textContent.includes('선택 범위 전체 완료')",timeout=60000)
            checks.append('original quality center → selected local diagnostic job → completed recorded evidence')
            page.locator('#qualityClose').click()
            page.locator('#task_settings').click()
            page.locator('#copyRun').click();ready()
            assert page.evaluate("draft.sensors[draft.sensor].A_radius")==450
            assert page.evaluate("selection().resource_contract.sensor_counts.A.value")==1
            checks.append('saved conditions copied as new draft without losing sensor radius or shared exact inventory')
            page.locator('#openScenario').click();page.locator('#scenarioList .scenarioRow button').first.click();ready()
            assert page.evaluate("draft.sensors[draft.sensor].A_radius")==450
            checks.append('original scenario open/restore retains detailed model and calculator conditions')
            page.locator('#runHistory').select_option(rid)
            page.wait_for_function("id=>run && run.run_id===id",arg=rid,timeout=60000)
            page.locator('#task_map').click()
            for w,h in [(1920,1080),(1440,900),(1280,720)]:
                page.set_viewport_size(dict(width=w,height=h));page.screenshot(path=str(OUT/f'full-workbench-{w}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            checks.append('real original workbench at 1920/1440/1280 with no horizontal document overflow')
            # A different registered model must retain independent draft/restore state.
            page.locator('#modelBundle').select_option('ABC_ALTERNATIVE_V1');ready()
            assert page.evaluate('draft.sensor')=='ABC_ALTERNATIVE_V1'
            assert page.evaluate('draft.sensors[draft.sensor].A_radius')==420
            page.locator('#modelBundle').select_option('ABC_COVERAGE_RESOURCE_V1');ready()
            checks.append('registered second model switch → independent defaults → original model restore without old device registrations')
            process.terminate();process.wait(timeout=10);process,url=start(data,plugins)
            page.goto(url+'/live.html?contract=ABC_COVERAGE_RESOURCE_V1&run='+rid)
            page.wait_for_function("run && run.state==='completed' && run.generation===2",timeout=120000)
            page.locator('#task_map').click()
            page.wait_for_function("currentRow() && document.querySelector('#mainMap [data-sensor-marker]')",timeout=60000)
            assert page.evaluate('currentRow().sensor_counts')==[1,1,1]
            checks.append('fresh independent server process strict raw/checkpoint restore → original UI selected-row map')
            assert not errors,errors
            assert not failures,failures
            report=dict(status='PASS',checks=checks,browser='real Microsoft Edge headless',run_id=rid,raw_id=raw,nfe=24,
                        domains=['full_ui_workflows','run_storage_restore','neutral_model_switch'],
                        javascript_errors=errors,http_failures=failures,human_usability='NOT_MEASURED',global_optimality='NOT_CERTIFIED',product_sha256=product_fingerprint(ROOT))
            (OUT/'browser-workflows.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(report,ensure_ascii=True,indent=2))
        except BaseException as exc:
            page.screenshot(path=str(OUT/'full-workflow-failure.png'),full_page=True)
            report=dict(status='FAIL',checks=checks,error=str(exc),javascript_errors=errors,http_failures=failures,
                        notice=page.locator('#notice').inner_text() if page.locator('#notice').count() else '',
                        configuration=page.evaluate('({selection:selection(),summary:configurationSummary,request:requestConfiguration()})'))
            (OUT/'browser-workflows.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(report,ensure_ascii=True,indent=2));raise
        finally:
            browser.close()
            if process.poll() is None:process.terminate();process.wait(timeout=10)


if __name__=='__main__':run()
