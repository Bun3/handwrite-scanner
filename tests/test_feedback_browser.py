"""화면 반응 검증: 실제 브라우저, 지연/실패 API 응답, 사용자 데이터 미사용."""
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

import pytest

pw = pytest.importorskip('playwright.sync_api')
EDGE = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
pytestmark = pytest.mark.skipif(not EDGE.exists(), reason='브라우저 테스트용 Edge 미설치')


@pytest.fixture
def screen():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory='app/static'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    with pw.sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
        page = browser.new_page()
        state = {'jobs': [], 'pending': [], 'errors': []}
        page.on('pageerror', lambda error: state['errors'].append(str(error)))
        def api(route):
            path = route.request.url.split('/api/')[-1]
            if path == 'jobs' and route.request.method == 'POST':
                state['pending'].append(route); return
            payload = {'jobs': state['jobs'], 'templates': [{'name': 'form', 'fields': []}],
                       'health': {'llm': False}, 'models': {'ram_gb': 16, 'models': []}, 'update': {}}.get(path, {})
            route.fulfill(json=payload)
        page.route('**/api/**', api)
        yield page, state, f'http://127.0.0.1:{server.server_port}'
        browser.close()
    server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_upload_pending_visible_then_accepted(screen):
    page, state, url = screen
    page.goto(url)
    page.select_option('#tplSel', 'form')
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    page.click('#submitJob')
    pw.expect(page.locator('#submitJob')).to_be_disabled()
    pw.expect(page.locator('#jobs')).to_contain_text('업로드 중')
    page.wait_for_function('document.getElementById("uploadStatus").textContent.includes("파일을 전달")')
    assert len(state['pending']) == 1
    state['jobs'] = [{'id': 'accepted', 'state': 'queued', 'phase': 'preparing', 'template': 'form', 'progress': '문서 준비 대기'}]
    state['pending'].pop().fulfill(json={'id': 'accepted'})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 완료')
    pw.expect(page.locator('#jobs')).to_contain_text('accepted')
    pw.expect(page.locator('#submitJob')).to_be_enabled()
    assert page.locator('#tplSel').input_value() == 'form'
    assert not state['errors']


def test_upload_failure_keeps_file_and_shows_guidance(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    page.click('#submitJob')
    pw.expect(page.locator('#submitJob')).to_be_disabled()
    page.wait_for_timeout(100)
    state['pending'].pop().fulfill(status=500, json={'error_info': {'message': '저장 공간이 부족합니다.', 'action': '공간을 확보하세요.'}})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 확인 실패')
    pw.expect(page.locator('#notifications')).to_contain_text('공간을 확보하세요')
    assert page.locator('input[type=file]').evaluate('(e) => e.files.length') == 1
    pw.expect(page.locator('#submitJob')).to_be_enabled()
    assert not state['errors']


def test_job_error_stays_in_table_and_escapes_details(screen):
    page, state, url = screen
    state['jobs'] = [{'id': 'bad', 'state': 'error', 'error': '<script>bad()</script>',
                      'error_info': {'message': '기준 이미지가 없습니다.', 'action': '기준 양식을 다시 등록하세요.'}}]
    page.goto(url)
    pw.expect(page.locator('#jobs')).to_contain_text('기준 양식을 다시 등록하세요')
    assert page.locator('#jobs script').count() == 0
    page.locator('#jobs summary').click()
    pw.expect(page.locator('#jobs pre')).to_be_visible()
    pw.expect(page.locator('#jobs pre')).to_have_text('<script>bad()</script>')
    assert not state['errors']


def test_missing_template_reference_shows_notification(screen):
    page, state, url = screen
    page.route('**/api/templates/form/reference?*', lambda r: r.fulfill(status=400, json={
        'error_info': {'message': '기준 이미지가 없습니다.', 'action': '기준 양식을 다시 등록하세요.'}}))
    page.goto(url + '/template.html?name=form')
    pw.expect(page.locator('#notifications')).to_contain_text('기준 양식을 다시 등록하세요')
    assert not state['errors']


def test_old_server_405_shows_update_instructions(screen):
    page, state, url = screen
    state['jobs'] = [{'id': 'old', 'state': 'cancelled'}]
    page.route('**/api/jobs/old/resume', lambda r: r.fulfill(status=405, json={'detail': 'Method Not Allowed'}))
    page.goto(url)
    page.get_by_role('button', name='이어하기', exact=True).click()
    pw.expect(page.locator('#notifications')).to_contain_text('화면과 서버 버전이 다를 수 있습니다')
    pw.expect(page.locator('#notifications')).to_contain_text('새 버전 EXE를 실행하세요')
    assert not state['errors']


def test_update_progress_and_expected_disconnect(screen):
    page, state, url = screen
    update = {'current': '1.0.0', 'latest': '2.0.0', 'available': True, 'supported': True,
              'url': 'https://github.com/Bun3/handwrite-scanner/releases', 'progress': {'phase': 'idle'}}
    page.route('**/api/update', lambda r: r.fulfill(json=update))
    def install(r):
        update['progress'] = {'phase': 'downloading', 'percent': 42, 'message': '새 버전을 내려받고 있습니다'}
        r.fulfill(json=update)
    page.route('**/api/update/install', install)
    page.on('dialog', lambda d: d.accept())
    page.goto(url); page.evaluate('updateCheck()')
    page.get_by_role('button', name='지금 업데이트').click()
    pw.expect(page.locator('#updateStatus')).to_contain_text('42%')
    assert page.evaluate("sessionStorage.getItem('updateTarget')") == '2.0.0'
    page.route('**/api/update', lambda r: r.abort())
    page.evaluate('updateCheck()')
    pw.expect(page.locator('#updateStatus')).to_contain_text('재시작 중')
    assert page.locator('#notifications').count() == 0
    assert not state['errors']


def test_source_checkout_keeps_manual_download(screen):
    page, state, url = screen
    page.route('**/api/update', lambda r: r.fulfill(json={
        'available': True, 'latest': '2.0.0', 'supported': False, 'progress': {'phase': 'idle'}}))
    page.goto(url); page.evaluate('updateCheck()')
    pw.expect(page.locator('#installUpdate')).to_be_hidden()
    pw.expect(page.locator('#updateStatus')).to_contain_text('Windows 배포판')
