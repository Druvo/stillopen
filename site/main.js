// Theme toggle, install tabs and copy buttons. No network calls, no cookies; the theme choice stays in this browser (localStorage).
(function () {
  var root = document.documentElement;
  var toggle = document.getElementById("theme-toggle");
  function current() { return root.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  function label() { if (toggle) toggle.textContent = current() === "dark" ? "Light mode" : "Dark mode"; }
  label();
  if (toggle) toggle.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("stillopen-theme", next); } catch (e) { /* private mode: the choice just is not remembered */ }
    label();
  });

  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  function select(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t); });
    t.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      var n = tabs[(i + d + tabs.length) % tabs.length];
      select(n); n.focus();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll("button.copy"), function (b) {
    b.addEventListener("click", function () {
      var code = document.getElementById(b.getAttribute("data-target"));
      var text = code ? code.textContent : "";
      var done = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { b.textContent = "Select and copy"; });
      else b.textContent = "Select and copy";
    });
  });
})();
