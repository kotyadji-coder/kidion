(function () {
  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").catch(function () {});

  var deferredPrompt = null;
  var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  var isAndroidMobile = /Android.*Mobile/.test(navigator.userAgent);
  var isMobile = isIOS || isAndroidMobile;
  var isStandalone = window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches;

  if (!isMobile || isStandalone || sessionStorage.getItem("pwa_later")) return;

  injectStyles();

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;
    setTimeout(function () { showInstallModal("android"); }, 1800);
  });

  if (isIOS) {
    setTimeout(function () { showInstallModal("ios"); }, 1800);
  }

  function injectStyles() {
    if (document.getElementById("kidion-pwa-styles")) return;
    var style = document.createElement("style");
    style.id = "kidion-pwa-styles";
    style.textContent = [
      ".pwa-overlay{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.4);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:20px;opacity:0;transition:opacity .2s}",
      ".pwa-overlay.is-open{opacity:1}",
      ".pwa-modal{background:#fff;border-radius:20px;padding:32px 24px 24px;max-width:340px;width:100%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.15);transform:translateY(20px);transition:transform .25s;font-family:var(--font,system-ui,sans-serif)}",
      ".pwa-overlay.is-open .pwa-modal{transform:translateY(0)}",
      ".pwa-modal-icon{font-size:48px;margin-bottom:12px}",
      ".pwa-modal-title{font-size:20px;font-weight:700;margin:0 0 8px;color:#1f2937;letter-spacing:-.02em}",
      ".pwa-modal-text{font-size:14px;color:#6b7280;margin:0 0 20px;line-height:1.5}",
      ".pwa-modal-btn{display:block;width:100%;padding:14px;border:0;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit;margin-bottom:8px}",
      ".pwa-modal-btn--primary{background:#7c3aed;color:#fff}",
      ".pwa-modal-btn--ghost{background:transparent;color:#6b7280}",
      ".pwa-modal-steps{text-align:left;margin:0 0 20px;padding:16px;background:#f9fafb;border-radius:12px}",
      ".pwa-modal-step{display:flex;align-items:flex-start;gap:10px;font-size:14px;color:#374151;line-height:1.4;padding:6px 0}",
      ".pwa-modal-step-num{width:22px;height:22px;border-radius:50%;flex:0 0 22px;background:#7c3aed;color:#fff;font-size:12px;font-weight:700;display:grid;place-items:center}"
    ].join("");
    document.head.appendChild(style);
  }

  function showInstallModal(type) {
    if (document.querySelector(".pwa-overlay") || sessionStorage.getItem("pwa_later")) return;

    var overlay = document.createElement("div");
    overlay.className = "pwa-overlay";

    if (type === "ios") {
      overlay.innerHTML =
        '<div class="pwa-modal">' +
          '<div class="pwa-modal-icon">📱</div>' +
          '<h2 class="pwa-modal-title">Установите Киди</h2>' +
          '<p class="pwa-modal-text">Добавьте на экран телефона и открывайте как обычное приложение</p>' +
          '<div class="pwa-modal-steps">' +
            '<div class="pwa-modal-step"><span class="pwa-modal-step-num">1</span><span>Нажмите «Поделиться» внизу экрана Safari</span></div>' +
            '<div class="pwa-modal-step"><span class="pwa-modal-step-num">2</span><span>Выберите <strong>«На экран Домой»</strong></span></div>' +
            '<div class="pwa-modal-step"><span class="pwa-modal-step-num">3</span><span>Нажмите <strong>«Добавить»</strong></span></div>' +
          '</div>' +
          '<button class="pwa-modal-btn pwa-modal-btn--primary" id="pwa-ok">Понятно</button>' +
          '<button class="pwa-modal-btn pwa-modal-btn--ghost" id="pwa-later">Потом</button>' +
        '</div>';
    } else {
      overlay.innerHTML =
        '<div class="pwa-modal">' +
          '<div class="pwa-modal-icon">📱</div>' +
          '<h2 class="pwa-modal-title">Установите Киди</h2>' +
          '<p class="pwa-modal-text">Как обычное приложение на телефоне. Бесплатно, за пару секунд.</p>' +
          '<button class="pwa-modal-btn pwa-modal-btn--primary" id="pwa-install">Установить</button>' +
          '<button class="pwa-modal-btn pwa-modal-btn--ghost" id="pwa-later">Не сейчас</button>' +
        '</div>';
    }

    document.body.appendChild(overlay);
    requestAnimationFrame(function () { overlay.classList.add("is-open"); });

    function close(rememberForSession) {
      overlay.classList.remove("is-open");
      setTimeout(function () { overlay.remove(); }, 200);
      if (rememberForSession) sessionStorage.setItem("pwa_later", "1");
    }

    var okBtn = document.getElementById("pwa-ok");
    if (okBtn) okBtn.addEventListener("click", function () { close(true); });

    var laterBtn = document.getElementById("pwa-later");
    if (laterBtn) laterBtn.addEventListener("click", function () { close(true); });

    var installBtn = document.getElementById("pwa-install");
    if (installBtn && deferredPrompt) {
      installBtn.addEventListener("click", function () {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(function () {
          deferredPrompt = null;
          close(true);
        });
      });
    }

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) close(false);
    });
  }
})();
