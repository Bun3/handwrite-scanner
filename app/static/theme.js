// 라이트/다크 테마. 저장값 우선, 없으면 OS 설정 따름. head에서 로드해 깜빡임 방지.
(function () {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;
})();

function currentTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
  syncThemeBtn();
}

function syncThemeBtn() {
  const b = document.getElementById('themeBtn');
  if (b) b.textContent = currentTheme() === 'dark' ? '☀' : '☾';
}

document.addEventListener('DOMContentLoaded', syncThemeBtn);
