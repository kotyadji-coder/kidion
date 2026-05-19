# Kidion Security Plan

Status: DRAFT
Date: 2026-05-18
Updated by: Claude Code + Anastasia

---

## Current State Summary

### What already works well
- Passwords hashed with bcrypt
- PINs hashed with bcrypt
- Session tokens signed with itsdangerous (HttpOnly, SameSite=lax)
- Child session expires in 30 min, parent in 30 days
- 10 safety rules in AI chat (_SAFETY_BASE)
- Prompt injection filter (sanitize_message)
- Vertex AI safety filters: BLOCK_LOW_AND_ABOVE on all 4 categories
- Child name NOT sent to Gemini for lessons
- Interest data sanitized before AI
- Full cascade deletion for child profiles
- Privacy policy + Terms of Service pages exist
- Parent can view child chat history (/spark/report)
- Image upload size limit (5 MB)

### Critical gaps
- No rate limiting on login/PIN (brute force risk)
- No PII scrubber before sending to Gemini API
- No security headers (CSP, HSTS, X-Frame-Options)
- No audit logging
- No auto-deletion of old chat data
- No parent account deletion endpoint
- No cookie consent
- No explicit parental consent flow (checkbox at registration)
- No crisis response protocol (suicide/self-harm/abuse detection)
- No output moderation (relies solely on Gemini safety filters)
- Chat history stored indefinitely
- Legal documents need expansion

---

## Full Task List

### BLOCK A: What Claude Code will implement

#### A1. Rate Limiting on Auth Endpoints
**Why:** 4-digit PIN = 10,000 combinations. Without rate limiting, brute force takes minutes.
**Plan:**
- Add in-memory rate limiter (IP + endpoint based)
- Login: max 5 attempts per IP per 5 minutes
- PIN auth: max 5 attempts per child per 5 minutes
- Forgot password: max 3 per email per hour
- Return 429 Too Many Requests on exceed
- Log rate limit hits

#### A2. Security Headers Middleware
**Why:** Missing CSP, HSTS, X-Frame-Options = clickjacking, XSS, mixed content risks.
**Plan:**
- Add FastAPI middleware for all responses
- Content-Security-Policy (strict, allow only own domain + google fonts)
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Strict-Transport-Security (in production)
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: restrict camera, microphone, geolocation

#### A3. PII Scrubber Before External AI Calls
**Why:** Child messages go to Gemini API (Google, USA). Must strip personal data.
**Plan:**
- Create services/pii_scrubber.py
- Regex patterns for Russian + English:
  - Phone numbers (8-xxx, +7-xxx, international)
  - Email addresses
  - URLs / links
  - Street addresses (ул., д., кв., проспект, etc.)
  - School names (школа №, гимназия, лицей)
  - Full names (surname patterns: -ов/-ова/-ин/-ина/-ский/-ская + capitalized word sequences)
  - Document numbers
  - Social media handles (@username)
- Replace detected PII with [УДАЛЕНО]
- Apply to: chat messages, interests, any text sent to Gemini
- Log PII detection events (without the PII itself)

#### A4. Crisis Response System
**Why:** Children may disclose abuse, suicidal thoughts, self-harm. Model must respond safely.
**Plan:**
- Create services/crisis_detector.py
- Keyword + pattern matching for Russian crisis topics:
  - Self-harm / suicide: "хочу умереть", "режу себя", "не хочу жить", etc.
  - Abuse: "меня бьют", "ко мне пристают", "боюсь идти домой"
  - Bullying: "меня травят", "издеваются"
  - Danger: "хочу отомстить", "хочу сделать бомбу"
  - Substances: "где купить", "наркотики"
- For each category: safe, empathetic response template in Russian
- Response pattern: validate feelings + don't panic + talk to trusted adult + helpline info
- Helpline: 8-800-2000-122 (Детский телефон доверия, free, 24/7)
- If crisis detected: skip AI call entirely, return template
- Log crisis detection events (category only, no message text)
- Add crisis flag to parent report view

#### A5. Output Moderation Layer
**Why:** Gemini safety filters are good but not perfect. Need our own post-check.
**Plan:**
- Create services/output_moderator.py
- Check AI responses for:
  - Leaked PII (same patterns as scrubber)
  - URLs / links (should never appear)
  - Phone numbers / emails in response
  - Profanity (Russian mat dictionary)
  - Dangerous content patterns
- If unsafe: replace with safe fallback message
- Log moderation events

#### A6. Audit Logging
**Why:** No visibility into security events. Required for incident response.
**Plan:**
- Create services/audit.py
- Log to SQLite table `audit_log`:
  - timestamp, event_type, user_id, child_id, ip, details
