from test_feedback_browser import screen, pw, pytestmark


def test_report_requires_preview_and_consent_and_retains_download_on_failure(screen):
    page, state, url = screen
    sent = []
    page.route('**/api/diagnostics/preview', lambda r: r.fulfill(json={
        'token': 'draft', 'can_send': True, 'report': {'schema': 1, 'description': r.request.post_data_json['description']}}))
    def submit(route):
        sent.append(route.request.post_data_json)
        route.fulfill(status=503, json={'detail': '보고서를 파일로 저장해 전달해 주세요.'})
    page.route('**/api/diagnostics/submit', submit)
    page.goto(url)
    page.evaluate("notify('실패', {code:'unexpected', technical:'PATIENT SECRET'})")
    page.get_by_role('button', name='이 오류 보고하기', exact=True).click()
    pw.expect(page.locator('#diagnosticSend')).to_be_disabled()
    page.locator('#diagnosticDescription').fill('버튼을 누르면 실패')
    page.get_by_role('button', name='전송 내용 미리보기', exact=True).click()
    pw.expect(page.locator('#diagnosticPreview')).to_contain_text('버튼을 누르면 실패')
    assert 'PATIENT SECRET' not in page.locator('#diagnosticPreview').inner_text()
    page.locator('#diagnosticConsent').check()
    page.locator('#diagnosticSend').click()
    pw.expect(page.locator('#diagnosticStatus')).to_contain_text('파일로 저장')
    assert sent == [{'token': 'draft', 'consent': True}]
    with page.expect_download() as download:
        page.get_by_role('button', name='보고서 파일 저장', exact=True).click()
    assert download.value.suggested_filename.endswith('.json')
    page.locator('#diagnosticDescription').fill('수정')
    pw.expect(page.locator('#diagnosticSend')).to_be_disabled()
    assert not state['errors']


def test_report_offline_fallback_and_keyboard_close(screen):
    page, state, url = screen
    page.route('**/api/diagnostics/preview', lambda r: r.abort())
    page.goto(url)
    page.get_by_role('button', name='오류 보고', exact=True).click()
    page.get_by_role('button', name='전송 내용 미리보기', exact=True).click()
    pw.expect(page.locator('#diagnosticStatus')).to_contain_text('기본 보고서')
    pw.expect(page.locator('#diagnosticSend')).to_be_disabled()
    pw.expect(page.get_by_role('button', name='보고서 파일 저장', exact=True)).to_be_enabled()
    page.keyboard.press('Escape')
    pw.expect(page.locator('#diagnosticDialog')).not_to_be_visible()
