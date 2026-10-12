(function () {
  'use strict';

  var DRAFTS = 'decide-dialog-drafts';
  var MARK = '[data-board-trouble]';
  var TOP_BAR = '[data-top-bar]';
  var SETTLE_MS = 300;
  var UNSEEN = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, LINK: 1 };

  var script = document.currentScript;
  var patience =
    Number(script && script.getAttribute('data-patience')) || 10000;
  var troubles = [];
  var waited = false;
  var panel = null;
  var shown = '';
  var pending = null;

  function storage() {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  }

  function savedKeys() {
    var saved = storage();
    var keys = [];
    if (!saved) return keys;
    try {
      for (var at = 0; at < saved.length; at += 1) keys.push(saved.key(at));
    } catch {
      return keys;
    }
    return keys;
  }

  function besidesDrafts() {
    return savedKeys().filter(function (key) {
      return key !== DRAFTS;
    });
  }

  function reload() {
    try {
      window.location.reload();
    } catch {
      return;
    }
  }

  function forgetBesidesDrafts() {
    var saved = storage();
    if (saved) {
      besidesDrafts().forEach(function (key) {
        try {
          saved.removeItem(key);
        } catch {
          return;
        }
      });
    }
    reload();
  }

  function forgetAll() {
    var saved = storage();
    try {
      if (saved) saved.clear();
    } catch {
      reload();
      return;
    }
    reload();
  }

  function showing(element) {
    if (element === panel || UNSEEN[element.tagName]) return false;
    return element.getClientRects().length > 0;
  }

  function blank() {
    var body = document.body;
    if (!body) return true;
    for (var at = 0; at < body.children.length; at += 1) {
      if (showing(body.children[at])) return false;
    }
    return true;
  }

  function marked() {
    if (document.querySelector(TOP_BAR)) return null;
    var trouble = document.querySelector(MARK);
    if (!trouble) return null;
    return trouble.textContent.trim() || 'The board could not load.';
  }

  function reasons() {
    var mark = marked();
    if (mark) return [mark];
    if (troubles.length) return troubles.slice(-3);
    return ['Nothing appeared after ' + patience / 1000 + ' seconds.'];
  }

  function offers() {
    var all = [];
    if (besidesDrafts().length) {
      all.push([
        'Delete everything except saved drafts and reload (might work)',
        forgetBesidesDrafts,
      ]);
    }
    if (savedKeys().length) {
      all.push(['Delete all local storage and reload', forgetAll]);
    }
    return all;
  }

  function line(tag, text) {
    var element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function draw(why, ways) {
    var drawn = JSON.stringify([
      why,
      ways.map(function (way) {
        return way[0];
      }),
    ]);
    if (panel && panel.isConnected && !panel.hidden && drawn === shown) return;
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'board-recovery';
      panel.setAttribute('role', 'alert');
      panel.style.cssText =
        'margin:16px;padding:16px;border:1px solid;border-radius:6px;' +
        'background:Canvas;color:CanvasText;font:14px/1.5 system-ui,sans-serif;';
    }
    shown = drawn;
    panel.replaceChildren(line('strong', 'The board could not start.'));
    why.forEach(function (reason) {
      panel.append(line('p', reason));
    });
    if (ways.length) {
      panel.append(
        line(
          'p',
          'An earlier version of the board may have saved something in this browser that this one cannot read.',
        ),
      );
    }
    ways.forEach(function (way) {
      var button = line('button', way[0]);
      button.type = 'button';
      button.style.cssText = 'display:block;margin-top:8px;font:inherit;';
      button.addEventListener('click', way[1]);
      panel.append(button);
    });
    panel.hidden = false;
    var host = document.body || document.documentElement;
    if (panel.parentNode !== host) host.insertBefore(panel, host.firstChild);
  }

  function hide() {
    if (panel && !panel.hidden) panel.hidden = true;
  }

  function check() {
    pending = null;
    try {
      if (marked() || ((troubles.length || waited) && blank())) {
        draw(reasons(), offers());
      } else {
        hide();
      }
    } catch {
      return;
    }
  }

  function soon() {
    if (pending === null) pending = setTimeout(check, SETTLE_MS);
  }

  function describe(event) {
    var target = event.target;
    if (target && target !== window && (target.src || target.href)) {
      return (
        'Could not load ' +
        (target.getAttribute('src') || target.getAttribute('href'))
      );
    }
    var error = event.error;
    if (error && error.message) return error.message;
    return event.message || 'An error with no message.';
  }

  function noted(why) {
    troubles.push(String(why));
    soon();
  }

  try {
    window.addEventListener(
      'error',
      function (event) {
        try {
          noted(describe(event));
        } catch {
          return;
        }
      },
      true,
    );
    window.addEventListener('unhandledrejection', function (event) {
      try {
        var reason = event.reason;
        noted(reason && reason.message ? reason.message : reason);
      } catch {
        return;
      }
    });
    setTimeout(function () {
      waited = true;
      check();
    }, patience);
    new MutationObserver(soon).observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  } catch {
    return;
  }
})();