- Events to log:
  - login_success, login_failed
  - pin_success, pin_failed
  - rate_limit_hit
  - pii_detected (no PII content, just count/type)
  - crisis_detected (category only)
  - output_moderated
  - account_deleted
  - child_deleted
  - consent_given, consent_revoked
  - chat_cleared
- Auto-cleanup: delete audit entries older than 90 days
- No raw message content in audit log

#### A7. Chat Data Retention & Auto-Cleanup
**Why:** Chat history stored indefinitely. Violates data minimization.
**Plan:**
- Add retention policy: auto-delete chat messages older than 90 days
- Add db function: cleanup_old_chat_messages()
- Run on app startup + daily (background task)
- Parent can manually clear child's chat history
- Log cleanup events in audit

#### A8. Parent Account Deletion
**Why:** Currently requires manual support contact. Must be self-service.
**Plan:**
- Add DELETE /api/account endpoint
- Cascade: delete all children (with their cascade) + user record
- Require password confirmation
- Clear session cookie
- Log in audit

#### A9. Parental Consent Flow
**Why:** Service processes children's data. Need explicit consent from parent.
**Plan:**
- Add consent_version and consent_given_at to users table
- At registration: checkbox "I confirm I am parent/legal representative and consent to processing my child's data per Privacy Policy"
- Store consent timestamp + policy version
- If consent not given: block child creation
- Add consent revocation = account deletion
- Show consent status in parent profile

#### A10. Enhanced Legal Pages
**Why:** Current pages are basic. Need expansion for RF compliance.
**Plan:**
- Expand Privacy Policy with:
  - Full list of collected data types
  - External AI provider disclosure (Google Gemini, USA)
  - Data retention periods (90 days chat, 30 days sessions)
  - Parental rights section
  - Deletion procedure
  - Contact for privacy requests
  - Cookie usage description
- Expand Terms with:
  - Age restriction (6-10, parent required)
  - AI disclaimer (not a replacement for teacher/psychologist)
  - Prohibited use
  - Content generated by AI disclaimer
- Add Cookie Policy section
- Add age gate notice

#### A11. Content Report / Complaint Button
**Why:** Parents and children need a way to flag bad AI responses.
**Plan:**
- Add "Report this message" button in chat UI
- POST /api/kid/chat/report with message_id + reason
- Store in content_reports table (already exists — verify and extend)
- Show reports in parent dashboard
- Log in audit

#### A12. Weak PIN Prevention
**Why:** "0000", "1234", "1111" are trivially guessable.
**Plan:**
- Block common PINs: 0000, 1111, 2222...9999, 1234, 4321, 0123, etc.
- Block sequential (1234, 2345, 3456...)
- Block repeated (1122, 1212, etc.)
- Show error: "Выберите более надёжный код"

---

### BLOCK A — STATUS: DONE (2026-05-18)

All 12 technical tasks implemented and committed: `6a52890`.

---

### BLOCK B: What Anastasia needs to do

#### B1. Найти IT-юриста (САМОЕ ВАЖНОЕ)
- [ ] Найти юриста, который специализируется на 152-ФЗ / детских сервисах / IT
- [ ] Задать ему 5 ключевых вопросов:
  1. **Трансграничная передача** — можно ли передавать обезличенные данные детей в Google Gemini API (США)? Что для этого нужно юридически?
  2. **Модель согласия** — достаточно ли чекбокса при регистрации или нужен отдельный документ? Нужна ли подпись / верификация родителя?
  3. **Регистрация в РКН** — нужно ли подавать уведомление оператора ПДн в Роскомнадзор?
  4. **Возрастная маркировка** — какую маркировку ставить по 436-ФЗ (6+/12+)? Как правильно описать сервис?
  5. **Политика конфиденциальности** — попросить проверить текущую (шаблон уже есть на сайте /privacy) и сказать, что доработать
- [ ] Получить письменное заключение или хотя бы список рекомендаций
- **Где искать:** Яндекс "юрист 152-ФЗ", профильные группы, рекомендации. Можно на Авито/Профи.ру.
- **Бюджет:** 15 000 - 30 000 руб за консультацию
- **Когда:** ДО публичного запуска (до первых реальных пользователей)

#### B2. Проверить условия Google Gemini API — DONE (2026-05-19)
- [x] Открыть страницу условий Google AI Studio
- [x] Найти раздел про использование данных для обучения
- [x] Проверить, есть ли Data Processing Agreement (DPA)
- [x] Записать результат

