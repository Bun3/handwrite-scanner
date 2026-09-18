const el = id => document.getElementById(id);
const request = async (url, body) => (await apiFetch(url, body === undefined ? undefined : {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
})).json();
let exportSelection = null, imported = null, mergeIndex = null, mergePlan = null;
let busy = false;
let destination = null;
const selected = id => [...el(id).querySelectorAll('input:checked')].map(i => i.value);
function textNode(tag, text, className) {
  const node = document.createElement(tag); node.textContent = text;
  if (className) node.className = className;
  return node;
}
function choice(container, value, text, checked = false) {
  const label = document.createElement('label'), input = document.createElement('input');
  input.type = 'checkbox'; input.value = value; input.checked = checked;
  label.append(input, ' ' + text); container.append(label); return label;
}
async function operation(statusId, action) {
  if (busy) return;
  busy = true;
  const buttons = [...document.querySelectorAll('.transfer-dialog button, #openExport')].filter(b => !b.closest('#unsavedDialog'));
  const previous = buttons.map(b => b.disabled); buttons.forEach(b => b.disabled = true);
  try { await action(); }
  catch (error) { el(statusId).textContent = error.message; }
  finally { busy = false; buttons.forEach((b, i) => b.disabled = previous[i]); }
}
for (const id of ['exportDialog', 'importDialog', 'mergeDialog']) {
  el(id).addEventListener('cancel', e => { if (busy) e.preventDefault(); });
}
window.addEventListener('beforeunload', e => { if (busy) { e.preventDefault(); e.returnValue = ''; } });
el('cancelExport').onclick = () => el('exportDialog').close();
el('cancelImport').onclick = () => el('importDialog').close();
el('cancelMerge').onclick = () => el('mergeDialog').close();

