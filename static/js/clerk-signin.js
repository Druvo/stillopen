/* Sign-in through Clerk: load Clerk's script from the person's own Clerk address, show its form, then trade its session token for our own session. */
(function () {
  var root = document.getElementById("clerk-root");
  if (!root) return;
  var errorBox = document.getElementById("clerk-error");
  function loading() { var n = document.getElementById("clerk-loading"); if (n) n.remove(); }
  function fail(message) {
    loading();
    errorBox.textContent = message;
    errorBox.hidden = false;
  }
  function exchange(clerk) {
    return clerk.session.getToken().then(function (token) {
      return fetch(root.dataset.exchange, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": root.dataset.csrf },
        body: JSON.stringify({ token: token, next: root.dataset.next }),
      });
    }).then(function (r) {
      return r.json().then(function (body) { return { ok: r.ok, body: body }; });
    }).then(function (result) {
      if (result.ok) { window.location.assign(result.body.next); return; }
      fail(result.body.error || "Signing in did not work. Please try again.");
      var out = document.createElement("button");
      out.type = "button";
      out.className = "btn btn-outline-secondary mt-2";
      out.textContent = "Use a different account";
      out.addEventListener("click", function () { clerk.signOut().then(function () { window.location.reload(); }); });
      errorBox.after(out);
    });
  }
  var script = document.createElement("script");
  script.async = true;
  script.crossOrigin = "anonymous";
  script.setAttribute("data-clerk-publishable-key", root.dataset.key);
  script.src = root.dataset.src;
  script.onerror = function () { fail("The sign-in form could not be loaded. Check your connection and reload the page."); };
  script.onload = function () {
    var clerk = window.Clerk;
    clerk.load().then(function () {
      var cleared = root.dataset.signedOut && clerk.session ? clerk.signOut() : Promise.resolve();
      return cleared.then(function () {
        if (clerk.session) return exchange(clerk);
        loading();
        var holder = document.createElement("div");
        root.appendChild(holder);
        var here = window.location.pathname + window.location.search.replace(/[?&]signed_out=1/, "");
        var options = { signInUrl: root.dataset.signinUrl, signUpUrl: root.dataset.signupUrl, fallbackRedirectUrl: here, forceRedirectUrl: here };
        if (root.dataset.mode === "signup") clerk.mountSignUp(holder, options); else clerk.mountSignIn(holder, options);
      });
    }).catch(function () { fail("The sign-in form could not be started. Please reload the page."); });
  };
  document.head.appendChild(script);
})();
