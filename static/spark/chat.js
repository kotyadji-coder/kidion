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

  // DOM refs
  const root = document.getElementById("spark-chat");
  const messagesEl = document.getElementById("messages");
  const emptyState = document.getElementById("empty-state");
  const chatInput = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");
  const btnNewChat = document.getElementById("btn-new-chat");
  const btnBack = document.getElementById("btn-back");
  const btnMic = document.getElementById("btn-mic");
  const fileInput = document.getElementById("file-input");
  const attachPreview = document.getElementById("attach-preview");
  const attachName = document.getElementById("attach-name");
  const btnRemoveAttach = document.getElementById("btn-remove-attach");
  const typingRow = document.getElementById("typing-row");
  const typingAvatar = document.getElementById("typing-avatar");
  const sideList = document.getElementById("side-list");
  const drawerList = document.getElementById("drawer-list");
  const drawer = document.getElementById("char-drawer");
  const voiceOverlay = document.getElementById("voice-overlay");

  // Init
  loadCharacters().then(() => {
    switchCharacter("spark", false);
    loadChat();
  });
  setupEvents();

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
    return { status: res.status, data: await res.json() };
  }

  // ---------- Characters ----------
  async function loadCharacters() {
    try {
      const { data } = await api("/api/kid/characters", "GET");
      characters = data.characters || [];
      renderSidebar();
      renderDrawer();
    } catch (e) {
      console.error("Failed to load characters:", e);
      // Fallback
      characters = [{ key: "spark", name_ru: "Спарк", role_ru: "Универсальный друг", is_free: true, locked: false, greeting_ru: "Привет! Я Спарк!", greeting_sub_ru: "", suggestions: [], accent_color: "spark" }];
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
          <div class="sc-side-meta">
            <span class="sc-side-tag ${c.is_free ? "is-free" : "is-pro"}">${c.is_free ? "Бесплатно" : "Подписка"}</span>
          </div>
        </div>`;
      li.querySelector(".sc-side-av").appendChild(getCharAvatar(c.key));
      li.addEventListener("click", () => switchCharacter(c.key, true));
      sideList.appendChild(li);
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
          <h3 class="sc-drawer-name">${esc(c.name_ru)}${c.locked ? " 🔒" : ""}</h3>
          <p class="sc-drawer-role">${esc(c.role_ru)}${c.locked ? " · по подписке" : ""}</p>
          <p class="sc-drawer-quote">«${esc(c.greeting_ru)}»</p>
        </div>
        <div class="sc-drawer-check">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7.5l2.6 2.5L11 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>`;
      li.querySelector(".sc-drawer-av").appendChild(getCharAvatar(c.key));
      li.addEventListener("click", () => {
        if (c.locked) return;
        switchCharacter(c.key, true);
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
    document.getElementById("empty-sub").textContent = c.greeting_sub_ru || "";

    // Render suggestion chips
    const chipsEl = document.getElementById("empty-chips");
    chipsEl.innerHTML = "";
    (c.suggestions || []).forEach((s) => {
      const btn = document.createElement("button");
      btn.className = "sc-chip";
      btn.innerHTML = `<span class="sc-chip-ico">${esc(s.ico)}</span><span>${esc(s.label)}</span>`;
      btn.addEventListener("click", () => {
        chatInput.value = s.label;
        updateSendBtn();
        chatInput.focus();
      });
      chipsEl.appendChild(btn);
    });

    // Update typing avatar
    typingAvatar.innerHTML = "";
    typingAvatar.appendChild(getCharAvatar(key));

    // Update placeholder
    chatInput.placeholder = `Напиши ${c.name_ru}...`;

    // Update sidebar & drawer active states
    sideList.querySelectorAll(".sc-side-item").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.char === key);
    });
    drawerList.querySelectorAll(".sc-drawer-item").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.char === key);
    });

    if (reload) loadChat();
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

    // Handle image messages
    if (m.image_url) {
      const imgBub = document.createElement("div");
      imgBub.className = "sc-bub sc-bub-img";
      const img = document.createElement("img");
      img.src = m.image_url;
      img.alt = "Картинка";
      imgBub.appendChild(img);
      stack.appendChild(imgBub);
    }

    if (m.content) {
      const bub = document.createElement("div");
      bub.className = "sc-bub " + (isUser ? "sc-bub-user" : "sc-bub-bot");
      bub.innerHTML = formatMessage(m.content);
      stack.appendChild(bub);
    }

    // Time
    if (m.created_at) {
      const time = document.createElement("span");
      time.className = "sc-time";
      const d = new Date(m.created_at);
      time.textContent = d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
      stack.appendChild(time);
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

      if (result.status === 429 || result.status === 403) {
        appendMessage({ role: "assistant", content: result.data.message || "Лимит исчерпан.", created_at: new Date().toISOString() }, true);
      } else if (result.data.response) {
        dailyCount = result.data.daily_count || dailyCount + 1;
        updateQuota();
        appendMessage({ role: "assistant", content: result.data.response, created_at: new Date().toISOString() }, true);
      }
      scrollToBottom();
    } catch (e) {
      typingRow.style.display = "none";
      appendMessage({ role: "assistant", content: "Ой, что-то пошло не так. Попробуй ещё раз!", created_at: new Date().toISOString() }, true);
      scrollToBottom();
    }
    sending = false;
  }

  async function clearChat() {
    if (!confirm("Начать новый разговор?")) return;
    await api(`/api/kid/chat/clear?character=${activeChar}`, "POST");
    loadChat();
  }

  // ---------- UI helpers ----------
  function updateQuota() {
    const remaining = Math.max(0, dailyLimit - dailyCount);
    document.getElementById("quota-count").textContent = `${remaining} из ${dailyLimit}`;
    const pct = dailyLimit > 0 ? Math.round((remaining / dailyLimit) * 100) : 0;
    document.getElementById("quota-bar-fill").style.width = pct + "%";
    document.getElementById("nav-msg-count").textContent = remaining;
  }

  function updateSendBtn() {
    const hasText = chatInput.value.trim().length > 0 || attachedFile;
    btnSend.classList.toggle("is-disabled", !hasText);
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
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
    btnBack.addEventListener("click", () => { window.location.href = "/kid/home"; });

    // File attachment
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        attachedFile = fileInput.files[0];
        attachName.textContent = attachedFile.name;
        attachPreview.style.display = "";
        updateSendBtn();
      }
    });
    btnRemoveAttach.addEventListener("click", clearAttachment);

    // Mobile drawer
    document.getElementById("tab-chars").addEventListener("click", (e) => {
      e.preventDefault();
      openDrawer();
    });
    document.getElementById("btn-close-drawer").addEventListener("click", closeDrawer);

    // Voice (placeholder — opens overlay, cancel closes it)
    btnMic.addEventListener("click", () => {
      voiceOverlay.classList.add("is-open");
      startVoiceRecognition();
    });
    document.getElementById("btn-voice-cancel").addEventListener("click", () => {
      voiceOverlay.classList.remove("is-open");
      stopVoiceRecognition();
    });
    document.getElementById("btn-voice-stop").addEventListener("click", () => {
      voiceOverlay.classList.remove("is-open");
      stopVoiceRecognition();
    });
  }

  // ---------- Voice (Web Speech API) ----------
  let recognition = null;

  function startVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      voiceOverlay.classList.remove("is-open");
      alert("Голосовой ввод не поддерживается в вашем браузере.");
      return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const text = event.results[0][0].transcript;
      chatInput.value = text;
      updateSendBtn();
      voiceOverlay.classList.remove("is-open");
    };
    recognition.onerror = () => {
      voiceOverlay.classList.remove("is-open");
    };
    recognition.onend = () => {
      // auto-close if no result
    };
    recognition.start();
  }

  function stopVoiceRecognition() {
    if (recognition) {
      recognition.stop();
      recognition = null;
    }
  }
})();
