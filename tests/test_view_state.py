"""화면 이동 뒤 편집 및 선택 상태를 보존하는 브라우저 회귀 검증."""
import io

from PIL import Image
from test_feedback_browser import screen, pw, pytestmark


def setup_documents(page):
    buffer = io.BytesIO()
    Image.new('RGB', (300, 400), 'white').save(buffer, 'PNG')
    templates = [{'name': n, 'fields': [{'id': 'f1', 'label': 'Name', 'type': 'text',
                  'box': [10, 10, 100, 30], 'candidates': []}], 'rules': []} for n in ['a', 'b']]
    page.route('**/api/templates', lambda r: r.fulfill(json=templates))
    page.route('**/reference?*', lambda r: r.fulfill(body=buffer.getvalue(), content_type='image/png'))
    page.route('**/api/jobs/*/page/*', lambda r: r.fulfill(body=buffer.getvalue(), content_type='image/png'))
    result = {'results': [{'page': i, 'template': 'a', 'fields': [
        {'id': 'f1', 'label': 'Name', 'value': str(i), 'confidence': 1}]} for i in range(20)]}
    page.route('**/api/jobs/found', lambda r: r.fulfill(json=result))
    return templates


def test_template_drafts_survive_switch_navigation_and_save(screen):
    page, state, url = screen
    templates = setup_documents(page)
    def save(route):
        templates[0].update(route.request.post_data_json)
        route.fulfill(json={'ok': True})
    page.route('**/api/templates/a', save)
    page.goto(url + '/template.html')
    page.locator('#tplSel').select_option('a')
    page.wait_for_selector('#editor', state='visible')
    page.locator('#fields input').first.fill('Edited')
    page.locator('#rules').fill('x > 1')
    page.locator('#tplSel').select_option('b')
    pw.expect(page.locator('#fields input').first).to_have_value('Name')
    page.locator('#tplSel').select_option('a')
    pw.expect(page.locator('#fields input').first).to_have_value('Edited')
    pw.expect(page.locator('#rules')).to_have_value('x > 1')
    page.locator('header a[href="/"]').click()
    page.locator('header a[href="template.html"]').click()
    pw.expect(page.locator('#tplSel')).to_have_value('a')
    pw.expect(page.locator('#fields input').first).to_have_value('Edited')
    page.get_by_role('button', name='저장', exact=True).click()
    pw.expect(page.locator('#saved')).to_contain_text('저장됨')
    templates[0]['fields'][0]['label'] = 'Updated elsewhere'
    page.reload()
    pw.expect(page.locator('#fields input').first).to_have_value('Updated elsewhere')
    assert not state['errors']


def test_intake_selection_survives_navigation_and_starts_without_reupload(screen):
    page, state, url = screen
    setup_documents(page)
    draft = {'token': 'draft', 'files': [{'index': 0, 'name': 'test.pdf', 'pages': 4, 'pdf': True}]}
    page.route('**/api/intake/draft', lambda r: r.fulfill(json=draft))
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    page.wait_for_selector('dialog[open]')
    page.locator('#templateChoices input[value=b]').uncheck()
    page.get_by_role('checkbox', name='1페이지', exact=True).uncheck()
    page.locator('#pickerApply').click()
    page.locator('header a[href="template.html"]').click()
    page.locator('header a[href="/"]').click()
    pw.expect(page.locator('#pageSelection')).to_contain_text('4페이지 중 3페이지')
    page.locator('#submitJob').click()
    page.wait_for_function('pendingUpload')
    page.wait_for_timeout(100)
    assert state['pending'][0].request.post_data_json == {'templates': ['a'], 'pages': [[2, 3, 4]]}
    state['pending'].pop().fulfill(json={'id': 'accepted'})
    pw.expect(page.locator('#uploadStatus')).to_contain_text('접수 완료')
    page.reload()
    pw.expect(page.locator('#pageSelection')).to_be_empty()
    assert not state['errors']


def test_template_draft_survives_failed_save_and_can_be_discarded(screen):
    page, state, url = screen
    setup_documents(page)
    page.route('**/api/templates/a', lambda r: r.fulfill(status=500, json={'detail': 'Save failed'}))
    page.goto(url + '/template.html?name=a')
    page.locator('#fields input').first.fill('Unsaved')
    page.get_by_role('button', name='저장', exact=True).click()
    pw.expect(page.locator('#notifications')).to_contain_text('Save failed')
    page.reload()
    pw.expect(page.locator('#fields input').first).to_have_value('Unsaved')
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#discardDraft').click()
    pw.expect(page.locator('#fields input').first).to_have_value('Name')
    pw.expect(page.locator('#discardDraft')).to_be_hidden()
    assert not state['errors']


