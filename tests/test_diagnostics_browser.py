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


def test_feedback_empty_guard_category_preview_and_mode_change(screen):
    page, state, url = screen
    previews = []
    def preview(route):
        data = route.request.post_data_json
        previews.append(data)
        route.fulfill(json={'token':'feedback', 'can_send':True, 'report':{
            'kind':data['kind'], 'category':data['category'], 'description':data['description']}})
    page.route('**/api/diagnostics/preview', preview)
    page.goto(url)
    page.get_by_role('button', name='의견 보내기', exact=True).click()
    pw.expect(page.locator('#diagnosticFeedbackInfo')).to_be_visible()
    pw.expect(page.locator('#diagnosticErrorInfo')).not_to_be_visible()
    page.locator('#diagnosticPrepare').click()
    assert not previews
    pw.expect(page.locator('#diagnosticStatus')).to_contain_text('의견을 입력')
    page.locator('#diagnosticDescription').fill('검색 기능을 개선해 주세요')
    page.locator('#diagnosticCategory').select_option('usability')
    page.locator('#diagnosticPrepare').click()
    pw.expect(page.locator('#diagnosticPreview')).to_contain_text('usability')
    assert previews[0]['kind'] == 'feedback'
    page.locator('#diagnosticConsent').check()
    pw.expect(page.locator('#diagnosticSend')).to_be_enabled()
    page.locator('#diagnosticKind').select_option('error')
    pw.expect(page.locator('#diagnosticSend')).to_be_disabled()
    pw.expect(page.locator('#diagnosticCategoryRow')).not_to_be_visible()
    pw.expect(page.locator('#diagnosticErrorInfo')).to_be_visible()
    assert not state['errors']


def test_old_server_cannot_attach_diagnostics_to_feedback(screen):
    page, state, url = screen
    page.route('**/api/diagnostics/preview', lambda r: r.fulfill(json={
        'token':'old', 'can_send':True, 'report':{'system':{'private':'DO_NOT_SEND'}}}))
    page.goto(url)
    page.get_by_role('button', name='의견 보내기', exact=True).click()
    page.locator('#diagnosticDescription').fill('개선해 주세요')
    page.locator('#diagnosticPrepare').click()
    pw.expect(page.locator('#diagnosticStatus')).to_contain_text('업데이트')
    pw.expect(page.locator('#diagnosticSend')).to_be_disabled()
    assert 'DO_NOT_SEND' not in page.locator('#diagnosticPreview').inner_text()
