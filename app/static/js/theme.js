// Переключение темы: «Системная» / «Светлая» / «Тёмная».
// Выбор хранится в localStorage («theme»), до отрисовки его применяет
// инлайн-скрипт в base.html. Графики слушают событие «themechange».
(function () {
  var KEY = 'theme';
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function stored() {
    try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
  }

  function effective(choice) {
    if (choice === 'light' || choice === 'dark') return choice;
    return media && media.matches ? 'dark' : 'light';
  }

  function apply(choice) {
    if (choice === 'light' || choice === 'dark') root.setAttribute('data-theme', choice);
    else root.removeAttribute('data-theme');
    try {
      if (choice === 'system') localStorage.removeItem(KEY); else localStorage.setItem(KEY, choice);
    } catch (e) { /* хранилище недоступно — тема действует до перезагрузки */ }
    sync(choice);
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: effective(choice) } }));
  }

  function sync(choice) {
    var eff = effective(choice);
    document.querySelectorAll('[data-theme-choice]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-theme-choice') === choice ? 'true' : 'false');
    });
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.setAttribute('data-effective', eff);
      btn.setAttribute('aria-label', eff === 'dark' ? 'Тема: тёмная. Включить светлую' : 'Тема: светлая. Включить тёмную');
      btn.setAttribute('aria-pressed', eff === 'dark' ? 'true' : 'false');
    });
  }

  // Значение CSS-токена текущей темы — для Chart.js и прочего canvas.
  window.themeToken = function (name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  };

  document.addEventListener('DOMContentLoaded', function () {
    sync(stored());
    document.querySelectorAll('[data-theme-choice]').forEach(function (btn) {
      btn.addEventListener('click', function () { apply(btn.getAttribute('data-theme-choice')); });
    });
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        apply(effective(stored()) === 'dark' ? 'light' : 'dark');
      });
    });
  });

  if (media) {
    var onSystemChange = function () {
      if (stored() !== 'system') return;
      sync('system');
      document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: effective('system') } }));
    };
    if (media.addEventListener) media.addEventListener('change', onSystemChange);
    else if (media.addListener) media.addListener(onSystemChange);
  }
})();
