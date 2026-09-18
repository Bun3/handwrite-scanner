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
            if path == 'intake' and route.request.method == 'POST':
                route.fulfill(json={'token': 'draft', 'files': [{'index': 0, 'name': 'test.pdf', 'pages': 4, 'pdf': True}]}); return
            if path == 'intake/draft/start' and route.request.method == 'POST':
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
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지')
    page.get_by_role('button', name='선택 적용', exact=True).click()
    page.click('#submitJob')
    pw.expect(page.locator('#submitJob')).to_be_disabled()
    pw.expect(page.locator('#jobs')).to_contain_text('업로드 중')
    page.wait_for_function('document.getElementById("uploadStatus").textContent.includes("선택한 페이지")')
    assert len(state['pending']) == 1
    state['jobs'] = [{'id': 'accepted', 'state': 'queued', 'phase': 'preparing', 'template': 'form', 'progress': '문서 준비 대기'}]
    state['pending'].pop().fulfill(json={'id': 'accepted'})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 완료')
    pw.expect(page.locator('#jobs')).to_contain_text('accepted')
    pw.expect(page.locator('#submitJob')).to_be_enabled()
    assert page.locator('#templateChoices input[value="form"]').is_checked()
    assert not state['errors']


def test_upload_failure_keeps_file_and_shows_guidance(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지')
    page.get_by_role('button', name='선택 적용', exact=True).click()
    page.click('#submitJob')
    pw.expect(page.locator('#submitJob')).to_be_disabled()
    page.wait_for_timeout(100)
    state['pending'].pop().fulfill(status=500, json={'error_info': {'message': '저장 공간이 부족합니다.', 'action': '공간을 확보하세요.'}})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 확인 실패')
    pw.expect(page.locator('#notifications')).to_contain_text('공간을 확보하세요')
    assert page.locator('input[type=file]').evaluate('(e) => e.files.length') == 1
    pw.expect(page.locator('#submitJob')).to_be_enabled()
    assert not state['errors']


def test_selected_pages_and_templates_are_submitted(screen):
    page, state, url = screen
    page.route('**/api/templates', lambda r: r.fulfill(json=[{'name': 'a'}, {'name': 'b'}]))
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지')
    page.get_by_role('checkbox', name='1페이지', exact=True).uncheck()
    page.get_by_role('checkbox', name='3페이지', exact=True).uncheck()
    page.locator('#templateChoices input[value="b"]').uncheck()
    assert page.locator('#pagePicker #templateChoices').count() == 1
    page.get_by_role('button', name='선택 적용', exact=True).click()
    page.click('#submitJob')
    page.wait_for_timeout(100)
    assert state['pending'][0].request.post_data_json == {'templates': ['a'], 'pages': [[2, 4]]}
    state['pending'].pop().fulfill(json={'id': 'selected'})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 완료')
    assert not state['errors']


def test_no_pages_selected_cannot_start(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지')
    page.get_by_role('button', name='전체 해제', exact=True).click()
    page.get_by_role('button', name='선택 적용', exact=True).click()
    page.click('#submitJob')
    pw.expect(page.locator('#notifications')).to_contain_text('페이지를 하나 이상')
    assert not state['pending']


def test_page_modal_cancel_apply_and_reopen(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    popup = page.get_by_role('dialog', name='검사할 페이지 선택')
    pw.expect(popup).to_be_visible()
    assert page.locator('#pageSelection .page-choice').count() == 0
    popup.get_by_role('checkbox', name='2페이지', exact=True).uncheck()
    page.keyboard.press('Escape')
    pw.expect(popup).not_to_be_visible()
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지 중 4페이지')
    page.get_by_role('button', name='양식·페이지 선택', exact=True).click()
    pw.expect(popup.get_by_role('checkbox', name='2페이지', exact=True)).to_be_checked()
    popup.get_by_role('checkbox', name='2페이지', exact=True).uncheck()
    popup.get_by_role('button', name='선택 적용', exact=True).click()
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지 중 3페이지')
    page.get_by_role('button', name='양식·페이지 선택', exact=True).click()
    pw.expect(popup.get_by_role('checkbox', name='2페이지', exact=True)).not_to_be_checked()
    assert not state['errors']


def test_large_pdf_scroll_is_bounded_and_density_keeps_selection(screen):
    page, state, url = screen
    requests = []
    page.route('**/api/intake', lambda r: r.fulfill(json={'token': 'big', 'files': [
        {'index': 0, 'name': 'big.pdf', 'pages': 10000, 'pdf': True},
        {'index': 1, 'name': 'second.pdf', 'pages': 3, 'pdf': True}]}))
    def thumbnail(r):
        requests.append(r.request.url)
        r.fulfill(status=503)
    page.route('**/api/intake/*/files/*/pages/*', thumbnail)
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'big.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    popup = page.get_by_role('dialog', name='검사할 페이지 선택')
    pw.expect(popup).to_be_visible()
    popup.get_by_role('checkbox', name='1페이지', exact=True).uncheck()
    page.get_by_label('미리보기 크기').select_option('8')
    page.locator('#pagePickerScroll').evaluate('(el) => el.scrollTop = el.scrollHeight')
    pw.expect(popup.get_by_role('checkbox', name='10000페이지', exact=True)).to_be_visible()
    assert page.locator('.page-choice').count() < 100
    assert len(requests) < 200
    page.get_by_label('입력 파일').select_option('1')
    popup.get_by_role('checkbox', name='3페이지', exact=True).uncheck()
    page.get_by_label('입력 파일').select_option('0')
    page.get_by_label('미리보기 크기').select_option('3')
    pw.expect(popup.get_by_role('checkbox', name='10000페이지', exact=True)).to_be_visible()
    page.locator('#pagePickerScroll').evaluate('(el) => el.scrollTop = 0')
    pw.expect(popup.get_by_role('checkbox', name='1페이지', exact=True)).not_to_be_checked()
    popup.get_by_role('button', name='선택 적용', exact=True).click()
    pw.expect(page.locator('#pageSelection')).to_contain_text('10003페이지 중 10001페이지')
    page.get_by_role('button', name='양식·페이지 선택', exact=True).click()
    assert page.get_by_label('미리보기 크기').input_value() == '3'
    assert not state['errors']


def test_popup_limits_image_requests_and_cleans_up(screen):
    page, state, url = screen
    waiting = []
    page.route('**/api/intake', lambda r: r.fulfill(json={'token': 'slow', 'files': [
        {'index': 0, 'name': 'slow.pdf', 'pages': 1000, 'pdf': True}]}))
    page.route('**/api/intake/*/files/*/pages/*', lambda r: waiting.append(r))
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'slow.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    popup = page.get_by_role('dialog', name='검사할 페이지 선택')
    pw.expect(popup).to_be_visible()
    page.wait_for_timeout(150)
    assert len(waiting) == 4
    page.locator('#pagePickerScroll').evaluate('(el) => el.scrollTop = el.scrollHeight')
    page.wait_for_timeout(150)
    assert len(waiting) == 4  # 이전 요청이 끝나기 전 스크롤로 요청이 폭증하지 않는다.
    assert popup.get_by_label('페이지 범위', exact=True).count() == 0
    assert page.locator('#pickerSize option').all_text_contents() == ['3열', '5열', '8열']
    popup.get_by_role('button', name='취소', exact=True).click()
    pw.expect(popup).not_to_be_visible()
    for route in waiting:
        try: route.abort()
        except pw.Error: pass
    assert page.locator('.page-choice').count() == 0
    assert page.evaluate('document.body.style.overflow') != 'hidden'
    assert not state['errors']


def test_template_selection_cancel_does_not_change_job_settings(screen):
    page, state, url = screen
    page.route('**/api/templates', lambda r: r.fulfill(json=[{'name': 'a'}, {'name': 'b'}]))
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    popup = page.get_by_role('dialog', name='검사할 페이지 선택')
    pw.expect(popup).to_be_visible()
    popup.locator('#templateChoices input[value="b"]').uncheck()
    popup.get_by_role('button', name='취소', exact=True).click()
    page.get_by_role('button', name='양식·페이지 선택', exact=True).click()
    pw.expect(popup.locator('#templateChoices input[value="b"]')).to_be_checked()
    popup.locator('#templateChoices input[value="b"]').uncheck()
    popup.get_by_role('button', name='선택 적용', exact=True).click()
    page.get_by_role('button', name='양식·페이지 선택', exact=True).click()
    pw.expect(popup.locator('#templateChoices input[value="b"]')).not_to_be_checked()
    assert page.locator('#up #templateChoices').count() == 0
    assert not state['errors']


def test_search_survives_review_and_return_to_jobs(screen):
    page, state, url = screen
    searches = []
    def search(route):
        searches.append(route.request.url)
        route.fulfill(json=[{'job': 'found', 'page': 2, 'value': '홍길동', 'label': '성명', 'template': 'form'}])
    page.route('**/api/search?*', search)
    page.route('**/api/jobs/found', lambda r: r.fulfill(json={'status': {'id': 'found'}, 'results': []}))
    page.goto(url)
    page.locator('#sq').fill('홍길동')
    page.locator('#sf button').click()
    pw.expect(page.locator('#sr')).to_contain_text('홍길동')
    page.locator('#sr a').click()
    page.wait_for_url('**/review.html?id=found&page=2')
    page.get_by_role('link', name='작업', exact=True).click()
    pw.expect(page.locator('#sq')).to_have_value('홍길동')
    pw.expect(page.locator('#sr')).to_contain_text('홍길동')
    assert len(searches) == 2  # 복귀 시 최신 결과를 다시 조회한다.
    page.locator('#sq').fill('')
    page.locator('#sf button').click()
    pw.expect(page.locator('#sr')).not_to_be_visible()
    page.reload()
    pw.expect(page.locator('#sq')).to_have_value('')
    pw.expect(page.locator('#sr')).not_to_be_visible()
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