**Результат проверки (https://ai.google.dev/gemini-api/terms):**
1. **Обучение на данных:** Free tier — ДА (данные используются для обучения). Paid tier — НЕТ. **Kidion ДОЛЖЕН использовать платный тариф.**
2. **DPA:** Есть для платного тарифа ("Data Processing Addendum for Products Where Google is a Data Processor").
3. **ПРОБЛЕМА — запрет для <18 лет:** Terms запрещают использование в сервисах "directed towards or likely to be accessed by individuals under the age of 18". Kidion формально нарушает это условие.
4. **Хранение:** Платный тариф — логирование на ограниченный срок только для выявления нарушений.
5. **Возможные решения:** (a) юридическая позиция "оператор — родитель 18+, ребёнок через родительский аккаунт, PII удалён"; (b) Vertex AI с Enterprise контрактом; (c) фоллбэк на YandexGPT/GigaChat. **Обсудить с юристом (B1).**

#### B3. Уведомление в Роскомнадзор
- [ ] Юрист скажет, нужно ли. Если да:
- [ ] Зайти на pd.rkn.gov.ru
- [ ] Подать уведомление об обработке ПДн
- [ ] Указать себя ответственным за обработку
- **Когда:** По результатам консультации юриста

#### B4. Юридическое лицо
- [ ] Решить: ИП или ООО
- [ ] Зарегистрировать (если ещё нет)
- [ ] Это нужно для: приёма платежей, указания в документах, работы с ЮKassa
- **Когда:** ДО приёма реальных платежей

#### B5. ЮKassa — реальные ключи
- [ ] Зарегистрироваться в ЮKassa (yookassa.ru) как ИП/ООО
- [ ] Получить реальные SHOP_ID и SECRET_KEY
- [ ] Включить фискализацию (отправка чеков) — это обязательно по закону
- [ ] Прислать ключи — я пропишу их в .env на сервере
- **Когда:** Когда будет юр. лицо

#### B6. Почта поддержки
- [ ] Создать support@kidion.ru (или настроить пересылку на личную почту)
- [ ] Эта почта уже указана в политике конфиденциальности на сайте
- [ ] Туда будут приходить запросы на удаление данных и жалобы
- **Когда:** ДО публичного запуска

#### B7. Проверить SSL и cookie на продакшене
- [ ] Зайти на kidion.ru, проверить что замочек в браузере есть
- [ ] Попросить меня проверить COOKIE_SECURE=true в .env на сервере (напиши мне "проверь cookie secure на сервере")
- **Когда:** После деплоя этих изменений

#### B8. Бэкапы базы данных
- [ ] Напиши мне "настрой бэкапы" — я сделаю cron-скрипт на сервере
- [ ] Бэкапы будут храниться на том же VPS (в России)
- **Когда:** ДО публичного запуска

#### B9. Red team тестирование (вместе со мной)
- [ ] Когда всё задеплоено — напиши мне "давай протестируем безопасность чата"
- [ ] Я подготовлю тестовые сценарии на русском языке:
  - Детский сленг и транслит
  - Попытки вытащить персональные данные
  - Кризисные темы
  - Prompt injection
  - Обход фильтров
- [ ] Пройдём вместе, я буду фиксить то, что пробьётся
- **Когда:** После деплоя

#### B10. Деплой на сервер
- [ ] Напиши мне "задеплой" — я обновлю код на VPS
- **Когда:** Когда будешь готова

---

### BLOCK B — Порядок действий (что сначала)

| # | Задача | Срочность | Время |
|---|--------|-----------|-------|
| 1 | B10. Деплой | Сейчас | 5 мин (делаю я) |
| 2 | B6. Почта support@kidion.ru | Эта неделя | 10 мин |
| 3 | B2. Проверить условия Google API | Эта неделя | 15 мин |
| 4 | B7. Проверить SSL/cookies | После деплоя | 2 мин |
| 5 | B8. Бэкапы | Эта неделя | 5 мин (делаю я) |
| 6 | B1. Юрист | До запуска | 1-2 недели |
| 7 | B9. Red team тест | После деплоя | 1 час (вместе) |
| 8 | B4. Юр. лицо | До платежей | 1-4 недели |
| 9 | B5. ЮKassa | После юр. лица | 1 неделя |
| 10 | B3. РКН | После юриста | По ситуации |

---

### BLOCK C: На будущее (при масштабировании)

- ML-based PII detector (вместо regex)
- Модерационная очередь с human review
- Расширенный родительский кабинет (лимиты времени, блокировка персонажей)
- Rate limiting через Redis (вместо in-memory)
- Структурированное логирование
- SIEM / мониторинг безопасности
- Пентест внешней командой
- Регулярные аудиты безопасности
- Bug bounty программа
- DDoS защита (Cloudflare)
- Шифрование БД at rest
- Incident response playbook
- Регулярные аудиты хранения данных
