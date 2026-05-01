/**
 * Kidion — Kid Chat JS
 */

(function() {
  const CFG = window.KID_CHAT || {};
  const chars = CFG.characters || {};

  let currentChatId = null;
  let currentCharacter = 'owl';
  let chats = [];
  let sending = false;
  let attachedFile = null;

  // DOM
  const chatList = document.getElementById('chat-list');
  const chatMessages = document.getElementById('chat-messages');
  const chatEmpty = document.getElementById('chat-empty');
  const chatTitle = document.getElementById('chat-title');
  const inputArea = document.getElementById('chat-input-area');
  const textarea = document.getElementById('chat-textarea');
  const sendBtn = document.getElementById('chat-send-btn');
  const btnNewChat = document.getElementById('btn-new-chat');
  const fileInput = document.getElementById('file-input');
  const attachPreview = document.getElementById('attach-preview');
  const attachThumb = document.getElementById('attach-thumb');
  const btnRemoveAttach = document.getElementById('btn-remove-attach');
  const limitInfo = document.getElementById('chat-limit-info');
  const charDesc = {
    emoji: document.getElementById('desc-emoji'),
    name: document.getElementById('desc-name'),
    text: document.getElementById('desc-text'),
  };

  // Mobile toggles
  const sidebar = document.getElementById('chat-sidebar');
  const characters = document.getElementById('chat-characters');
  const btnSidebar = document.getElementById('btn-toggle-sidebar');
  const btnChars = document.getElementById('btn-toggle-characters');

  // Create overlay element
  const overlay = document.createElement('div');
  overlay.className = 'chat-overlay';
  document.body.appendChild(overlay);

  // --- Init ---
  loadChats();
  setupEvents();

  // --- API helpers ---
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

  // --- Load chats ---
  async function loadChats() {
    try {
      const { data } = await api('/api/kid/chats', 'GET');
      chats = data.chats || [];
      renderChatList();
    } catch (e) {
      console.error('Failed to load chats:', e);
    }
  }

  function renderChatList() {
    if (!chatList) return;
    if (chats.length === 0) {
      chatList.innerHTML = '<div style="padding:20px;text-align:center;color:var(--color-muted);font-size:14px;font-weight:600;">Пока нет чатов</div>';
      return;
    }
    chatList.innerHTML = chats.map(c => {
      const charEmoji = (chars[c.character_key] || {}).emoji || '\u{1f989}';
      const active = c.id === currentChatId ? ' chat-list-item--active' : '';
      const date = formatDate(c.updated_at);
      return `
        <button class="chat-list-item${active}" data-id="${c.id}">
          <span class="chat-list-item__emoji">${charEmoji}</span>
          <span class="chat-list-item__info">
            <div class="chat-list-item__title">${escHtml(c.title)}</div>
            <div class="chat-list-item__date">${date}</div>
          </span>
          <span class="chat-list-item__delete" data-delete="${c.id}" title="Удалить">&#128465;</span>
        </button>
      `;
    }).join('');

    // Attach events
    chatList.querySelectorAll('.chat-list-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('[data-delete]')) return;
        openChat(parseInt(el.dataset.id, 10));
        closePanels();
      });
    });
    chatList.querySelectorAll('[data-delete]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteChat(parseInt(el.dataset.delete, 10));
      });
    });
  }

  // --- Open chat ---
  async function openChat(chatId) {
    currentChatId = chatId;
    const chat = chats.find(c => c.id === chatId);
    if (chat) {
      currentCharacter = chat.character_key || 'owl';
      chatTitle.textContent = chat.title;
      updateCharacterUI(currentCharacter);
    }
    inputArea.style.display = '';
    renderChatList();

    // Load messages
    try {
      const { data } = await api(`/api/kid/chats/${chatId}/messages`, 'GET');
      renderMessages(data.messages || []);
      updateLimitInfo(data.daily_count, data.daily_limit);
    } catch (e) {
      console.error('Failed to load messages:', e);
    }
  }

  function renderMessages(messages) {
    if (!chatMessages) return;
    if (messages.length === 0) {
      const charInfo = chars[currentCharacter] || chars.owl;
      chatMessages.innerHTML = `
        <div class="chat-empty-state">
          <div class="chat-empty-state__icon">${charInfo.emoji}</div>
          <div class="chat-empty-state__text">Привет! Я ${charInfo.name_ru}. Спроси меня о чём угодно!</div>
        </div>
      `;
      return;
    }

    chatMessages.innerHTML = messages.map(m => renderMessage(m)).join('');
    scrollToBottom();
  }

  function renderMessage(msg) {
    const isUser = msg.role === 'user';
    const cls = isUser ? 'chat-msg--user' : 'chat-msg--assistant';
    const charInfo = chars[currentCharacter] || chars.owl;
    const avatar = isUser
      ? CFG.childName.charAt(0).toUpperCase()
      : charInfo.emoji;
    const time = formatTime(msg.created_at);
    const imgHtml = msg.image_url
      ? `<img class="chat-msg__image" src="${escAttr(msg.image_url)}" alt="image">`
      : '';

    return `
      <div class="chat-msg ${cls}">
        <div class="chat-msg__avatar">${avatar}</div>
        <div>
          ${imgHtml}
          <div class="chat-msg__bubble">${formatContent(msg.content)}</div>
          <div class="chat-msg__time">${time}</div>
        </div>
      </div>
    `;
  }

  function showTyping() {
    const charInfo = chars[currentCharacter] || chars.owl;
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--assistant';
    el.id = 'typing-indicator';
    el.innerHTML = `
      <div class="chat-msg__avatar">${charInfo.emoji}</div>
      <div class="chat-msg__bubble chat-typing">
        <span class="chat-typing__dot"></span>
        <span class="chat-typing__dot"></span>
        <span class="chat-typing__dot"></span>
      </div>
    `;
    chatMessages.appendChild(el);
    scrollToBottom();
  }

  function hideTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  // --- Create chat ---
  async function createNewChat() {
    try {
      const { status, data } = await api('/api/kid/chats', 'POST', { character_key: currentCharacter });
      if (status === 200 || status === 201) {
        chats.unshift(data.chat);
        renderChatList();
        openChat(data.chat.id);
        closePanels();
      }
    } catch (e) {
      console.error('Failed to create chat:', e);
    }
  }

  // --- Delete chat ---
  async function deleteChat(chatId) {
    try {
      await api(`/api/kid/chats/${chatId}`, 'DELETE');
      chats = chats.filter(c => c.id !== chatId);
      if (currentChatId === chatId) {
        currentChatId = null;
        chatTitle.textContent = 'Выбери чат';
        chatMessages.innerHTML = `
          <div class="chat-empty-state" id="chat-empty">
            <div class="chat-empty-state__icon">&#128172;</div>
            <div class="chat-empty-state__text">Выбери чат слева или создай новый!</div>
          </div>
        `;
        inputArea.style.display = 'none';
      }
      renderChatList();
    } catch (e) {
      console.error('Failed to delete chat:', e);
    }
  }

  // --- Send message ---
  async function sendMessage() {
    if (sending) return;
    const text = textarea.value.trim();
    if (!text && !attachedFile) return;
    if (!currentChatId) return;

    sending = true;
    sendBtn.disabled = true;

    // Show user message immediately
    const userMsg = {
      role: 'user',
      content: text,
      image_url: attachedFile ? URL.createObjectURL(attachedFile) : null,
      created_at: new Date().toISOString(),
    };

    // Remove empty state if present
    const emptyEl = chatMessages.querySelector('.chat-empty-state');
    if (emptyEl) emptyEl.remove();

    chatMessages.insertAdjacentHTML('beforeend', renderMessage(userMsg));
    scrollToBottom();

    textarea.value = '';
    textarea.style.height = 'auto';
    clearAttach();

    showTyping();

    try {
      let result;
      if (attachedFile) {
        const formData = new FormData();
        formData.append('message', text);
        formData.append('image', attachedFile);
        result = await api(`/api/kid/chats/${currentChatId}/send`, 'POST', formData);
      } else {
        result = await api(`/api/kid/chats/${currentChatId}/send`, 'POST', { message: text });
      }

      hideTyping();

      if (result.status === 200) {
        const assistantMsg = {
          role: 'assistant',
          content: result.data.response,
          created_at: new Date().toISOString(),
        };
        chatMessages.insertAdjacentHTML('beforeend', renderMessage(assistantMsg));
        scrollToBottom();

        // Update chat title if it was auto-generated
        if (result.data.title) {
          const chat = chats.find(c => c.id === currentChatId);
          if (chat) {
            chat.title = result.data.title;
            chatTitle.textContent = result.data.title;
          }
          renderChatList();
        }

        // Update limit info
        if (result.data.daily_count !== undefined) {
          updateLimitInfo(result.data.daily_count, result.data.daily_limit);
        }
      } else if (result.status === 429) {
        chatMessages.insertAdjacentHTML('beforeend', `
          <div class="chat-msg chat-msg--assistant">
            <div class="chat-msg__avatar">${(chars[currentCharacter] || chars.owl).emoji}</div>
            <div class="chat-msg__bubble" style="background:#FFF3E0;color:#E17055;">
              ${escHtml(result.data.message || 'Лимит сообщений на сегодня исчерпан')}
            </div>
          </div>
        `);
        scrollToBottom();
      } else {
        chatMessages.insertAdjacentHTML('beforeend', `
          <div class="chat-msg chat-msg--assistant">
            <div class="chat-msg__avatar">${(chars[currentCharacter] || chars.owl).emoji}</div>
            <div class="chat-msg__bubble" style="background:#FFF3E0;color:#E17055;">
              ${escHtml(result.data.message || result.data.error || 'Что-то пошло не так')}
            </div>
          </div>
        `);
        scrollToBottom();
      }
    } catch (e) {
      hideTyping();
      console.error('Send error:', e);
    }

    sending = false;
    updateSendBtn();
  }

  // --- Character selection ---
  function updateCharacterUI(key) {
    const info = chars[key] || chars.owl;
    document.querySelectorAll('.character-card').forEach(el => {
      el.classList.toggle('character-card--active', el.dataset.key === key);
    });
    if (charDesc.emoji) charDesc.emoji.textContent = info.emoji;
    if (charDesc.name) charDesc.name.textContent = info.name_ru;
    if (charDesc.text) charDesc.text.textContent = info.description_ru;
  }

  // --- Events ---
  function setupEvents() {
    btnNewChat.addEventListener('click', createNewChat);

    textarea.addEventListener('input', () => {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
      updateSendBtn();
    });

    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener('click', sendMessage);

    // File attachment
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

    // Character selection
    document.querySelectorAll('.character-card').forEach(el => {
      el.addEventListener('click', () => {
        currentCharacter = el.dataset.key;
        updateCharacterUI(currentCharacter);
      });
    });

    // Mobile toggles
    btnSidebar.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      characters.classList.remove('open');
      overlay.classList.toggle('active', sidebar.classList.contains('open'));
    });

    btnChars.addEventListener('click', () => {
      characters.classList.toggle('open');
      sidebar.classList.remove('open');
      overlay.classList.toggle('active', characters.classList.contains('open'));
    });

    overlay.addEventListener('click', closePanels);
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
    sendBtn.disabled = sending || (!textarea.value.trim() && !attachedFile);
  }

  function updateLimitInfo(count, limit) {
    if (!limitInfo) return;
    const remaining = Math.max(0, limit - count);
    limitInfo.textContent = `Сообщений сегодня: ${count} / ${limit}`;
    if (remaining <= 3 && remaining > 0) {
      limitInfo.style.color = '#E17055';
    } else if (remaining === 0) {
      limitInfo.style.color = '#E17055';
      limitInfo.textContent += ' (лимит исчерпан)';
    } else {
      limitInfo.style.color = '';
    }
  }

  function closePanels() {
    sidebar.classList.remove('open');
    characters.classList.remove('open');
    overlay.classList.remove('active');
  }

  function scrollToBottom() {
    if (chatMessages) {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escAttr(str) {
    return escHtml(str).replace(/"/g, '&quot;');
  }

  function formatContent(text) {
    // Simple markdown: **bold**, *italic*, newlines
    let html = escHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    html = html.replace(/\*(.+?)\*/g, '<i>$1</i>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const today = now.toDateString();
    const dateStr = d.toDateString();
    if (dateStr === today) return 'Сегодня';
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (dateStr === yesterday.toDateString()) return 'Вчера';
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  }

  function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
})();
