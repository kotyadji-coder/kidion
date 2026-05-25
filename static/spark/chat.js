/**
 * Spark Chat — multi-character chat JS
 */
(function () {
  const CFG = window.SPARK_CHAT || {};
  const dailyLimit = CFG.hasSubscription ? CFG.paidLimit : CFG.freeLimit;

  // State
  let characters = [];
  let activeChar = "spark";
  let sending = false;
  let attachedFile = null;
  let dailyCount = 0;
  let selectedStyle = null; // remembers Arty style selection
  let freeImagesRemaining = 3;

  // DOM refs
  const root = document.getElementById("spark-chat");
  const messagesEl = document.getElementById("messages");
  const emptyState = document.getElementById("empty-state");
  const chatInput = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");
  const btnNewChat = document.getElementById("btn-new-chat");
  const btnMic = document.getElementById("btn-mic");
  const fileInput = document.getElementById("file-input");
  const attachPreview = document.getElementById("attach-preview");
  const attachName = document.getElementById("attach-name");
  const btnRemoveAttach = document.getElementById("btn-remove-attach");
  const typingRow = document.getElementById("typing-row");
  const typingAvatar = document.getElementById("typing-avatar");
  const sideList = document.getElementById("side-list");
  const charStrip = document.getElementById("char-strip");
  const drawerList = document.getElementById("drawer-list");
  const drawer = document.getElementById("char-drawer");
  const voiceOverlay = document.getElementById("voice-overlay");

  // Init
  loadCharacters().then(() => {
    switchCharacter("spark", false);
    loadChat();
  });
  setupEvents();

  // Voice input available for everyone (Web Speech API is free)

  // ---------- API ----------
  async function api(url, method, body) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (body instanceof FormData) {
      opts.body = body;
    } else if (body) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    let data;
    try { data = await res.json(); } catch { data = { error: "invalid_response" }; }
    return { status: res.status, data };
  }

  // ---------- Characters ----------
  async function loadCharacters() {
    try {
      const { data } = await api("/api/kid/characters", "GET");
      characters = data.characters || [];
      const artist = characters.find(c => c.key === "artist");
      if (artist && artist.free_images_remaining != null) {
        freeImagesRemaining = artist.free_images_remaining;
      }
      renderSidebar();
      renderCharStrip();
      renderDrawer();
    } catch (e) {
      console.error("Failed to load characters:", e);
      // Fallback
      characters = [{ key: "spark", name_ru: "Киди", role_ru: "Универсальный друг", is_free: true, locked: false, greeting_ru: "Привет! Я Киди!", greeting_sub_ru: "", suggestions: [], accent_color: "spark" }];
    }
  }

  function getCharAvatar(key) {
    const tmpl = document.getElementById("avatar-" + key);
    if (tmpl) return tmpl.content.cloneNode(true);
    const span = document.createElement("span");
    span.textContent = key[0].toUpperCase();
    return span;
  }

  function renderSidebar() {
    sideList.innerHTML = "";
    characters.forEach((c) => {
      const li = document.createElement("li");
      li.className = "sc-side-item" + (c.key === activeChar ? " is-active" : "");
      li.dataset.char = c.key;
      li.innerHTML = `
        <div class="sc-side-av-wrap">
          <div class="sc-side-av"></div>
          <span class="sc-side-dot"></span>
        </div>
        <div class="sc-side-info">
          <div class="sc-side-row">
            <span class="sc-side-name">${esc(c.name_ru)}</span>
          </div>
          <span class="sc-side-msg">${esc(c.role_ru)}</span>
        </div>`;
      li.querySelector(".sc-side-av").appendChild(getCharAvatar(c.key));
      li.addEventListener("click", () => switchCharacter(c.key, true));
      sideList.appendChild(li);
    });
  }

  function isCharExhausted(key) {
    if (key === "artist") return freeImagesRemaining <= 0 && !CFG.hasSubscription;
    return (dailyLimit - dailyCount) <= 0;
  }

  function renderCharStrip() {
    charStrip.innerHTML = "";
    characters.forEach((c) => {
      const btn = document.createElement("button");
      btn.className = "sc-char-btn" + (c.key === activeChar ? " is-active" : "") + (c.locked ? " is-locked" : "");
      btn.dataset.char = c.key;
      const av = document.createElement("div");
      av.className = "sc-char-av";
      av.appendChild(getCharAvatar(c.key));
      if (isCharExhausted(c.key)) {
        const dot = document.createElement("span");
        dot.className = "sc-char-dot-off";
        av.appendChild(dot);
      }
      const name = document.createElement("span");
      name.className = "sc-char-name";
      name.textContent = c.name_ru;
      btn.appendChild(av);
      btn.appendChild(name);
      btn.addEventListener("click", () => {
        switchCharacter(c.key, !c.locked);
      });
      charStrip.appendChild(btn);
    });
  }

  function renderDrawer() {
    drawerList.innerHTML = "";
    characters.forEach((c) => {
      const li = document.createElement("li");
      li.className = "sc-drawer-item" + (c.key === activeChar ? " is-active" : "") + (c.locked ? " is-locked" : "");
      li.dataset.char = c.key;
      li.innerHTML = `
        <div class="sc-drawer-av"></div>
        <div class="sc-drawer-info">
          <h3 class="sc-drawer-name">${esc(c.name_ru)}</h3>
          <p class="sc-drawer-role">${esc(c.role_ru)}</p>
          <p class="sc-drawer-quote">«${esc(c.greeting_ru)}»</p>
        </div>
        <div class="sc-drawer-check">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7.5l2.6 2.5L11 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>`;
      li.querySelector(".sc-drawer-av").appendChild(getCharAvatar(c.key));
      li.addEventListener("click", () => {
        switchCharacter(c.key, !c.locked);
        closeDrawer();
      });
      drawerList.appendChild(li);
    });
  }

  function switchCharacter(key, reload) {
    activeChar = key;
    root.dataset.char = key;

    const c = characters.find((ch) => ch.key === key) || characters[0];

    // Update header
    document.getElementById("head-name").textContent = c.name_ru;
    document.getElementById("head-role").textContent = c.role_ru;
    const headAv = document.getElementById("head-avatar");
    headAv.innerHTML = "";
    headAv.appendChild(getCharAvatar(key));

    // Update empty state
    const emptyAv = document.getElementById("empty-avatar");
    emptyAv.innerHTML = "";
    emptyAv.appendChild(getCharAvatar(key));
    document.getElementById("empty-greet").textContent = c.greeting_ru;
    const subText = c.greeting_sub_ru || "";
    document.getElementById("empty-sub").textContent = subText;

    // Render suggestion chips (grid for artist, horizontal for others)
    const chipsEl = document.getElementById("empty-chips");
    chipsEl.innerHTML = "";
    const isArtist = key === "artist";
    if (isArtist) {
      chipsEl.classList.add("is-grid");
      const freeImg = c.free_images_remaining != null ? c.free_images_remaining : 3;
      const counter = document.createElement("p");
      counter.className = "sc-grid-hint sc-img-counter";
      counter.textContent = freeImg > 0
        ? `${freeImg} картинки бесплатно`
        : `Волшебные краски закончились`;
      chipsEl.appendChild(counter);
    } else {
      chipsEl.classList.remove("is-grid");
    }
    (c.suggestions || []).forEach((s) => {
      const btn = document.createElement("button");
      btn.className = isArtist ? "sc-style-card" : "sc-chip";
      btn.innerHTML = isArtist
        ? `<span class="sc-style-ico">${esc(s.ico)}</span><span class="sc-style-label">${esc(s.label)}</span>`
        : `<span class="sc-chip-ico">${esc(s.ico)}</span><span>${esc(s.label)}</span>`;
      btn.addEventListener("click", () => {
        if (isArtist) {
          if (attachedFile) {
            chatInput.value = `Сделай моё фото в стиле ${s.label}`;
            sendMessage();
          } else {
            // No photo: show auto-response without spending tokens, remember style
            selectedStyle = s.label;
            emptyState.style.display = "none";
            messagesEl.style.display = "";
            if (!messagesEl.querySelector(".sc-day")) {
              const day = document.createElement("div");
              day.className = "sc-day";
              day.textContent = "Сегодня";
              messagesEl.appendChild(day);
            }
            appendMessage({ role: "user", content: `Стиль: ${s.label}`, created_at: new Date().toISOString() }, false);
            appendMessage({ role: "assistant", content: `Стиль ${s.label} — отличный выбор! Расскажи, что нарисовать, или прикрепи фото.`, created_at: new Date().toISOString() }, true);
            scrollToBottom();
          }
          return;
        } else {
          chatInput.value = s.label;
          updateSendBtn();
          chatInput.focus();
        }
      });
      chipsEl.appendChild(btn);
    });

    // Update typing avatar
    typingAvatar.innerHTML = "";
    typingAvatar.appendChild(getCharAvatar(key));

    // Update placeholder
    chatInput.placeholder = `Напиши ${c.name_ru}...`;

    // Update sidebar, char strip & drawer active states
    sideList.querySelectorAll(".sc-side-item").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.char === key);
    });
    charStrip.querySelectorAll(".sc-char-btn").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.char === key);
    });
    drawerList.querySelectorAll(".sc-drawer-item").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.char === key);
    });

    // Handle locked character: show greeting but hide composer
    const c_locked = c.locked;
    const composer = document.getElementById("composer");
    if (c_locked) {
      messagesEl.style.display = "none";
      emptyState.style.display = "";
      // Override empty sub with subscribe CTA
      document.getElementById("empty-sub").innerHTML =
        c.greeting_sub_ru || c.role_ru + "<br><br>" +
        '<a href="/chat/subscribe" style="color:var(--spark-violet);font-weight:600;text-decoration:underline">Оформите подписку</a>, чтобы общаться с ' + esc(c.name_ru);
      composer.style.display = "none";
    } else {
      composer.style.display = "";
      if (reload) loadChat();
      updateQuota();
    }
  }

  // ---------- Chat ----------
  async function loadChat() {
    try {
      const { data } = await api(`/api/kid/chat?character=${activeChar}`, "GET");
      dailyCount = data.daily_count || 0;
      updateQuota();
      renderMessages(data.messages || []);
    } catch (e) {
      console.error("Failed to load chat:", e);
    }
  }

  function renderMessages(messages) {
    messagesEl.innerHTML = "";
    if (!messages.length) {
      emptyState.style.display = "";
      messagesEl.style.display = "none";
      return;
    }
    emptyState.style.display = "none";
    messagesEl.style.display = "";

    // Day separator
    const day = document.createElement("div");
    day.className = "sc-day";
    day.textContent = "Сегодня";
    messagesEl.appendChild(day);

    messages.forEach((m, i) => {
      const next = messages[i + 1];
      const isBot = m.role === "assistant";
      const showAv = isBot && (!next || next.role !== "assistant");
      appendMessage(m, showAv);
    });

    scrollToBottom();
  }

  function appendMessage(m, showAv) {
    const isUser = m.role === "user";
    const row = document.createElement("div");
    row.className = "sc-row" + (isUser ? " is-user" : "");

    if (!isUser) {
      const av = document.createElement("div");
      av.className = "sc-row-av" + (showAv ? " is-show" : "");
      av.appendChild(getCharAvatar(activeChar));
      row.appendChild(av);
    }

    const stack = document.createElement("div");
    stack.className = "sc-stack";

    // Handle image messages (clickable to view full-size)
    if (m.image_url) {
      const imgBub = document.createElement("div");
      imgBub.className = "sc-bub sc-bub-img";
      const img = document.createElement("img");
      img.src = m.image_url;
      img.alt = "Картинка";
      img.addEventListener("click", () => showImageViewer(m.image_url));
      imgBub.appendChild(img);
      const openBtn = document.createElement("button");
      openBtn.className = "sc-img-open-btn";
      openBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14L21 3"/><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/></svg>';
      openBtn.title = "Открыть";
      openBtn.addEventListener("click", (e) => { e.stopPropagation(); showImageViewer(m.image_url); });
      imgBub.appendChild(openBtn);
      stack.appendChild(imgBub);
    }

    if (m.content) {
      const bub = document.createElement("div");
      bub.className = "sc-bub " + (isUser ? "sc-bub-user" : "sc-bub-bot");
      bub.innerHTML = formatMessage(m.content);
      stack.appendChild(bub);
    }

    // Time + report button for assistant messages
    if (m.created_at) {
      const meta = document.createElement("div");
      meta.className = "sc-meta";
      const time = document.createElement("span");
      time.className = "sc-time";
      const d = new Date(m.created_at);
      time.textContent = d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
      meta.appendChild(time);

      if (false) { // report button hidden from kids
      }

      stack.appendChild(meta);
    }

    row.appendChild(stack);
    messagesEl.appendChild(row);
  }

  function formatMessage(text) {
    // Escape HTML first
    let s = esc(text);
    // Bold **text**
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // Italic *text*
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // Newlines
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  async function sendMessage() {
    if (sending) return;
    const text = chatInput.value.trim();
    if (!text && !attachedFile) return;

    sending = true;
    chatInput.value = "";
    updateSendBtn();

    // Show user message immediately
    emptyState.style.display = "none";
    messagesEl.style.display = "";
    if (!messagesEl.querySelector(".sc-day")) {
      const day = document.createElement("div");
      day.className = "sc-day";
      day.textContent = "Сегодня";
      messagesEl.appendChild(day);
    }
    appendMessage({ role: "user", content: text, created_at: new Date().toISOString() }, false);
    scrollToBottom();

    // Show typing
    typingRow.style.display = "";
    scrollToBottom();

    try {
      let result;
      if (attachedFile) {
        const fd = new FormData();
        fd.append("message", text);
        fd.append("image", attachedFile);
        result = await api(`/api/kid/chat/send?character=${activeChar}`, "POST", fd);
        clearAttachment();
      } else {
        result = await api(`/api/kid/chat/send?character=${activeChar}`, "POST", { message: text });
      }

      typingRow.style.display = "none";

      if (result.status === 429) {
        document.getElementById("limit-overlay").classList.add("is-open");
      } else if (result.status === 403) {
        appendMessage({ role: "assistant", content: result.data.message || "Этот персонаж доступен по подписке.", created_at: new Date().toISOString() }, true);
      } else if (result.data.response) {
        dailyCount = result.data.daily_count || dailyCount + 1;
        if (result.data.free_images_remaining != null) {
          freeImagesRemaining = result.data.free_images_remaining;
        }
        updateQuota();
        appendMessage({
          role: "assistant",
          content: result.data.response,
          image_url: result.data.image_url || null,
          created_at: new Date().toISOString(),
        }, true);
      }
      scrollToBottom();
    } catch (e) {
      typingRow.style.display = "none";
      console.error("sendMessage error:", e);
      appendMessage({ role: "assistant", content: "Ой, что-то пошло не так. Попробуй ещё раз!", created_at: new Date().toISOString() }, true);
      scrollToBottom();
    }
    sending = false;
  }

  function showImageViewer(url) {
    const existing = document.getElementById("img-viewer");
    if (existing) existing.remove();
    const overlay = document.createElement("div");
    overlay.id = "img-viewer";
    overlay.className = "sc-img-viewer";
    overlay.innerHTML =
      '<img src="' + url + '" alt="Картинка">' +
      '<div class="sc-img-viewer-actions">' +
        '<a href="' + url + '" download class="sc-img-viewer-btn">Скачать</a>' +
        '<button class="sc-img-viewer-btn sc-img-viewer-close">Закрыть</button>' +
      '</div>';
    overlay.querySelector(".sc-img-viewer-close").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  async function clearChat() {
    showConfirmModal("Начать новый разговор?", "Вся история чата будет удалена.", async () => {
      await api(`/api/kid/chat/clear?character=${activeChar}`, "POST");
      loadChat();
    });
  }

  function showConfirmModal(title, subtitle, onConfirm) {
    const existing = document.getElementById("confirm-modal");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "confirm-modal";
    overlay.className = "sc-confirm-overlay";
    overlay.innerHTML =
      '<div class="sc-confirm-card">' +
        '<h3 class="sc-confirm-title">' + esc(title) + '</h3>' +
        '<p class="sc-confirm-sub">' + esc(subtitle) + '</p>' +
        '<div class="sc-confirm-actions">' +
          '<button class="sc-confirm-btn sc-confirm-cancel">Отмена</button>' +
          '<button class="sc-confirm-btn sc-confirm-ok">Да, начать</button>' +
        '</div>' +
      '</div>';

    overlay.querySelector(".sc-confirm-cancel").addEventListener("click", () => overlay.remove());
    overlay.querySelector(".sc-confirm-ok").addEventListener("click", () => {
      overlay.remove();
      onConfirm();
    });
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

    document.body.appendChild(overlay);
  }

  // ---------- UI helpers ----------
  function updateQuota() {
    if (activeChar === "artist") {
      document.getElementById("quota-count").textContent = `${freeImagesRemaining} картинок`;
      const pct = Math.round((freeImagesRemaining / 3) * 100);
      document.getElementById("quota-bar-fill").style.width = pct + "%";
      document.getElementById("nav-msg-count").textContent = freeImagesRemaining;
      document.getElementById("quota-info").querySelector("strong").previousSibling.textContent = "Осталось ";
      document.getElementById("quota-info").querySelector("strong").nextSibling.textContent = " бесплатных";
    } else {
      const remaining = Math.max(0, dailyLimit - dailyCount);
      document.getElementById("quota-count").textContent = `${remaining} из ${dailyLimit}`;
      const pct = dailyLimit > 0 ? Math.round((remaining / dailyLimit) * 100) : 0;
      document.getElementById("quota-bar-fill").style.width = pct + "%";
      document.getElementById("nav-msg-count").textContent = remaining;
      document.getElementById("quota-info").querySelector("strong").previousSibling.textContent = "Осталось ";
      document.getElementById("quota-info").querySelector("strong").nextSibling.textContent = " сообщений сегодня";
    }
    renderCharStrip();
  }

  function updateSendBtn() {
    const hasText = chatInput.value.trim().length > 0 || attachedFile;
    btnSend.classList.toggle("is-disabled", !hasText);
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
      // Repeat after images may have loaded
      setTimeout(() => { messagesEl.scrollTop = messagesEl.scrollHeight; }, 150);
    });
  }

  function clearAttachment() {
    attachedFile = null;
    attachPreview.style.display = "none";
    fileInput.value = "";
    updateSendBtn();
  }

  function closeDrawer() {
    drawer.classList.remove("is-open");
  }
  function openDrawer() {
    renderDrawer();
    drawer.classList.add("is-open");
  }

  function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ---------- Pro modal ----------
  const proModal = document.getElementById("pro-modal");
  const proModalIcon = document.getElementById("pro-modal-icon");
  const proModalTitle = document.getElementById("pro-modal-title");
  const proModalText = document.getElementById("pro-modal-text");

  function showProModal(feature) {
    const configs = {
      image: {
        icon: "\uD83C\uDFA8",
        title: "Картинки доступны по подписке",
        text: "Попроси взрослого оформить подписку, чтобы отправлять и получать картинки от нейросети!",
      },
      voice: {
        icon: "\uD83C\uDFA4",
        title: "Голосовой ввод по подписке",
        text: "С подпиской можно говорить голосом, а Киди переведёт речь в текст!",
      },
      character: {
        icon: "\u2728",
        title: "Этот персонаж по подписке",
        text: "С подпиской откроются все персонажи: Зуми (учитель), Лоро (рассказчик) и Арти (художник)!",
      },
    };
    const cfg = configs[feature] || configs.character;
    proModalIcon.textContent = cfg.icon;
    proModalTitle.textContent = cfg.title;
    proModalText.textContent = cfg.text;
    proModal.classList.add("is-open");
  }

  document.getElementById("btn-pro-close").addEventListener("click", () => {
    proModal.classList.remove("is-open");
  });

  // ---------- Events ----------
  function setupEvents() {
    chatInput.addEventListener("input", updateSendBtn);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    btnSend.addEventListener("click", sendMessage);
    btnNewChat.addEventListener("click", clearChat);

    // Adult gate for parent area
    setupAdultGate();

    // File attachment — allowed for everyone (free users get 3 images/month)
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        attachedFile = fileInput.files[0];
        attachName.textContent = attachedFile.name;
        attachPreview.style.display = "";
        updateSendBtn();
        // For artist: auto-fill style hint when photo attached
        if (activeChar === "artist" && !chatInput.value.trim()) {
          const style = selectedStyle || "аниме";
          chatInput.value = `Сделай моё фото в стиле ${style}`;
          chatInput.select();
          updateSendBtn();
        }
      }
    });
    btnRemoveAttach.addEventListener("click", clearAttachment);

    // Mobile drawer (still accessible from desktop sidebar)
    document.getElementById("btn-close-drawer").addEventListener("click", closeDrawer);

    // Voice input — available for everyone
    btnMic.addEventListener("click", () => {
      openVoiceOverlay();
    });
    document.getElementById("btn-voice-cancel").addEventListener("click", () => {
      closeVoiceOverlay();
    });
    document.getElementById("btn-voice-stop").addEventListener("click", () => {
      finishVoiceInput();
    });
    document.getElementById("btn-voice-retry").addEventListener("click", () => {
      openVoiceOverlay();
    });
  }

  // ---------- Voice (Web Speech API) ----------
  let recognition = null;
  let voiceText = "";         // accumulated final transcript
  let voiceInterim = "";      // current interim text
  let voiceStopping = false;  // user pressed cancel/done

  const voiceH = document.querySelector(".sc-voice-h");
  const voiceSub = document.querySelector(".sc-voice-sub");
  const voiceTranscript = document.getElementById("voice-transcript");
  const voicePulse = document.getElementById("voice-pulse");
  const btnVoiceStop = document.getElementById("btn-voice-stop");
  const btnVoiceRetry = document.getElementById("btn-voice-retry");
  const btnVoiceCancel = document.getElementById("btn-voice-cancel");

  function setVoiceUI(state) {
    // states: listening, error, nospeech
    voicePulse.classList.toggle("is-error", state !== "listening");
    btnVoiceStop.style.display = state === "listening" ? "" : "none";
    btnVoiceRetry.style.display = state === "listening" ? "none" : "";
    btnVoiceCancel.style.display = "";
  }

  function openVoiceOverlay() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      voiceH.textContent = "Браузер не поддерживает голосовой ввод";
      voiceSub.textContent = "Попробуй Chrome или Safari.";
      voiceTranscript.textContent = "";
      voiceOverlay.classList.add("is-open");
      setVoiceUI("error");
      return;
    }

    voiceText = "";
    voiceInterim = "";
    voiceStopping = false;
    voiceH.textContent = "Говори, я слушаю!";
    voiceSub.textContent = "Я переведу твою речь в текст.";
    voiceTranscript.textContent = "";
    voiceOverlay.classList.add("is-open");
    setVoiceUI("listening");
    startRecognition();
  }

  function closeVoiceOverlay() {
    voiceStopping = true;
    voiceOverlay.classList.remove("is-open");
    if (recognition) {
      try { recognition.abort(); } catch (_) {}
      recognition = null;
    }
  }

  function finishVoiceInput() {
    voiceStopping = true;
    if (recognition) {
      try { recognition.stop(); } catch (_) {}
    }
    // Use whatever text we have (final + interim)
    const text = (voiceText + " " + voiceInterim).trim();
    if (text) {
      chatInput.value = text;
      updateSendBtn();
    }
    voiceOverlay.classList.remove("is-open");
    recognition = null;
  }

  function startRecognition() {
    if (recognition) {
      try { recognition.abort(); } catch (_) {}
      recognition = null;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      voiceText = "";
      voiceInterim = "";
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          voiceText += event.results[i][0].transcript + " ";
        } else {
          voiceInterim += event.results[i][0].transcript;
        }
      }
      voiceTranscript.textContent = (voiceText + voiceInterim).trim();
    };

    recognition.onerror = (e) => {
      if (voiceStopping) return;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        voiceH.textContent = "Нет доступа к микрофону";
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
        if (isIOS) {
          voiceSub.textContent = "Настройки → Safari → Микрофон → Разрешить";
        } else if (isSafari) {
          voiceSub.textContent = "Safari → Настройки для этого сайта → Микрофон → Разрешить";
        } else {
          voiceSub.textContent = "Нажми на замок 🔒 в адресной строке → Разрешить микрофон → Обнови страницу";
        }
        setVoiceUI("error");
        recognition = null;
      } else if (e.error === "no-speech") {
        // Don't close — let user retry or keep waiting
        voiceH.textContent = "Не слышу... Попробуй ещё раз";
        voiceSub.textContent = "Говори громче и ближе к микрофону.";
        setVoiceUI("nospeech");
        recognition = null;
      } else if (e.error === "aborted") {
        recognition = null;
      } else {
        // network, audio-capture, etc.
        voiceH.textContent = "Что-то пошло не так";
        voiceSub.textContent = "Проверь микрофон и попробуй снова.";
        setVoiceUI("error");
        recognition = null;
      }
    };

    recognition.onend = () => {
      if (voiceStopping) { recognition = null; return; }
      // If we have text, auto-finish
      const text = (voiceText + voiceInterim).trim();
      if (text) {
        chatInput.value = text;
        updateSendBtn();
        voiceOverlay.classList.remove("is-open");
        recognition = null;
        return;
      }
      // No text yet — auto-restart (Chrome kills recognition on silence)
      recognition = null;
      if (voiceOverlay.classList.contains("is-open")) {
        setTimeout(() => {
          if (!voiceStopping && voiceOverlay.classList.contains("is-open")) {
            startRecognition();
          }
        }, 100);
      }
    };

    try {
      recognition.start();
    } catch (e) {
      voiceH.textContent = "Не удалось запустить микрофон";
      voiceSub.textContent = "Попробуй обновить страницу.";
      setVoiceUI("error");
      recognition = null;
    }
  }

  // ---------- Adult gate ----------
  function setupAdultGate() {
    const gateOverlay = document.getElementById("adult-gate");
    const gateQuestion = document.getElementById("gate-question");
    const gateAnswer = document.getElementById("gate-answer");
    const gateError = document.getElementById("gate-error");
    const btnParent = document.getElementById("btn-parent-gate");
    let correctAnswer = 0;

    function generateProblem() {
      const a = 10 + Math.floor(Math.random() * 40);
      const b = 10 + Math.floor(Math.random() * 40);
      correctAnswer = a + b;
      gateQuestion.textContent = `${a} + ${b} = ?`;
      gateAnswer.value = "";
      gateError.style.display = "none";
    }

    btnParent.addEventListener("click", () => {
      generateProblem();
      gateOverlay.classList.add("is-open");
      setTimeout(() => gateAnswer.focus(), 100);
    });

    document.getElementById("btn-gate-check").addEventListener("click", checkGate);
    gateAnswer.addEventListener("keydown", (e) => {
      if (e.key === "Enter") checkGate();
    });
    document.getElementById("btn-gate-cancel").addEventListener("click", () => {
      gateOverlay.classList.remove("is-open");
    });

    function checkGate() {
      if (parseInt(gateAnswer.value, 10) === correctAnswer) {
        gateOverlay.classList.remove("is-open");
        window.location.href = `/chat/report/${CFG.childId}`;
      } else {
        gateError.style.display = "";
        gateAnswer.value = "";
        gateAnswer.focus();
      }
    }
  }
})();