def test_restored_intake_already_started_is_not_shown_as_new_input(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    page.locator('#pickerApply').click()
    page.route('**/api/intake/draft', lambda r: r.fulfill(json={'token': 'draft', 'job_id': 'accepted'}))
    page.reload()
    pw.expect(page.locator('#uploadStatus')).to_contain_text('accepted')
    pw.expect(page.locator('#pageSelection')).to_be_empty()
    assert page.locator('input[type=file]').evaluate('(e)=>e.required')
    assert not state['errors']


def test_expired_intake_shows_guidance_and_clears_saved_selection(screen):
    page, state, url = screen
    page.goto(url)
    page.set_input_files('input[type=file]', {'name': 'test.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-test'})
    page.locator('#pickerApply').click()
    page.route('**/api/intake/draft', lambda r: r.fulfill(status=400, json={'error_info': {
        'code': 'input_missing', 'message': '임시 입력이 만료되었거나 없습니다.', 'action': '파일을 다시 선택하세요.'}}))
    page.reload()
    pw.expect(page.locator('#notifications')).to_contain_text('만료')
    pw.expect(page.locator('#pageSelection')).to_be_empty()
    pw.expect(page.locator('input[type=file]')).to_be_enabled()
    page.reload()
    assert page.locator('#notifications').count() == 0


def test_review_settings_survive_return_and_are_per_job(screen):
    page, state, url = screen
    setup_documents(page)
    page.goto(url + '/review.html?id=found')
    page.wait_for_function("document.querySelectorAll('.page').length===20")
    page.locator('#fieldFilter').select_option('Name')
    page.locator('#pageField').select_option('Name')
    page.locator('#pageValue').fill('1')
    page.locator('.sk-field').select_option('Name')
    page.locator('#sortKeys button').first.click()
    page.locator('#expFmt').select_option('csv')
    page.locator('#expOnly').check()
    page.locator('header a[href="/"]').click()
    page.goto(url + '/review.html?id=found')
    page.wait_for_function("document.querySelectorAll('.page').length===20")
    pw.expect(page.locator('#fieldFilter')).to_have_value('Name')
    pw.expect(page.locator('#pageField')).to_have_value('Name')
    pw.expect(page.locator('#pageValue')).to_have_value('1')
    pw.expect(page.locator('#expFmt')).to_have_value('csv')
    pw.expect(page.locator('#expOnly')).to_be_checked()
    assert page.evaluate('sortKeys()') == [{'fld': 'Name', 'asc': False}]
    page.goto(url + '/review.html?id=another')
    pw.expect(page.locator('#pageValue')).to_have_value('')
    pw.expect(page.locator('#expFmt')).to_have_value('md')
    assert not state['errors']


def test_search_opens_matched_page_despite_saved_review_filter(screen):
    page, state, url = screen
    setup_documents(page)
    page.goto(url + '/review.html?id=found')
    page.wait_for_function("document.querySelectorAll('.page').length===20")
    page.locator('#pageField').select_option('Name')
    page.locator('#pageValue').fill('no match')
    page.locator('header a[href="/"]').click()
    page.route('**/api/search?*', lambda r: r.fulfill(json=[
        {'job': 'found', 'page': 18, 'value': '18', 'label': 'Name', 'template': 'a'}]))
    page.locator('#sq').fill('18')
    page.locator('#sf button').click()
    page.locator('#sr a').click()
    target = page.locator('.page[data-page="18"] h4')
    pw.expect(target).to_be_in_viewport()
    pw.expect(page.locator('#pageValue')).to_have_value('')
    assert not state['errors']


def test_job_error_details_keep_dom_and_open_state_on_poll(screen):
    page, state, url = screen
    state['jobs'] = [{'id': 'bad', 'state': 'error', 'error': 'details'}, {'id': 'live', 'state': 'running', 'progress': '1/10'}]
    page.goto(url)
    page.locator('#jobs summary').click()
    page.locator('#jobs details').evaluate('(e)=>window.originalDetails=e')
    state['jobs'][1]['progress'] = '2/10'
    page.evaluate('refresh()')
    pw.expect(page.locator('#jobs pre')).to_be_visible()
    assert page.locator('#jobs details').evaluate('(e)=>e===window.originalDetails')
    assert not state['errors']


def test_filter_changed_during_review_load_is_not_overwritten(screen):
    page, state, url = screen
    setup_documents(page)
    waiting = []
    page.route('**/api/jobs/found/page/1', lambda r: waiting.append(r))
    page.goto(url + '/review.html?id=found')
    page.locator('#pageField').select_option('Name')
    page.locator('#pageValue').fill('19')
    page.wait_for_timeout(100)
    waiting.pop().fallback()
    page.wait_for_function('reviewReady')
    pw.expect(page.locator('#pageValue')).to_have_value('19')
    pw.expect(page.locator('.page[data-page="0"] h4')).to_be_hidden()
    pw.expect(page.locator('.page[data-page="19"] h4')).to_be_visible()
    assert not state['errors']
