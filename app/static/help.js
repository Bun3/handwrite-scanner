/* 공통 도움말: 동적으로 생성된 화면도 hover, focus, 별도 터치 버튼으로 설명한다. */
(() => {
  const rules = [
    ['#llm', '인식 엔진 상태', '상태 안내\n대기: 인식 시작 시 자동 실행\n준비 중: 모델을 메모리에 불러오는 중\n준비됨: 엔진 응답 정상\n인식 중: 문서를 처리하는 중\n확인 필요: 시작 실패 또는 엔진 응답 이상\n연결 확인 필요: 프로그램 서버에 연결하지 못함\n\n문서 업로드·변환·양식 확인 상태는 작업 목록에서 별도로 확인하세요. 모델 선택과 다운로드는 아래 인식 모델에서 관리합니다.'],
    ['#themeBtn', '화면 테마', '밝은 화면과 어두운 화면을 전환합니다. 선택한 테마는 이 브라우저에 저장됩니다.', false],
    ['#submitJob', '인식 시작', '선택한 양식과 페이지만 검사합니다. 양식과 맞지 않는 문서는 건너뜁니다. 접수 후 문서와 엔진 준비에 시간이 걸릴 수 있습니다.'],
    ['#sq', '문서 검색', '파일 이름이 아니라 인식·검수된 필드 값에서 검색합니다. 결과의 문서 열기로 해당 페이지를 확인할 수 있습니다.'],
    ['#mTpl', '통합 내보내기', '선택한 양식으로 인식된 여러 작업의 결과를 하나의 표로 모읍니다. 문서 한 페이지가 한 행입니다. 원본 작업과 통합 작업을 모두 보관했다면 같은 문서가 중복될 수 있습니다.'],
    ['#mFmt, #expFmt', '표 파일 형식', 'CSV는 스프레드시트에서, Markdown은 문서 편집기에서, 텍스트는 일반 메모장에서 확인하기 편한 형식입니다.'],
    ['#mdl th:nth-child(3)', '최소 RAM', '모델 실행에 필요한 메모리의 기준입니다. 다른 프로그램의 사용량에 따라 여유 메모리가 부족할 수 있습니다. 별표는 이 PC의 RAM 기준 추천이며 인식 정확도 순위가 아닙니다.'],
    ['button[onclick^="mdlSelect("]', '인식 모델 사용', '다음 인식에 사용할 모델을 선택합니다. 기존에 저장된 인식 결과는 바뀌지 않습니다.'],
    ['button[onclick^="mdlDownload("]', '모델 다운로드', '이 PC에 모델 파일을 설치합니다. 인터넷 연결과 모델 크기만큼의 저장 공간이 필요하며, 설치 후 사용 버튼으로 선택합니다.'],
    ['#installUpdate', '프로그램 업데이트', '새 버전을 설치하고 프로그램을 다시 시작합니다. 진행 중인 작업이 있다면 먼저 중단하고 저장 상태를 확인하세요.'],
    ['button[onclick="phoneStart()"]', '폰 촬영 업로드', 'PC와 휴대폰을 같은 Wi-Fi에 연결한 뒤 QR로 접속합니다. 사진 업로드 후 PC에서 인식이 시작됩니다. 휴대폰 화면에서는 PDF 페이지 선택을 하지 않습니다.'],
    ['button[onclick="phoneStop()"]', '폰 업로드 끄기', '휴대폰 업로드 연결을 닫습니다. 이미 접수된 작업은 작업 목록에 남습니다.'],
    ['button[onclick^="cancelJob("]', '작업 중단', '현재 처리 중인 항목을 마친 뒤 중단하므로 즉시 멈추지 않을 수 있습니다. 완료된 페이지는 유지되며 나중에 이어할 수 있습니다.'],
    ['button[onclick^="resumeJob("], #transferResult button', '이어하기', '완료된 페이지와 검수 수정값을 유지하고 미완료 페이지를 처리합니다. 중단 당시 처리 중이던 페이지는 처음부터 다시 인식합니다.'],
    ['button[onclick^="rerunJob("]', '처음부터 재인식', '저장된 원본을 처음부터 다시 검사합니다. 기존 인식 결과와 검수 수정값이 새 결과로 대체됩니다. 남은 페이지만 처리하려면 이어하기를 사용하세요.'],
    ['button[onclick^="delJob("]', '작업 삭제', '이 프로그램에 보관된 해당 작업의 입력 사본, 인식 결과와 생성된 PDF를 삭제합니다. 별도로 보관한 원본 파일은 삭제하지 않습니다.'],
    ['#pickerFile', '입력 파일 선택', '여러 파일 중 현재 미리 볼 파일을 고릅니다. 파일을 바꿔도 다른 파일의 페이지 선택은 유지됩니다.'],
    ['#pickerSize', '미리보기 열 수', '한 줄에 배치할 미리보기 개수입니다. 열 수가 적을수록 크게 보이며 화면이 좁으면 실제 열 수가 줄어들 수 있습니다. 검사 범위에는 영향을 주지 않습니다.'],
    ['#pickerAll', '현재 파일 전체 선택', '현재 보고 있는 파일에서 선택 가능한 페이지를 모두 고릅니다. 다른 파일의 선택은 바뀌지 않습니다. 분담 시 완료됐거나 이미 맡긴 페이지는 제외됩니다.'],
    ['#pickerNone', '현재 파일 전체 해제', '현재 보고 있는 파일의 선택만 해제합니다. 다른 파일에서 고른 페이지는 그대로 유지됩니다.'],
    ['#pickerApply', '페이지 선택 적용', '팝업에서 고른 양식과 페이지를 반영합니다. 이 버튼만으로 인식이나 내보내기가 시작되지는 않습니다.'],
    ['#pagePicker .picker-templates legend', '검사할 양식', '여러 양식을 선택하면 각 페이지를 그 양식들과 비교합니다. 일치하는 양식이 없는 페이지는 건너뜁니다.'],
    ['button[onclick="createTpl()"]', '기준 양식 등록', '빈 양식 이미지 또는 PDF를 기준으로 등록합니다. 이후 인식할 영역과 필드 타입을 지정하고 저장하세요.'],
    ['#adBtn', '자동 필드 감지', '기준 양식에서 입력 영역을 찾아 필드 목록을 제안합니다. 기존 필드 목록을 대체하므로 확인창을 표시합니다. 영역·이름·타입을 검토한 뒤 저장하세요.'],
    ['#fields th:nth-child(2)', '필드 이름', '검수 화면과 내보낸 표에 표시할 이름입니다. 검증 규칙에서도 이 이름으로 필드를 참조합니다.'],
    ['#fields th:nth-child(3)', '필드 타입과 빈 값', '자유텍스트·전화번호·숫자·시각 등 내용에 맞는 타입을 선택합니다. 표시 선택은 동그라미·체크 등으로 고른 선택지를 읽습니다. ‘비어있어도 정상’을 켜면 빈칸을 정상으로 취급합니다.'],
    ['#fields th:nth-child(4)', '후보 목록', '가능한 값을 한 줄에 하나씩 입력합니다. 후보목록 타입은 이 목록을 인식·보정에 사용합니다. 표시 선택 타입에는 양식에 인쇄된 선택지를 반드시 입력하세요.'],
    ['#fields th:nth-child(5)', '추가 지시와 범위', '추가 지시는 해당 필드를 읽을 때 참고할 설명입니다. 숫자·시각의 최소·최대 범위는 값 검증에 사용합니다. 입력만으로 정확도가 보장되지는 않습니다.'],
    ['#rules', '검증 규칙', '필드 이름을 사용하는 식을 한 줄에 하나씩 입력합니다. 예: 종료시간 >= 시작시간. ‘라벨 = 식’은 빈 값을 계산해 채우고, 값이 있으면 식과 일치하는지 검사합니다. 저장할 때 규칙 문법도 확인합니다.'],
    ['#discardDraft', '임시 변경 버리기', '이 탭에 임시 보관된 편집을 버리고 마지막으로 저장한 템플릿을 불러옵니다. 저장된 템플릿을 삭제하는 기능은 아닙니다.'],
    ['button[onclick="saveTpl()"]', '템플릿 저장', '편집한 필드와 규칙을 저장합니다. 임시 보관만 된 변경은 인식에 반영되지 않습니다. 기존 작업에 보관된 당시 양식 사본은 바뀌지 않습니다.'],
    ['button[onclick="delTpl()"]', '템플릿 삭제', '등록된 양식과 기준 이미지를 삭제합니다. 삭제 후에는 새 작업에서 선택할 수 없습니다. 작업별 양식 사본이 없는 이전 작업은 이어하기에 영향을 받을 수 있습니다.'],
    ['#fieldFilter', '표시 필드', '화면에서 볼 필드만 좁힙니다. 문서 자체를 제외하지 않습니다. 표 내보내기에도 적용하려면 ‘표시 필드 컬럼만’을 함께 선택하세요.'],
    ['body:not(.transfer-page) #title', '검수 값 저장', '필드 값을 수정하고 다른 곳으로 이동하면 자동으로 저장합니다. 미저장 표시는 아직 반영되지 않은 값이며, 저장 실패 시 수정 내용을 이 탭에 임시 보관합니다. 입력칸에 마우스를 올리면 인식 당시 원문을 볼 수 있습니다.'],
    ['#pageField', '문서 필터', '선택한 필드에 입력값이 포함된 문서만 남깁니다. 대소문자는 구분하지 않습니다. 표 내보내기의 행에도 적용되지만 PDF와 원본 다운로드에는 적용되지 않습니다.'],
    ['button[onclick="addSortKey()"]', '정렬 우선순위', '정렬할 필드를 여러 개 추가할 수 있습니다. 앞쪽 조건부터 적용하며 ↑·↓로 방향을 바꾸고 손잡이를 끌어 우선순위를 바꿉니다. 화면 정렬은 표 파일의 행 순서를 바꾸지 않습니다.'],
    ['.field-row .conf', '인식 신뢰도', '인식 결과를 검토할 때 참고하는 표시이며 정확도를 보장하는 수치는 아닙니다. 사람이 수정해 저장한 값은 100%로 표시합니다. 미저장은 아직 서버에 반영되지 않은 수정입니다.', false],
    ['button[onclick="pdf(\'searchable\')"], button[onclick="preview(\'searchable\')"]', '검색 가능한 PDF', '원본 이미지 위에 인식된 텍스트층을 넣어 검색·복사가 가능한 PDF를 만듭니다. 원본 글씨 모양은 유지되며 화면의 문서 필터와 표시 필드 설정은 적용되지 않습니다.'],
    ['button[onclick="original()"]', '원본 다운로드', '작업에 보관된 업로드 원본을 내려받습니다. 인식 결과나 검수 수정값을 원본에 덧씌우지 않습니다.'],
    ['#expOnly', '표시 필드 컬럼만', '표시 필드에서 고른 항목만 표의 열로 내보냅니다. 해제하면 모든 필드를 포함합니다. 문서 필터는 이 옵션과 별개로 행을 제한합니다.'],
    ['#openExport', '자료 내보내기', '템플릿과 작업을 .hscan 파일로 묶어 다른 PC에서 이어할 수 있게 합니다. CSV·PDF 결과 파일을 만드는 기능과는 다릅니다.'],
    ['#importFile', '자료 불러오기', '.hscan 파일의 내용을 먼저 확인한 뒤 선택한 자료만 등록합니다. 가져온 작업은 자동으로 인식하지 않으므로 필요한 작업에서 이어하기를 누르세요.'],
    ['#exportMode', '내보내기 방식', '전체 이동은 작업과 보관된 원본을 함께 옮깁니다. 페이지 분담은 한 작업의 미완료 페이지 일부를 맡기는 방식이며 파일을 만들면 해당 페이지를 이 PC에서 건너뜁니다.'],
    ['#chooseSplit', '맡길 페이지 선택', '다른 PC에서 처리할 미완료 페이지를 고릅니다. 이미 완료됐거나 분담한 페이지는 선택할 수 없습니다. 기존 분담을 다시 보내려면 먼저 분담을 해제하세요.'],
    ['#chooseDestination', '저장 위치 선택', '이 브라우저를 사용하는 PC에서 폴더와 파일 이름을 지정합니다. 선택만으로 자료를 저장하지 않으며 파일 만들기를 눌러야 저장됩니다.'],
    ['#exportFilename', '자료 파일 이름', '.hscan 확장자가 없으면 자동으로 붙입니다. 폴더 경로는 넣지 말고 저장 위치 선택에서 지정하세요.'],
    ['#exportJobs .transfer-job > .secondary', '분담 해제', '다른 PC에 맡겨 건너뛰던 페이지를 이 PC에서 다시 처리할 수 있게 합니다. 상대 PC의 작업은 취소되지 않습니다.'],
    ['#importDialog fieldset:first-of-type legend', '템플릿 목록에도 추가', '작업에 필요한 양식은 작업 전용 사본으로 함께 가져옵니다. 여기서 선택하면 새 작업에서도 사용할 수 있도록 템플릿 목록에 추가합니다. 이름이 같고 내용이 다르면 이름을 바꿔 보관합니다.'],
    ['#copyDuplicates', '별도 사본 추가', '같은 자료 파일의 작업을 이미 가져왔다면 기본적으로 중복 작업은 건너뜁니다. 이 옵션을 켜고 해당 작업을 선택하면 새 작업 ID로 사본을 하나 더 만듭니다. 기존 작업과 검수 내용은 덮어쓰거나 합치지 않습니다. 결과를 합치려면 ‘기존 작업과 합치기’를 사용하세요.'],
    ['#importJobs .secondary', '기존 작업과 합치기', '같은 원본 작업에서 나눠 처리한 결과를 합칩니다. 서로 무관한 작업을 묶는 기능은 아닙니다. 같은 페이지의 결과가 다르면 사용할 결과를 직접 고릅니다.'],
    ['#mergeTarget', '병합 기준 작업', '가져온 결과를 어느 작업에 합칠지 선택합니다. 두 원본을 보존하고 새 통합 작업을 만듭니다.'],
    ['#runMerge', '새 통합 작업', '추가 결과와 선택한 충돌 결과로 새 작업을 만듭니다. 두 원본은 그대로 남으므로 이후 통합 내보내기에서 같은 문서가 중복되지 않는지 확인하세요.'],
    ['#skipSaveExport', '저장된 내용만 내보내기', '서버에 마지막으로 저장된 내용으로 파일을 만듭니다. 이 탭의 미저장 편집은 삭제하지 않지만 내보낸 파일에는 반영하지 않습니다.']
  ];
  const attached = new WeakMap();
  const entries = new Set();
  let active = null, timer, frame, count = 0;
  function hide() {
    clearTimeout(timer);
    if (!active) return;
    const {tip, badge} = active;
    if (tip.hidePopover && tip.matches(':popover-open')) tip.hidePopover();
    tip.hidden = true; badge?.setAttribute('aria-expanded', 'false'); active = null;
  }
  function show(entry) {
    clearTimeout(timer);
    if (entry.target.dataset.helpText) {
      entry.tip.textContent = entry.target.dataset.helpText + '\n\n' + entry.text;
      entry.tip.style.whiteSpace = 'pre-line';
    }
    if (active === entry) { position(entry); return; }
    hide(); active = entry;
    const {tip, target, badge} = entry;
    tip.hidden = false;
    if (tip.showPopover) tip.showPopover();
    else (target.closest('dialog') || document.body).append(tip);
    position(entry);
    badge?.setAttribute('aria-expanded', 'true');
  }
  function position({tip, target, badge}) {
    const rect = (badge || target).getBoundingClientRect();
    if (!target.isConnected || rect.bottom < 0 || rect.top > innerHeight) { hide(); return; }
    const bounds = tip.getBoundingClientRect(), gap = 8;
    tip.style.left = Math.max(gap, Math.min(rect.left, innerWidth - bounds.width - gap)) + 'px';
    const top = rect.bottom + gap + bounds.height <= innerHeight ? rect.bottom + gap : rect.top - bounds.height - gap;
    tip.style.top = Math.max(gap, Math.min(top, innerHeight - bounds.height - gap)) + 'px';
  }
  const laterHide = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (active && [active.target, active.badge].includes(document.activeElement)) return;
      hide();
    }, 160);
  };
  function attach(target, label, text, withBadge = true) {
    if (attached.has(target) || target.classList.contains('help-trigger')) return;
    const tip = document.createElement('div');
    tip.id = target.id === 'copyDuplicates' ? 'duplicateHelp' : `help-${++count}`;
    tip.className = 'help-tooltip'; tip.setAttribute('role', 'tooltip'); tip.setAttribute('popover', 'manual');
    if (!tip.showPopover) tip.removeAttribute('popover');
    tip.hidden = true; tip.textContent = text; (target.closest('dialog') || document.body).append(tip);
    const entry = {target, tip, text, badge: null}; attached.set(target, entry); entries.add(entry);
    const described = new Set((target.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    described.add(tip.id); target.setAttribute('aria-describedby', [...described].join(' '));
    // 원문 표시 등 기존 보충 정보는 유지하고 같은 설명의 이중 표시만 피한다.
    if (target.id === 'themeBtn' || target.getAttribute('onclick')?.startsWith('resumeJob(')) target.removeAttribute('title');
    if (withBadge) {
      const badge = document.createElement('button'); entry.badge = badge;
      badge.type = 'button'; badge.className = 'help-trigger'; badge.textContent = 'i';
      badge.setAttribute('aria-label', label + ' 도움말'); badge.setAttribute('aria-describedby', tip.id); badge.setAttribute('aria-expanded', 'false');
      // 체크박스는 설명 버튼을 누를 때 선택되지 않도록 label 밖에 둔다.
      if (target.matches('th, legend, h3')) target.append(badge);
      else if (target.id === 'rules') target.previousElementSibling.append(badge);
      else (target.closest('label') || target).after(badge);
      badge.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); show(entry); });
    } else if (!target.matches('button, input, select, textarea, a')) target.tabIndex = 0;
    for (const node of [target, entry.badge].filter(Boolean)) {
      node.addEventListener('pointerenter', () => { clearTimeout(timer); timer = setTimeout(() => show(entry), 300); });
      node.addEventListener('pointerleave', laterHide);
      node.addEventListener('focus', () => show(entry));
      node.addEventListener('blur', laterHide);
    }
    tip.addEventListener('pointerenter', () => clearTimeout(timer)); tip.addEventListener('pointerleave', laterHide);
  }
  function scan() {
    frame = 0;
    for (const [selector, label, text, badge] of rules) document.querySelectorAll(selector).forEach(target => attach(target, label, text, badge));
    if (active && (!active.target.isConnected || !active.target.getClientRects().length)) hide();
    // 동적 목록이 다시 그려지면 이전 도움말 노드도 정리한다.
    for (const entry of entries) if (!entry.target.isConnected) { entry.tip.remove(); entry.badge?.remove(); entries.delete(entry); }
  }
  new MutationObserver(records => {
    if (active && records.some(r => r.type === 'attributes' && r.target === active.target)) show(active);
    if (records.some(r => [...r.addedNodes, ...r.removedNodes].some(n => n.nodeType === 1 && !n.matches('.help-tooltip, .help-trigger')))) {
      if (!frame) frame = requestAnimationFrame(scan);
    }
  }).observe(document.body, {childList: true, subtree: true, attributes:true, attributeFilter:['data-help-text']});
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && active) { hide(); e.preventDefault(); e.stopImmediatePropagation(); } }, true);
  document.addEventListener('pointerdown', e => { if (active && ![active.target, active.badge, active.tip].some(n => n?.contains(e.target))) hide(); }, true);
  document.addEventListener('click', e => { if (!e.target.closest('.help-trigger, .help-tooltip')) hide(); }, true);
  document.addEventListener('input', hide, true);
  document.addEventListener('close', hide, true);
  const reposition = () => { if (active) position(active); };
  document.addEventListener('scroll', reposition, true); window.addEventListener('resize', reposition);
  scan();
})();
