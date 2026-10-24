// Light for everyone by default (the familiar look of mainstream job and SaaS sites), with a toggle that remembers a visitor's choice of dark.
// Loaded in <head> without defer so the right theme is set before anything paints (no flash).
(function () {
  var KEY = 'so-theme';
  function stored() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function apply(theme) { document.documentElement.setAttribute('data-bs-theme', theme); }
  var saved = stored();
  apply(saved === 'dark' ? 'dark' : 'light');

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
      function label() {
        var dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
        button.setAttribute('aria-pressed', String(dark));
        button.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
      }
      label();
      button.addEventListener('click', function () {
        var next = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
        apply(next);
        try { localStorage.setItem(KEY, next); } catch (e) { /* private mode: the choice just is not remembered */ }
        document.querySelectorAll('[data-theme-toggle]').forEach(function (b) { b.dispatchEvent(new Event('themechange')); });
        label();
      });
      button.addEventListener('themechange', label);
    });
  });
})();
