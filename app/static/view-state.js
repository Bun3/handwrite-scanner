/* 같은 탭 안의 화면 이동에 필요한 상태만 보관한다. */
const viewState = {
  read(key, fallback = null) {
    try { return JSON.parse(sessionStorage.getItem('view:' + key)) ?? fallback; }
    catch { return fallback; }
  },
  write(key, value) {
    try { sessionStorage.setItem('view:' + key, JSON.stringify(value)); return true; }
    catch {
      notify('화면 상태를 임시 보관하지 못했습니다. 저장하거나 인식을 시작하기 전에는 화면을 이동하지 마세요.');
      return false;
    }
  },
  remove(key) { try { sessionStorage.removeItem('view:' + key); } catch {} }
};