el('openExport').onclick = () => operation('transferStatus', async () => {
  const [templates, jobs] = await Promise.all([request('/api/templates'), request('/api/jobs')]);
  exportSelection = null;
  el('exportTemplates').replaceChildren(); el('exportJobs').replaceChildren();
  for (const t of templates) choice(el('exportTemplates'), t.name, t.name);
  for (const j of jobs) {
    const row = document.createElement('div'); row.className = 'transfer-job';
    choice(row, j.id, `${j.id} · ${({done: '완료', cancelled: '중단', error: '오류', running: '진행 중', queued: '대기'})[j.state] || j.state} · ${j.templates?.join(', ') || j.template || '자동 인식'}`);
    if (j.delegated_pages?.length) {
      const release = textNode('button', `분담 해제 (${j.delegated_pages.length}페이지)`, 'secondary');
      release.onclick = () => {
        if (!confirm('외부 결과를 기다리지 않고 이 PC에서 해당 페이지를 처리하도록 바꿀까요?')) return;
        operation('exportStatus', async () => { await request(`/api/transfer/jobs/${encodeURIComponent(j.id)}/release`, {}); release.remove(); el('exportStatus').textContent = '분담을 해제했습니다. 작업 화면에서 이어하기를 누르세요.'; });
      };
      row.append(release);
    }
    el('exportJobs').append(row);
  }
  if (!jobs.length) el('exportJobs').textContent = '등록된 작업이 없습니다.';
  if (!templates.length) el('exportTemplates').textContent = '등록된 템플릿이 없습니다.';
  el('exportMode').value = 'full'; el('splitOptions').hidden = true; el('exportStatus').textContent = '';
  destination = null;
  el('chooseDestination').hidden = !window.showSaveFilePicker;
  el('exportDestination').textContent = window.showSaveFilePicker ? '저장 위치 선택에서 폴더와 파일 이름을 지정하세요.' : '이 브라우저는 저장 위치 선택을 지원하지 않습니다. 브라우저 다운로드 설정에서 ‘저장 위치를 매번 확인’을 켜면 폴더를 선택할 수 있습니다.';
  el('exportDialog').showModal();
});
function exportFilename() {
  let name = el('exportFilename').value.trim();
  if (!name || /[\\/:*?"<>|\x00-\x1f]/.test(name) || /[. ]$/.test(name)) throw new Error('폴더 경로 없이 올바른 파일 이름을 입력하세요.');
  if (!name.toLowerCase().endsWith('.hscan')) name += '.hscan';
  if (name.length > 180) throw new Error('파일 이름은 확장자를 포함해 180자 이내로 입력하세요.');
  return name;
}
el('exportFilename').oninput = () => {
  destination = null;
  if (window.showSaveFilePicker) el('exportDestination').textContent = '파일 이름이 바뀌었습니다. 저장 위치를 다시 선택하세요.';
};
el('chooseDestination').onclick = () => operation('exportStatus', async () => {
  try {
    const handle = await window.showSaveFilePicker({suggestedName: exportFilename(), types: [{description: 'handwrite-scanner 자료', accept: {'application/octet-stream': ['.hscan']}}]});
    destination = handle; el('exportFilename').value = handle.name;
    el('exportDestination').textContent = `${handle.name} · 선택한 폴더에 저장합니다.`;
    el('exportStatus').textContent = '';
  } catch (error) { if (error.name !== 'AbortError') throw error; }
});

function pendingEdits(ids) {
  const edits = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (!key.startsWith('view:templateDraft:') && !key.startsWith('view:reviewDraft:')) continue;
    const value = JSON.parse(sessionStorage.getItem(key));
    if (key.startsWith('view:templateDraft:')) edits.push({key, value, name: key.slice('view:templateDraft:'.length), template: true});
    else if (ids.includes(value.job)) edits.push({key, value, name: `${value.job} · ${value.page + 1}페이지 · ${value.id}`});
  }
  return edits;
}
async function saveBeforeExport(ids) {
  const edits = pendingEdits(ids);
  if (!edits.length) return true;
  el('unsavedItems').replaceChildren(...edits.map(e => textNode('li', `${e.template ? '템플릿: ' : '검수: '}${e.name}`)));
  const answer = await new Promise(resolve => {
    const dialog = el('unsavedDialog');
    dialog.oncancel = e => { e.preventDefault(); dialog.close('cancel'); };
    dialog.onclose = () => resolve(dialog.returnValue);
    el('cancelUnsaved').onclick = () => dialog.close('cancel');
    el('skipSaveExport').onclick = () => dialog.close('skip');
    el('saveBeforeExport').onclick = () => dialog.close('save');
    dialog.showModal();
  });
  if (answer === 'cancel') return false;
  if (answer === 'save') {
    for (const edit of edits) {
      await apiFetch(edit.template ? '/api/templates/' + encodeURIComponent(edit.name) : `/api/jobs/${encodeURIComponent(edit.value.job)}/fields`, {
        method: edit.template ? 'PUT' : 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(edit.value)
      });
      if (sessionStorage.getItem(edit.key) === JSON.stringify(edit.value)) sessionStorage.removeItem(edit.key);
    }
  }
  return true;
}
el('exportMode').onchange = () => { el('splitOptions').hidden = el('exportMode').value !== 'split'; };
el('exportJobs').onchange = () => { exportSelection = null; el('splitSummary').textContent = ''; };

async function stopJobs(ids) {
  let jobs = (await request('/api/jobs')).filter(j => ids.includes(j.id));
  const active = jobs.filter(j => ['running', 'queued'].includes(j.state));
  if (!active.length) return;
  if (!confirm(`진행 중인 ${active.length}개 작업을 중단한 뒤 내보낼까요? 완료된 페이지는 유지됩니다.`)) throw new Error('내보내기를 취소했습니다.');
  for (const j of active) {
    try { await request(`/api/jobs/${encodeURIComponent(j.id)}/cancel`, {}); }
    catch (error) {
      const current = (await request('/api/jobs')).find(x => x.id === j.id);
      if (current && ['running', 'queued'].includes(current.state)) throw error;
    }
  }
  for (let n = 0; n < 300; n++) {
    el('exportStatus').textContent = '현재 인식 중인 항목이 끝나고 작업이 중단되기를 기다리고 있습니다…';
    jobs = (await request('/api/jobs')).filter(j => ids.includes(j.id));
    if (!jobs.some(j => ['running', 'queued'].includes(j.state))) return;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error('작업 중단에 시간이 걸립니다. 작업 화면에서 중단 상태를 확인한 뒤 다시 내보내세요.');
}

el('chooseSplit').onclick = () => operation('exportStatus', async () => {
  const ids = selected('exportJobs');
  if (ids.length !== 1) throw new Error('분담할 작업 하나를 선택하세요.');
  await stopJobs(ids);
  el('exportStatus').textContent = '페이지 미리보기를 준비하고 있습니다…';
  const info = await request(`/api/transfer/jobs/${encodeURIComponent(ids[0])}/pages`, {});
  const disabled = info.pages.filter(p => p.completed || p.delegated).map(p => p.page + 1);
  const available = info.pages.filter(p => !p.completed && !p.delegated).map(p => p.page + 1);
  if (!available.length) throw new Error('분담할 미완료 페이지가 없습니다. 기존 분담을 다시 보내려면 먼저 분담 해제를 누르세요.');
  el('exportStatus').textContent = info.legacy_templates ? '이전 작업이므로 현재 등록된 양식 사본을 포함합니다.' : '완료됐거나 이미 분담한 페이지는 선택할 수 없습니다.';
  pagePicker.open({job: ids[0], files: [{index: 0, name: ids[0], pages: info.pages.length, disabled,
    labels: info.pages.map(p => `${p.source_file} · 원본 ${p.source_page}페이지`)}]},
    [new Set(exportSelection?.pages.map(n => n + 1) || available)], [], [], selection => {
      exportSelection = {job: ids[0], pages: [...selection[0]].map(n => n - 1)};
      el('splitSummary').textContent = `${exportSelection.pages.length}페이지 분담`;
    });
});

el('runExport').onclick = () => operation('exportStatus', async () => {
  const ids = selected('exportJobs'), templates = selected('exportTemplates');
  if (!ids.length && !templates.length) throw new Error('내보낼 자료를 선택하세요.');
  const body = {jobs: ids, templates};
  if (el('exportMode').value === 'split') {
    if (ids.length !== 1 || exportSelection?.job !== ids[0] || !exportSelection.pages.length) throw new Error('맡길 페이지를 먼저 선택하세요.');
    body.pages = exportSelection.pages;
  }
  const filename = exportFilename();
  if (window.showSaveFilePicker && !destination) throw new Error('저장 위치 선택 버튼으로 폴더와 파일 이름을 먼저 지정하세요.');
  if (!await saveBeforeExport(ids)) return;
  await stopJobs(ids);
  el('exportStatus').textContent = '자료 파일을 만들고 있습니다. 원본이 많으면 시간이 걸릴 수 있습니다…';
  const result = await request('/api/transfer/export', body);
  const a = textNode('a', '자료 파일 다시 다운로드'); a.href = result.url + '?filename=' + encodeURIComponent(filename); a.download = filename;
  el('transferResult').replaceChildren(a);
  if (destination) {
    el('exportStatus').textContent = '선택한 파일에 저장하고 있습니다…';
    try {
      const response = await apiFetch(a.href);
      const writable = await destination.createWritable();
      await response.body.pipeTo(writable);
    } catch (error) {
      el('transferStatus').textContent = '자료 파일은 생성됐지만 선택한 위치에 저장하지 못했습니다. 아래 링크로 다시 다운로드하세요.' + (body.pages ? ' 분담한 페이지는 이미 이 PC에서 제외됐으므로 전달하지 않을 경우 분담을 해제하세요.' : '');
      throw error;
    }
  } else a.click();
  el('transferStatus').textContent = body.pages ? '분담 파일을 만들었습니다. 맡긴 페이지는 이 PC에서 건너뜁니다. 전달하지 않았다면 분담 해제로 되돌릴 수 있습니다.' : '자료 파일을 만들었습니다. 다른 PC의 자료 이동 화면에서 불러오세요.';
  if (destination) el('transferStatus').textContent += ` ${destination.name} 파일을 선택한 폴더에 저장했습니다.`;
  el('exportDialog').close();
});

el('importFile').onchange = async () => {
  const file = el('importFile').files[0]; if (!file) return;
  await operation('transferStatus', async () => {
    el('transferStatus').textContent = '자료를 확인하고 있습니다…';
    const body = new FormData(); body.append('file', file);
    imported = await (await apiFetch('/api/transfer/preview', {method: 'POST', body})).json();
    el('importTemplates').replaceChildren(); el('importJobs').replaceChildren();
    imported.templates.forEach((t, i) => choice(el('importTemplates'), i,
      `${t.name} → ${t.same ? '기존 양식 사용' : t.destination}`, t.selected));
    imported.jobs.forEach((j, i) => {
      const row = document.createElement('div'); row.className = 'transfer-job';
      choice(row, i, `${j.name} · 완료 ${j.completed}/${j.total}페이지${j.duplicate ? ' · 이미 가져옴' : ''}`, !j.duplicate);
      row.append(textNode('p', `사용 모델: ${j.model_label || j.model}${j.model_installed ? '' : ' · 이 PC에서 모델 설치 또는 변경 필요'}${j.legacy_templates ? ' · 현재 양식을 포함한 이전 작업' : ''}`, 'hint'));
      if (j.related.length) {
        const button = textNode('button', '기존 작업과 합치기', 'secondary');
        button.onclick = () => openMerge(i); row.append(button);
      }
      el('importJobs').append(row);
    });
    el('copyDuplicates').checked = false; el('importStatus').textContent = ''; el('transferStatus').textContent = '파일 확인이 끝났습니다. 가져올 자료를 선택하세요.';
    el('importDialog').showModal();
  });
  el('importFile').value = '';
};

function showJobs(ids, message) {
  el('transferResult').replaceChildren(); el('transferStatus').textContent = message;
  for (const id of ids) {
    const row = textNode('div', id + ' ');
    const link = textNode('a', '검수 / 결과 확인'); link.href = 'review.html?id=' + encodeURIComponent(id); row.append(link);
    const resume = textNode('button', '이어하기', 'secondary');
    resume.onclick = () => operation('transferStatus', async () => {
      const data = await request('/api/jobs/' + encodeURIComponent(id));
      if (data.status.state === 'done') throw new Error('이미 완료된 작업입니다. 검수 / 결과 확인을 눌러 주세요.');
      const current = await request('/api/models');
      const active = current.models.find(m => m.active)?.id;
      const original = data.status.model;
      const changed = original && active && original !== active;
      if (changed && !confirm(`원래 모델은 ${original}입니다. 현재 모델 ${active}로 남은 페이지를 처리할까요? 모델을 맞추려면 취소하고 작업 화면에서 모델을 선택하세요.`)) return;
      await request(`/api/jobs/${encodeURIComponent(id)}/resume${changed ? '?accept_current_model=true' : ''}`, {});
      el('transferStatus').textContent = '작업을 접수했습니다. 작업 화면에서 진행 상태를 확인하세요.'; resume.remove();
    });
    row.append(' ', resume); el('transferResult').append(row);
  }
}
el('runImport').onclick = () => operation('importStatus', async () => {
  const jobs = selected('importJobs').map(Number), templates = selected('importTemplates').map(Number);
  if (!jobs.length && !templates.length) throw new Error('가져올 자료를 선택하세요.');
  const result = await request('/api/transfer/commit', {token: imported.token, jobs, templates, copy_duplicates: el('copyDuplicates').checked});
  showJobs(result.jobs, `작업 ${result.jobs.length}개 · 양식 ${result.templates.length}개 가져옴${result.skipped.length ? ` · 중복 ${result.skipped.length}개 제외` : ''}`);
  el('importDialog').close();
});

function openMerge(index) {
  mergeIndex = index; mergePlan = null;
  el('mergeTarget').replaceChildren(...imported.jobs[index].related.map(id => new Option(id, id)));
  el('mergeSummary').textContent = ''; el('mergeConflicts').replaceChildren(); el('runMerge').disabled = true;
  el('mergeDialog').showModal();
}
el('mergeTarget').onchange = () => { mergePlan = null; el('runMerge').disabled = true; el('mergeConflicts').replaceChildren(); };
el('previewMerge').onclick = async () => {
  await operation('mergeSummary', async () => {
    mergePlan = null; el('runMerge').disabled = true;
    const result = await request('/api/transfer/merge-preview', {token: imported.token, index: mergeIndex, target: el('mergeTarget').value});
    mergePlan = {...result, target: el('mergeTarget').value};
    el('mergeSummary').textContent = `추가 ${result.added.length}페이지 · 동일 ${result.same.length}페이지 · 충돌 ${result.conflicts.length}페이지${result.model_changed ? ' · 서로 다른 모델로 인식한 결과가 포함됩니다.' : ''}`;
    el('mergeConflicts').replaceChildren();
    for (const conflict of result.conflicts) {
      const group = document.createElement('fieldset');
      group.append(textNode('legend', `${conflict.source_file} · 원본 ${conflict.source_page}페이지`));
      for (const [key, label] of [['local', '기존 결과'], ['incoming', '가져온 결과']]) {
        const wrapper = document.createElement('label'), radio = document.createElement('input');
        radio.type = 'radio'; radio.name = 'conflict-' + conflict.page; radio.value = key;
        wrapper.append(radio, label);
        const page = conflict[key];
        wrapper.append(textNode('pre', page.skipped ? '양식 불일치로 건너뜀' : page.fields.map(f => `${f.label}: ${f.value}`).join('\n') || '빈 결과'));
        group.append(wrapper);
      }
      el('mergeConflicts').append(group);
    }
  });
  el('runMerge').disabled = !mergePlan;
};
el('runMerge').onclick = () => operation('mergeSummary', async () => {
  if (!mergePlan) throw new Error('병합 내용을 먼저 확인하세요.');
  const choices = {};
  for (const conflict of mergePlan.conflicts) {
    const checked = document.querySelector(`input[name="conflict-${conflict.page}"]:checked`);
    if (!checked) throw new Error('충돌하는 페이지마다 사용할 결과를 선택하세요.');
    choices[conflict.page] = checked.value;
  }
  const result = await request('/api/transfer/merge', {token: imported.token, index: mergeIndex, target: mergePlan.target, revision: mergePlan.revision, choices});
  showJobs([result.job], '새 통합 작업을 만들었습니다. 두 원본 작업은 그대로 보존됩니다.');
  el('mergeDialog').close(); el('importDialog').close();
});
