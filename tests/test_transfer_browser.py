from test_feedback_browser import screen, pw, pytestmark


def preview():
    return {'token': 'staged', 'templates': [{'name': 'form', 'destination': 'form (가져옴 1)', 'same': False, 'selected': True}],
            'jobs': [{'name': 'job', 'total': 4, 'completed': 2, 'model': 'qwen3vl-8b', 'model_installed': True,
                      'legacy_templates': False, 'duplicate': None, 'related': ['original']}], 'model': 'qwen3vl-8b'}


def test_import_previews_before_commit_and_does_not_start_job(screen):
    page, state, url = screen
    posts = []
    page.route('**/api/transfer/preview', lambda r: r.fulfill(json=preview()))
    def commit(r):
        posts.append(r.request.post_data_json)
        r.fulfill(json={'jobs': ['new'], 'templates': ['form (가져옴 1)'], 'skipped': []})
    page.route('**/api/transfer/commit', commit)
    page.goto(url + '/transfer.html')
    page.set_input_files('#importFile', {'name': 'data.hscan', 'mimeType': 'application/octet-stream', 'buffer': b'test'})
    pw.expect(page.locator('#importDialog')).to_be_visible()
    assert posts == []
    pw.expect(page.locator('#importTemplates')).to_contain_text('form (가져옴 1)')
    page.locator('#runImport').click()
    pw.expect(page.locator('#transferResult')).to_contain_text('new')
    assert posts == [{'token': 'staged', 'jobs': [0], 'templates': [0], 'copy_duplicates': False}]
    assert not state['pending'] and not state['errors']


def test_merge_requires_per_page_choice_and_keeps_both_inputs(screen):
    page, state, url = screen
    posts = []
    page.route('**/api/transfer/preview', lambda r: r.fulfill(json=preview()))
    page.route('**/api/transfer/merge-preview', lambda r: r.fulfill(json={'added': [2], 'same': [], 'revision': 'rev', 'conflicts': [
        {'page': 0, 'source_file': 'sample.pdf', 'source_page': 1,
         'local': {'fields': [{'label': 'Name', 'value': '<script>old</script>'}]},
         'incoming': {'fields': [{'label': 'Name', 'value': 'new value'}]}}]}))
    def merge(r):
        posts.append(r.request.post_data_json); r.fulfill(json={'job': 'combined'})
    page.route('**/api/transfer/merge', merge)
    page.goto(url + '/transfer.html')
    page.set_input_files('#importFile', {'name': 'data.hscan', 'mimeType': 'application/octet-stream', 'buffer': b'test'})
    page.get_by_role('button', name='기존 작업과 합치기').click()
    page.locator('#previewMerge').click()
    pw.expect(page.locator('#runMerge')).to_be_enabled()
    page.locator('#runMerge').click()
    pw.expect(page.locator('#mergeSummary')).to_contain_text('사용할 결과를 선택')
    assert posts == []
    assert page.locator('#mergeConflicts script').count() == 0
    page.locator('input[value=incoming]').check()
    page.locator('#runMerge').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('두 원본 작업은 그대로')
    assert posts[0]['choices'] == {'0': 'incoming'}
    assert not state['errors']


def test_export_split_uses_virtual_page_picker_and_correct_zero_based_pages(screen):
    page, state, url = screen
    state['jobs'] = [{'id': 'original', 'state': 'cancelled', 'templates': ['form']}]
    posts = []
    page.route('**/api/transfer/jobs/original/pages', lambda r: r.fulfill(json={'job': 'original', 'pages': [
        {'page': i, 'source_file': 'sample.pdf', 'source_page': i + 1, 'completed': i == 0, 'delegated': False} for i in range(1000)]}))
    def export(r):
        posts.append(r.request.post_data_json); r.fulfill(json={'url': '/api/transfer/download/token', 'filename': 'data.hscan'})
    page.route('**/api/transfer/export', export)
    page.route('**/api/transfer/download/token', lambda r: r.fulfill(body=b'data', headers={'Content-Disposition': 'attachment; filename=data.hscan'}))
    page.goto(url + '/transfer.html')
    page.locator('#openExport').click()
    page.locator('#exportJobs input').check()
    page.locator('#exportMode').select_option('split')
    page.locator('#chooseSplit').click()
    pw.expect(page.locator('#pagePicker')).to_be_visible()
    pw.expect(page.get_by_role('checkbox', name='1페이지', exact=True)).to_be_disabled()
    page.locator('#pickerNone').click()
    page.get_by_role('checkbox', name='2페이지', exact=True).check()
    page.get_by_role('checkbox', name='3페이지', exact=True).check()
    assert page.locator('.page-choice').count() < 100
    pw.expect(page.locator('#templateChoices')).not_to_be_visible()
    page.locator('#pickerApply').click()
    page.locator('#runExport').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('분담 파일을 만들었습니다')
    assert posts == [{'jobs': ['original'], 'templates': [], 'pages': [1, 2]}]
    assert not state['errors']
