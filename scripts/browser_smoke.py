"""Live local integration check. Uses synthetic clips; votes are automated test inputs.

Pass --meta to make at most one bounded planner run (up to four paid API requests).
"""
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--meta', action='store_true')
args = parser.parse_args()
out = Path('artifacts')
out.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8765/workbench/', wait_until='networkidle')
    def wait_js(expression, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if page.evaluate(expression): return
            page.wait_for_timeout(100)
        raise AssertionError('Timed out: ' + expression)
    wait_js("localStorage.getItem('tunejury-session') !== null")
    sid = page.evaluate("localStorage.getItem('tunejury-session')")
    print('Browser session:',sid,flush=True)
    page.locator('#brief').fill('Compare calm instrumental background music, 10–30 seconds long. Keep varied candidates and prepare the next A/B comparison.')
    page.locator('.advanced-criteria summary').click()
    page.locator('#query').fill('calm instrumental background music')
    page.locator('#min-duration').fill('10')
    page.locator('#max-duration').fill('30')
    page.locator('#demo').click()
    wait_js("document.querySelectorAll('.track').length === 4")
    page.locator('#score').click()
    for _ in range(90):
        state = page.request.get(f'http://127.0.0.1:8765/api/sessions/{sid}').json()
        if state['score_status'] in ('complete','error'): break
        page.wait_for_timeout(2000)
    assert state['score_status']=='complete', state.get('score_error')
    wait_js("document.querySelectorAll('.compare-card').length === 2")
    print('Real TuneJury scores:',[(t['name'],round(t['score'],4)) for t in state['tracks']],flush=True)
    first_audio = page.locator('#comparison audio').first
    first_audio.evaluate('(a)=>a.load()')
    wait_js("document.querySelector('#comparison audio').readyState >= 1")
    assert first_audio.evaluate('(a)=>a.duration') > 0
    page.screenshot(path=str(out/'desktop.png'),full_page=True)
    if args.meta:
        page.locator('#run-agent').click()
        for _ in range(100):
            state = page.request.get(f'http://127.0.0.1:8765/api/sessions/{sid}').json()
            if state['agent_status'] in ('complete','error','limited'):break
            page.wait_for_timeout(2000)
        print('Meta status:',state['agent_status'],'error:',state.get('agent_error'),flush=True)
        print('Meta tools:',[e['message'] for e in state['activity'] if e['kind']=='tool'],flush=True)
        assert state['agent_status'] == 'complete', state.get('agent_error')
        page.wait_for_timeout(2000)
    # This input is explicitly NOT human preference evidence.
    if state['pair']:
        page.locator('#reason').fill('Automated UI smoke-test vote; not human preference evidence.')
        page.locator('[data-vote=a]').click()
        wait_js("!document.querySelector('#reveal').classList.contains('hidden')")
    page.locator('[data-select]').first.click()
    wait_js("document.querySelector('#export').hasAttribute('href')")
    with page.expect_download() as download:
        page.locator('#export').click()
    download.value.save_as(out/'selection-smoke.zip')
    page.evaluate('window.scrollTo(0,0)')
    page.wait_for_timeout(300)
    page.screenshot(path=str(out/'desktop-selected.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    final=page.request.get(f'http://127.0.0.1:8765/api/sessions/{sid}').json()
    status=page.request.get('http://127.0.0.1:8765/api/status').json()
    report={'session_id':sid,'scoring':final['score_status'],'meta':final['agent_status'],
            'meta_error':final['agent_error'],'votes':len(final['votes']),
            'selected':final['selected'],'browser_errors':errors,'budget':status['budget'],
            'data':'synthetic test audio; automated vote, not human validation'}
    (out/'smoke-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
    assert not errors,errors
    browser.close()
