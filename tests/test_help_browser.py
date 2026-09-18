from test_feedback_browser import screen, pw, pytestmark
from test_view_state import setup_documents


def test_job_help_does_not_execute_action_and_escape_dismisses(screen):
    page, state, url = screen
    state['jobs'] = [{'id': 'job', 'state': 'cancelled', 'template': 'form'}]
    page.goto(url)
    badge = page.get_by_role('button', name='처음부터 재인식 도움말', exact=True)
    badge.click()
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('검수 수정값')
    page.keyboard.press('Escape')
    pw.expect(page.locator('[role=tooltip]:visible')).to_have_count(0)
    page.get_by_role('button', name='이어하기', exact=True).focus()
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('완료된 페이지')
    assert not state['errors']


def test_touch_help_does_not_toggle_duplicate_checkbox(screen):
    from test_transfer_browser import preview
    page, state, url = screen
    context = page.context.browser.new_context(viewport={'width': 390, 'height': 740}, has_touch=True, is_mobile=True)
    try:
        touch = context.new_page()
        touch.route('**/api/transfer/preview', lambda r: r.fulfill(json=preview()))
        touch.goto(url + '/transfer.html')
        touch.set_input_files('#importFile', {'name':'data.hscan', 'mimeType':'application/octet-stream', 'buffer':b'test'})
        touch.get_by_role('button', name='별도 사본 추가 도움말', exact=True).tap()
        pw.expect(touch.locator('#duplicateHelp')).to_be_visible()
        pw.expect(touch.locator('#copyDuplicates')).not_to_be_checked()
        touch.locator('#importTitle').tap()
        pw.expect(touch.locator('#duplicateHelp')).not_to_be_visible()
    finally:
        context.close()


def test_modal_help_stays_in_view_and_escape_keeps_dialog_open(screen):
    page, state, url = screen
    page.set_viewport_size({'width': 390, 'height': 740})
    page.goto(url + '/transfer.html')
    page.locator('#openExport').click()
    page.get_by_role('button', name='내보내기 방식 도움말', exact=True).click()
    tip = page.locator('[role=tooltip]:visible')
    pw.expect(tip).to_contain_text('페이지 분담')
    box = tip.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 390
    assert box['y'] >= 0 and box['y'] + box['height'] <= 740
    page.keyboard.press('Escape')
    pw.expect(page.locator('#exportDialog')).to_be_visible()
    pw.expect(tip).to_have_count(0)
    assert not state['errors']


def test_template_and_review_explain_options_without_changing_values(screen):
    page, state, url = screen
    setup_documents(page)
    page.goto(url + '/template.html?name=a')
    page.get_by_role('button', name='후보 목록 도움말', exact=True).click()
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('한 줄에 하나씩')
    page.goto(url + '/review.html?id=found')
    page.get_by_role('button', name='표시 필드 도움말', exact=True).click()
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('문서 자체를 제외하지')
    assert page.locator('#fieldFilter').input_value() == ''
    assert not state['errors']
