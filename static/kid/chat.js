/**
 * Kidion — Kid Chat JS (v5)
 * Single Spark chat per child
 */

(function() {
  const CFG = window.KID_CHAT || {};
  let sending = false;
  let attachedFile = null;

  // DOM
  const chatMessages = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send-btn');
  const fileInput = document.getElementById('file-input');
  const attachPreview = document.getElementById('attach-preview');
  const attachThumb = document.getElementById('attach-thumb');
  const btnRemoveAttach = document.getElementById('btn-remove-attach');
  const limitInfoCount = document.getElementById('limit-info-count');
  const btnNewChat = document.getElementById('btn-new-chat');

  // Init
  loadChat();
  setupEvents();

  // --- API helper ---
  async function api(url, method, body) {
    const opts = { method, credentials: 'same-origin', headers: {} };
    if (body instanceof FormData) {
      opts.body = body;
    } else if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    return { status: res.status, data: await res.json() };
  }

  // --- Load chat messages ---
  async function loadChat() {
    try {
      const { data } = await api('/api/kid/chat', 'GET');
      renderMessages(data.messages || []);
      updateLimit(data.daily_count, data.daily_limit);
    } catch (e) {
      console.error('Failed to load chat:', e);
    }
  }

  function renderMessages(messages) {
    if (!chatMessages) return;
    if (messages.length === 0) {
      showEmptyState();
      return;
    }
    const emptyEl = chatMessages.querySelector('.chat-empty-state');
    if (emptyEl) emptyEl.remove();
    chatMessages.innerHTML = messages.map(renderMessage).join('');
    scrollToBottom();
  }

  function showEmptyState() {
    if (!chatMessages) return;
    chatMessages.innerHTML =
      '<div class="chat-empty-state" id="chat-empty">' +
      '<div class="chat-empty__avatar"><img src="/static/kid/img/spark.png" alt="Kidi"></div>' +
      '<div class="chat-empty__title">Привет! Я Kidi!</div>' +
      '<div class="chat-empty__text">Я знаю много интересного и всегда готов помочь. Спроси меня о чём угодно!</div>' +
      '<div class="chat-empty__hints">' +
      '<button class="chat-empty__hint" data-text="Расскажи интересный факт">Интересный факт</button>' +
      '<button class="chat-empty__hint" data-text="Помоги с домашкой">Помощь с уроками</button>' +
      '<button class="chat-empty__hint" data-text="Придумай историю">Придумай историю</button>' +
      '</div></div>';
    bindHints();
  }

  function renderMessage(msg) {
    const isUser = msg.role === 'user';
    const cls = isUser ? 'chat-msg--user' : 'chat-msg--assistant';
    const avatar = isUser
      ? '<div class="chat-msg__avatar">' + CFG.childName.charAt(0).toUpperCase() + '</div>'
      : '<div class="chat-msg__avatar"><img src="/static/kid/img/spark.png" alt="Kidi"></div>';
    const time = formatTime(msg.created_at);
    const imgHtml = msg.image_url
      ? '<img class="chat-msg__image" src="' + escAttr(msg.image_url) + '" alt="image">'
      : '';

    return '<div class="chat-msg ' + cls + '">' +
      avatar +
      '<div>' +
      imgHtml +
      '<div class="chat-msg__bubble">' + formatContent(msg.content) + '</div>' +
      '<div class="chat-msg__time">' + time + '</div>' +
      '</div></div>';
  }

  function showTyping() {
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--assistant';
    el.id = 'typing-indicator';
    el.innerHTML = '<div class="chat-msg__avatar"><img src="/static/kid/img/spark.png" alt="Kidi"></div>' +
      '<div class="chat-msg__bubble chat-typing">' +
      '<span class="chat-typing__dot"></span><span class="chat-typing__dot"></span><span class="chat-typing__dot"></span>' +
      '</div>';
    chatMessages.appendChild(el);
    scrollToBottom();
  }

  function hideTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  // --- Send message ---
  async function sendMessage(text) {
    if (sending) return;
    text = text || (chatInput.value || '').trim();
    if (!text && !attachedFile) return;

    sending = true;
    sendBtn.disabled = true;

    // Remove empty state
    const emptyEl = chatMessages.querySelector('.chat-empty-state');
    if (emptyEl) emptyEl.remove();

    // Show user message
    chatMessages.insertAdjacentHTML('beforeend', renderMessage({
      role: 'user',
      content: text,
      image_url: attachedFile ? URL.createObjectURL(attachedFile) : null,
      created_at: new Date().toISOString(),
    }));
    scrollToBottom();

    chatInput.value = '';
    clearAttach();
    showTyping();

    try {
      let result;
      if (attachedFile) {
        const fd = new FormData();
        fd.append('message', text);
        fd.append('image', attachedFile);
        result = await api('/api/kid/chat/send', 'POST', fd);
      } else {
        result = await api('/api/kid/chat/send', 'POST', { message: text });
      }

      hideTyping();

      if (result.status === 200) {
        chatMessages.insertAdjacentHTML('beforeend', renderMessage({
          role: 'assistant',
          content: result.data.response,
          created_at: new Date().toISOString(),
        }));
        scrollToBottom();
        if (result.data.daily_count !== undefined) {
          updateLimit(result.data.daily_count, result.data.daily_limit);
        }
      } else if (result.status === 429) {
        chatMessages.insertAdjacentHTML('beforeend',
          '<div class="chat-msg chat-msg--assistant">' +
          '<div class="chat-msg__avatar"><img src="/static/kid/img/spark.png" alt="Kidi"></div>' +
          '<div class="chat-msg__bubble" style="background:#FFF3E0;color:#E8503F;">' +
          escHtml(result.data.message || 'На сегодня сообщения закончились!') +
          '</div></div>');
        scrollToBottom();
      }
    } catch (e) {
      hideTyping();
    }

    sending = false;
    updateSendBtn();
  }

  // --- New conversation ---
  async function clearChat() {
    try {
      await api('/api/kid/chat/clear', 'POST');
      showEmptyState();
    } catch (e) {
      console.error('Failed to clear chat:', e);
    }
  }

  // --- Events ---
  function setupEvents() {
    chatInput.addEventListener('input', updateSendBtn);
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener('click', () => sendMessage());

    // File attach
    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        alert('Файл слишком большой (макс. 5 МБ)');
        fileInput.value = '';
        return;
      }
      attachedFile = file;
      attachThumb.src = URL.createObjectURL(file);
      attachPreview.style.display = 'flex';
      updateSendBtn();
    });

    btnRemoveAttach.addEventListener('click', clearAttach);

    // New conversation button
    if (btnNewChat) {
      btnNewChat.addEventListener('click', clearChat);
    }

    // Quick hint buttons
    bindHints();
  }

  function bindHints() {
    document.querySelectorAll('.chat-empty__hint').forEach(btn => {
      btn.addEventListener('click', () => {
        const text = btn.dataset.text;
        if (text) sendMessage(text);
      });
    });
  }

  // --- Helpers ---
  function clearAttach() {
    attachedFile = null;
    fileInput.value = '';
    attachPreview.style.display = 'none';
    attachThumb.src = '';
    updateSendBtn();
  }

  function updateSendBtn() {
    sendBtn.disabled = sending || (!(chatInput.value || '').trim() && !attachedFile);
  }

  function updateLimit(count, limit) {
    const remaining = Math.max(0, (limit || 5) - (count || 0));
    if (limitInfoCount) limitInfoCount.textContent = remaining;
  }

  function scrollToBottom() {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escAttr(str) {
    return escHtml(str).replace(/"/g, '&quot;');
  }

  function formatContent(text) {
    let html = escHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    html = html.replace(/\*(.+?)\*/g, '<i>$1</i>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
})();
