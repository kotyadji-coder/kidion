/**
 * Kidion — Kid Chat JS (v3)
 * One chat per character persona (owl, dreamer, professor)
 */

(function() {
  const CFG = window.KID_CHAT || {};
  const chars = CFG.characters || {};

  let currentCharacter = 'owl';
  let chatIdByCharacter = {}; // { owl: 123, dreamer: 456, ... }
  let currentChatId = null;
  let sending = false;
  let attachedFile = null;

  // DOM
  const chatMessages = document.getElementById('chat-messages');
  const chatTitle = document.getElementById('chat-title');
  const chatSubtitle = document.getElementById('chat-subtitle');
  const chatHeaderIcon = document.getElementById('chat-header-icon');
  const inputArea = document.getElementById('chat-input-area');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send-btn');
  const fileInput = document.getElementById('file-input');
  const attachPreview = document.getElementById('attach-preview');
  const attachThumb = document.getElementById('attach-thumb');
  const btnRemoveAttach = document.getElementById('btn-remove-attach');
  const limitInfoCount = document.getElementById('limit-info-count');
  const limitRemaining = document.getElementById('limit-remaining');

  // Sidebar & mobile
  const sidebar = document.getElementById('chat-sidebar');
  const btnSidebar = document.getElementById('btn-toggle-sidebar');
  const overlay = document.getElementById('chat-overlay');

  // --- Init ---
  loadChats().then(() => {
    selectCharacter('owl');
  });
  setupEvents();

  // --- API ---
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

  // --- Load all chats and map by character ---
  async function loadChats() {
    try {
      const { data } = await api('/api/kid/chats', 'GET');
      const chats = data.chats || [];
      // Map: take the most recent chat for each character
      chatIdByCharacter = {};
      chats.forEach(c => {
        if (!chatIdByCharacter[c.character_key]) {
          chatIdByCharacter[c.character_key] = c.id;
        }
      });
    } catch (e) {
      console.error('Failed to load chats:', e);
    }
  }

  // --- Select character ---
  async function selectCharacter(key) {
    currentCharacter = key;
    const info = chars[key] || chars.owl || {};

    // Update header
    if (chatTitle) chatTitle.textContent = info.name_ru || key;
    if (chatSubtitle) chatSubtitle.textContent = info.description_ru ? info.description_ru.substring(0, 40) : '';
    if (chatHeaderIcon) {
      chatHeaderIcon.textContent = info.emoji || '🦉';
      chatHeaderIcon.style.background = info.color || '#2DD4BF';
    }

    // Update active states
    document.querySelectorAll('.ch-persona, .ch-mobile-persona').forEach(el => {
      const isActive = el.dataset.key === key;
      el.classList.toggle('ch-persona--active', isActive);
      el.classList.toggle('ch-mobile-persona--active', isActive);
    });

    // Open or create chat
    if (chatIdByCharacter[key]) {
      await openChat(chatIdByCharacter[key]);
    } else {
      // Create a new chat for this character
      try {
        const { status, data } = await api('/api/kid/chats', 'POST', { character_key: key });
        if (status === 200 || status === 201) {
          chatIdByCharacter[key] = data.chat.id;
          await openChat(data.chat.id);
        }
      } catch (e) {
        showEmptyState(info);
      }
    }

    closePanels();
  }

  // --- Open chat ---
  async function openChat(chatId) {
    currentChatId = chatId;
    try {
      const { data } = await api('/api/kid/chats/' + chatId + '/messages', 'GET');
      renderMessages(data.messages || []);
      updateLimit(data.daily_count, data.daily_limit);
    } catch (e) {
      const info = chars[currentCharacter] || {};
      showEmptyState(info);
    }
  }

  function showEmptyState(info) {
    if (!chatMessages) return;
    chatMessages.innerHTML =
      '<div class="chat-empty-state">' +
      '<div class="chat-empty-state__icon">' + (info.emoji || '💬') + '</div>' +
      '<div class="chat-empty-state__text">Привет! Я ' + escHtml(info.name_ru || '') + '. Спроси меня о чём угодно!</div>' +
      '</div>';
  }

  function renderMessages(messages) {
    if (!chatMessages) return;
    if (messages.length === 0) {
      showEmptyState(chars[currentCharacter] || {});
      return;
    }
    chatMessages.innerHTML = messages.map(renderMessage).join('');
    scrollToBottom();
  }

  function renderMessage(msg) {
    const isUser = msg.role === 'user';
    const cls = isUser ? 'chat-msg--user' : 'chat-msg--assistant';
    const charInfo = chars[currentCharacter] || {};
    const avatar = isUser ? CFG.childName.charAt(0).toUpperCase() : (charInfo.emoji || '🦉');
    const avatarBg = isUser ? '' : (' style="background:' + (charInfo.color || '#2DD4BF') + ';"');
    const time = formatTime(msg.created_at);
    const imgHtml = msg.image_url
      ? '<img class="chat-msg__image" src="' + escAttr(msg.image_url) + '" alt="image">'
      : '';

    return '<div class="chat-msg ' + cls + '">' +
      '<div class="chat-msg__avatar"' + avatarBg + '>' + avatar + '</div>' +
      '<div>' +
      imgHtml +
      '<div class="chat-msg__bubble">' + formatContent(msg.content) + '</div>' +
      '<div class="chat-msg__time">' + time + '</div>' +
      '</div></div>';
  }

  function showTyping() {
    const info = chars[currentCharacter] || {};
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--assistant';
    el.id = 'typing-indicator';
    el.innerHTML = '<div class="chat-msg__avatar" style="background:' + (info.color || '#2DD4BF') + ';">' + (info.emoji || '🦉') + '</div>' +
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
  async function sendMessage() {
    if (sending) return;
    const text = (chatInput.value || '').trim();
    if (!text && !attachedFile) return;

    // Ensure we have a chat
    if (!currentChatId) {
      try {
        const { status, data } = await api('/api/kid/chats', 'POST', { character_key: currentCharacter });
        if (status === 200 || status === 201) {
          chatIdByCharacter[currentCharacter] = data.chat.id;
          currentChatId = data.chat.id;
        } else return;
      } catch (e) { return; }
    }

    sending = true;
    sendBtn.disabled = true;

    // Show user message
    const userMsg = {
      role: 'user',
      content: text,
      image_url: attachedFile ? URL.createObjectURL(attachedFile) : null,
      created_at: new Date().toISOString(),
    };
    const emptyEl = chatMessages.querySelector('.chat-empty-state');
    if (emptyEl) emptyEl.remove();
    chatMessages.insertAdjacentHTML('beforeend', renderMessage(userMsg));
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
        result = await api('/api/kid/chats/' + currentChatId + '/send', 'POST', fd);
      } else {
        result = await api('/api/kid/chats/' + currentChatId + '/send', 'POST', { message: text });
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
          '<div class="chat-msg chat-msg--assistant"><div class="chat-msg__avatar">' +
          ((chars[currentCharacter] || {}).emoji || '🦉') + '</div>' +
          '<div class="chat-msg__bubble" style="background:#FFF3E0;color:#E8503F;">' +
          escHtml(result.data.message || 'Лимит сообщений на сегодня исчерпан') +
          '</div></div>');
        scrollToBottom();
      }
    } catch (e) {
      hideTyping();
    }

    sending = false;
    updateSendBtn();
  }

  // --- Events ---
  function setupEvents() {
    // Character selection (sidebar + mobile)
    document.querySelectorAll('.ch-persona, .ch-mobile-persona').forEach(el => {
      el.addEventListener('click', () => selectCharacter(el.dataset.key));
    });

    // Input
    chatInput.addEventListener('input', updateSendBtn);
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener('click', sendMessage);

    // File
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

    // Mobile sidebar toggle
    if (btnSidebar) {
      btnSidebar.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active', sidebar.classList.contains('open'));
      });
    }

    if (overlay) {
      overlay.addEventListener('click', closePanels);
    }
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
    if (limitRemaining) limitRemaining.textContent = remaining;
  }

  function closePanels() {
    sidebar.classList.remove('open');
    overlay.classList.remove('active');
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
