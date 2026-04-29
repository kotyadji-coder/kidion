/**
 * chat.js — Kidion chat interface logic.
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

var chatState = 'idle'; // idle | awaiting_input | waiting | result
var selectedType = null; // 'tale' | 'lesson'
var pollingInterval = null;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function getMessagesEl() {
    return document.getElementById('chat-messages');
}

function getInputArea() {
    return document.getElementById('chat-input-area');
}

function getTextarea() {
    return document.getElementById('chat-textarea');
}

function getCrystalsEl() {
    return document.getElementById('crystals-count');
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function appendBotMessage(html) {
    var el = document.createElement('div');
    el.className = 'msg msg--bot';
    el.innerHTML = html;
    getMessagesEl().appendChild(el);
    scrollToBottom();
    return el;
}

function appendUserMessage(text) {
    var el = document.createElement('div');
    el.className = 'msg msg--user';
    el.textContent = text;
    getMessagesEl().appendChild(el);
    scrollToBottom();
    return el;
}

function scrollToBottom() {
    var container = getMessagesEl();
    container.scrollTop = container.scrollHeight;
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

var _typingEl = null;

function showTypingIndicator() {
    if (_typingEl) return;
    var el = document.createElement('div');
    el.className = 'msg msg--bot';
    el.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    getMessagesEl().appendChild(el);
    _typingEl = el;
    scrollToBottom();
}

function hideTypingIndicator() {
    if (_typingEl) {
        _typingEl.remove();
        _typingEl = null;
    }
}

// ---------------------------------------------------------------------------
// Type selection buttons
// ---------------------------------------------------------------------------

function showTypeButtons() {
    var buttonsHtml =
        '<p>Что создадим сегодня?</p>' +
        '<div class="chat-buttons">' +
        '  <button class="chat-btn" onclick="onTypeSelected(\'tale\')">🧸 Создать сказку</button>' +
        '  <button class="chat-btn" onclick="onTypeSelected(\'lesson\')">📚 Создать урок</button>' +
        '</div>';
    appendBotMessage(buttonsHtml);
}

function onTypeSelected(type) {
    selectedType = type;
    chatState = 'awaiting_input';

    var label = type === 'tale' ? '🧸 Создать сказку' : '📚 Создать урок';
    appendUserMessage(label);

    var prompt = type === 'tale'
        ? 'Отлично! Расскажите о ребёнке: возраст, имя (опционально), и что вас беспокоит или какую тему хотите затронуть в сказке.'
        : 'Отлично! Расскажите: предмет или тема, возраст ребёнка, и что именно хотите объяснить или закрепить.';

    appendBotMessage(prompt);
    showInputArea();
}

// ---------------------------------------------------------------------------
// Input area
// ---------------------------------------------------------------------------

function showInputArea() {
    var area = getInputArea();
    area.style.display = '';
    setTimeout(function () {
        getTextarea().focus();
    }, 50);
}

function hideInputArea() {
    getInputArea().style.display = 'none';
}

// ---------------------------------------------------------------------------
// Send message
// ---------------------------------------------------------------------------

function onSendMessage() {
    var textarea = getTextarea();
    var text = textarea.value.trim();
    if (!text || chatState !== 'awaiting_input') return;

    textarea.value = '';
    textarea.style.height = 'auto';
    appendUserMessage(text);
    hideInputArea();

    chatState = 'waiting';
    showTypingIndicator();

    fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: selectedType, question: text })
    })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
        if (data.error === 'insufficient_crystals') {
            hideTypingIndicator();
            appendBotMessage('У вас недостаточно кристаллов для создания. Пополните баланс:');
            showPaymentOptions();
            chatState = 'idle';
        } else if (data.gen_id) {
            startPolling(data.gen_id);
        } else {
            hideTypingIndicator();
            onGenerationError();
        }
    })
    .catch(function () {
        hideTypingIndicator();
        onGenerationError();
    });
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

function startPolling(genId) {
    if (pollingInterval) clearInterval(pollingInterval);

    pollingInterval = setInterval(function () {
        fetch('/api/poll/' + genId)
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            if (data.status === 'done') {
                clearInterval(pollingInterval);
                pollingInterval = null;
                hideTypingIndicator();
                if (data.crystals !== undefined) {
                    updateCrystals(data.crystals);
                }
                onGenerationDone(data);
            } else if (data.status === 'error') {
                clearInterval(pollingInterval);
                pollingInterval = null;
                hideTypingIndicator();
                onGenerationError();
            }
            // pending — keep polling
        })
        .catch(function () {
            // Network error — keep polling, will retry next tick
        });
    }, 3000);
}

// ---------------------------------------------------------------------------
// Result / error handlers
// ---------------------------------------------------------------------------

function onGenerationDone(data) {
    chatState = 'result';
    var url = data.result_url;
    var html =
        'Готово! Вот ваш результат:' +
        '<div class="result-card">' +
        '  <a class="result-card__link" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">🔗 ' + escapeHtml(url) + '</a>' +
        '</div>' +
        '<div class="chat-buttons" style="margin-top:1rem">' +
        '  <button class="chat-btn" onclick="onTypeSelected(\'tale\')">🧸 Ещё сказку</button>' +
        '  <button class="chat-btn" onclick="onTypeSelected(\'lesson\')">📚 Ещё урок</button>' +
        '</div>';
    appendBotMessage(html);
}

function onGenerationError() {
    chatState = 'idle';
    appendBotMessage('Произошла ошибка при создании. Попробуйте ещё раз.');
    showTypeButtons();
}

// ---------------------------------------------------------------------------
// Payment options
// ---------------------------------------------------------------------------

function showPaymentOptions() {
    var packages = [
        { id: '50_50',    crystals: 50,   price: '50 ₽' },
        { id: '300_220',  crystals: 220,  price: '300 ₽' },
        { id: '700_590',  crystals: 590,  price: '700 ₽' },
        { id: '1500_990', crystals: 990,  price: '1500 ₽' },
    ];

    var html = '<div class="payment-options">';
    packages.forEach(function (pkg) {
        html +=
            '<button class="payment-option" onclick="purchasePackage(\'' + pkg.id + '\')">' +
            '  <span>💎 ' + pkg.crystals + ' кристаллов</span>' +
            '  <span>' + pkg.price + '</span>' +
            '</button>';
    });
    html += '</div>';
    appendBotMessage(html);
}

function purchasePackage(packageId) {
    fetch('/api/payment/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_id: packageId })
    })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
        if (data.confirmation_url) {
            window.location.href = data.confirmation_url;
        } else {
            appendBotMessage('Не удалось создать платёж. Попробуйте позже.');
        }
    })
    .catch(function () {
        appendBotMessage('Ошибка соединения. Попробуйте позже.');
    });
}

// ---------------------------------------------------------------------------
// Crystals counter
// ---------------------------------------------------------------------------

function updateCrystals(count) {
    var el = getCrystalsEl();
    if (el) {
        el.textContent = '💎 ' + count;
    }
    // Also update navbar crystals
    var navCrystals = document.querySelector('.navbar__crystals');
    if (navCrystals) {
        navCrystals.textContent = '💎 ' + count;
    }
}

// ---------------------------------------------------------------------------
// Payment return handling (?payment=done in URL)
// ---------------------------------------------------------------------------

function checkPaymentReturn() {
    var params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'done') {
        // Clean URL
        window.history.replaceState({}, '', '/chat');
        appendBotMessage('Оплата прошла успешно! Ваши кристаллы зачислены. Выберите, что создать:');
        showTypeButtons();
    }
}

// ---------------------------------------------------------------------------
// Auto-resize textarea
// ---------------------------------------------------------------------------

function autoResizeTextarea() {
    var textarea = getTextarea();
    if (!textarea) return;
    textarea.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });
    textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSendMessage();
        }
    });
}

// ---------------------------------------------------------------------------
// Escape HTML
// ---------------------------------------------------------------------------

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Send button
// ---------------------------------------------------------------------------

function initSendButton() {
    var btn = document.getElementById('chat-send-btn');
    if (btn) {
        btn.addEventListener('click', onSendMessage);
    }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function chatInit() {
    // Welcome message
    appendBotMessage('Привет! Я Kidion — ваш AI-помощник для создания материалов для детей.');
    showTypeButtons();

    autoResizeTextarea();
    initSendButton();
    checkPaymentReturn();
}
