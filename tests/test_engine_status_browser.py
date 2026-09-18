from test_feedback_browser import screen, pw, pytestmark


def test_engine_status_near_start_has_state_help_and_connection_failure(screen):
    page, state, url = screen
    health = {'llm':False, 'engine':{'state':'loading'}}
    page.route('**/api/health', lambda r: r.fulfill(json=health))
    page.goto(url)
    pw.expect(page.locator('#up #llm')).to_contain_text('준비 중')
    assert page.locator('header #llm').count() == 0
    page.get_by_role('button', name='인식 엔진 상태 도움말', exact=True).click()
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('메모리')
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('대기')
    health.update(llm=True, engine={'state':'ready'})
    page.evaluate('health()')
    pw.expect(page.locator('#llm')).to_contain_text('준비됨')
    page.evaluate("cachedJobs = [{state:'running', phase:'recognizing'}]; health()")
    pw.expect(page.locator('#llm')).to_contain_text('인식 중')
    health.update(llm=False, engine={'state':'error', 'error':{'message':'메모리가 부족합니다.', 'action':'작은 모델을 선택하세요.'}})
    page.evaluate('health()')
    pw.expect(page.locator('#llm')).to_contain_text('확인 필요')
    pw.expect(page.locator('[role=tooltip]:visible')).to_contain_text('작은 모델')
    page.route('**/api/health', lambda r: r.abort())
    page.evaluate('health()')
    pw.expect(page.locator('#llm')).to_contain_text('연결 확인 필요')
    page.set_viewport_size({'width':390,'height':844})
    for control in page.locator('header > button, header > a').all():
        bounds = control.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
    assert not state['errors']
