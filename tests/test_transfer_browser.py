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
    page.get_by_role('button', name='기존 작업과 합치기', exact=True).click()
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
    page.add_init_script('window.showSaveFilePicker = undefined')
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


def prepare_export(screen, fail_save=False):
    page, state, url = screen
    events = []
    page.add_init_script('window.showSaveFilePicker = undefined')
    def save(r):
        events.append('save')
        r.fulfill(status=400 if fail_save else 200, json={'detail': 'save failed'})
    page.route('**/api/templates/form', save)
    def export(r):
        events.append('export')
        r.fulfill(json={'url': '/api/transfer/download/token', 'filename': 'data.hscan'})
    page.route('**/api/transfer/export', export)
    page.route('**/api/transfer/download/**', lambda r: r.fulfill(body=b'data'))
    page.goto(url + '/transfer.html')
    page.evaluate("sessionStorage.setItem('view:templateDraft:form', JSON.stringify({fields:[], rules:['changed']}))")
    page.locator('#openExport').click()
    page.locator('#exportTemplates input').check()
    return page, state, events


def test_export_saves_draft_before_building_bundle(screen):
    page, state, events = prepare_export(screen)
    page.locator('#runExport').click()
    pw.expect(page.locator('#unsavedDialog')).to_be_visible()
    assert events == []
    page.locator('#saveBeforeExport').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('자료 파일을 만들었습니다')
    assert events == ['save', 'export']
    assert page.evaluate("sessionStorage.getItem('view:templateDraft:form')") is None
    assert not state['errors']


def test_failed_draft_save_blocks_export_and_keeps_draft(screen):
    page, state, events = prepare_export(screen, fail_save=True)
    page.locator('#runExport').click()
    page.locator('#saveBeforeExport').click()
    pw.expect(page.locator('#exportStatus')).to_contain_text('save failed')
    assert events == ['save']
    assert page.evaluate("sessionStorage.getItem('view:templateDraft:form')") is not None


def test_export_cancel_and_skip_do_not_save_draft(screen):
    page, state, events = prepare_export(screen)
    page.locator('#runExport').click()
    page.locator('#cancelUnsaved').click()
    assert events == []
    page.locator('#runExport').click()
    page.locator('#skipSaveExport').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('자료 파일을 만들었습니다')
    assert events == ['export']
    assert page.evaluate("sessionStorage.getItem('view:templateDraft:form')") is not None


def test_export_writes_to_selected_file_and_tooltip_is_accessible(screen):
    page, state, url = screen
    page.add_init_script('''window.savedChunks = []; window.showSaveFilePicker = async options => {
      window.pickerOptions = options;
      return {name:'chosen.hscan', createWritable:async () => new WritableStream({write(chunk){window.savedChunks.push([...chunk])}})};
    }''')
    page.route('**/api/transfer/export', lambda r: r.fulfill(json={'url':'/api/transfer/download/token', 'filename':'data.hscan'}))
    page.route('**/api/transfer/download/**', lambda r: r.fulfill(body=b'bundle'))
    page.goto(url + '/transfer.html')
    page.locator('#openExport').click()
    page.locator('#exportTemplates input').check()
    page.locator('#exportFilename').fill('custom.hscan')
    page.locator('#chooseDestination').click()
    pw.expect(page.locator('#exportDestination')).to_contain_text('chosen.hscan')
    page.locator('#runExport').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('저장했습니다')
    assert page.evaluate('window.pickerOptions.suggestedName') == 'custom.hscan'
    assert page.evaluate('window.savedChunks.flat()') == list(b'bundle')
    assert not state['errors']


def test_review_pending_edit_is_saved_before_export(screen):
    page, state, events = prepare_export(screen)
    page.locator('#cancelExport').click()
    state['jobs'] = [{'id': 'job', 'state': 'done'}]
    page.evaluate("sessionStorage.removeItem('view:templateDraft:form'); sessionStorage.setItem('view:reviewDraft:job:0:f', JSON.stringify({job:'job',page:0,id:'f',value:'edited'}))")
    def save(r):
        assert r.request.post_data_json['value'] == 'edited'
        events.append('review'); r.fulfill(json={})
    page.route('**/api/jobs/job/fields', save)
    page.locator('#openExport').click()
    page.locator('#exportJobs input').check()
    page.locator('#runExport').click()
    page.locator('#saveBeforeExport').click()
    pw.expect(page.locator('#transferStatus')).to_contain_text('자료 파일을 만들었습니다')
    assert events == ['review', 'export']


def test_duplicate_explanation_on_hover_and_keyboard_focus(screen):
    page, state, url = screen
    page.route('**/api/transfer/preview', lambda r: r.fulfill(json=preview()))
    page.goto(url + '/transfer.html')
    page.set_input_files('#importFile', {'name': 'data.hscan', 'mimeType': 'application/octet-stream', 'buffer': b'test'})
    page.locator('#copyDuplicates').hover()
    pw.expect(page.locator('#duplicateHelp')).to_be_visible()
    pw.expect(page.locator('#duplicateHelp')).to_contain_text('새 작업 ID')
    page.locator('#importTitle').hover()
    page.locator('#copyDuplicates').focus()
    pw.expect(page.locator('#duplicateHelp')).to_be_visible()


def test_destination_write_failure_keeps_download_recovery(screen):
    page, state, url = screen
    page.add_init_script('''window.showSaveFilePicker = async () => ({name:'chosen.hscan',
      createWritable:async () => {throw new Error('Permission denied')}})''')
    page.route('**/api/transfer/export', lambda r: r.fulfill(json={'url':'/api/transfer/download/token', 'filename':'data.hscan'}))
    page.route('**/api/transfer/download/**', lambda r: r.fulfill(body=b'bundle'))
    page.goto(url + '/transfer.html')
    page.locator('#openExport').click()
    page.locator('#exportTemplates input').check()
    page.locator('#chooseDestination').click()
    page.locator('#runExport').click()
    pw.expect(page.locator('#exportStatus')).to_contain_text('Permission denied')
    pw.expect(page.locator('#transferStatus')).to_contain_text('저장하지 못했습니다')
    pw.expect(page.locator('#transferResult a')).to_have_attribute('href', '/api/transfer/download/token?filename=chosen.hscan')
    assert not state['errors']
