# Spark Chat — Development Plan

## Architecture Decision: Subdomain on Shared Backend

chat.kidion.ru runs on the same FastAPI app (port 8004) as kidion.ru. Nginx routes both domains to the same backend. Shared: users table, auth cookies (domain=.kidion.ru), crystals, subscriptions. Separate: templates, static files, routes.

---

## Phase 1: Multi-Character Chat (backend)

**Goal:** Support multiple AI characters instead of just Spark.

### DB Changes:
- Add `chat_characters` table: `id, key, name_ru, avatar_url, description_ru, system_prompt, greeting_ru, hints_json, accent_color, bg_color, is_free`
- Modify `kid_chats` table: add `character_key` column (default 'spark')
- Add `chat_reports` table: `id, child_id, chat_id, date, summary, topics_json, created_at`

### Backend:
- Seed 4 characters: Spark (free), Professor Owl, Captain Story, Friend Pixie
- Each character has its own system prompt, greeting, hint buttons
- `POST /api/kid/chat/send` accepts `character_key` param
- `GET /api/kid/chat?character=owl` returns chat for specific character
- `POST /api/kid/chat/clear?character=owl` clears specific character chat
- Characters behind paywall: check subscription before allowing non-Spark chat

### Files to modify:
- `db.py` — new tables, seed data, queries
- `services/kid_chat.py` — multi-character prompts, character selection
- `main.py` — updated API endpoints

**Estimate: ~2 days**

---

## Phase 2: Subdomain Setup (infra + routing)

**Goal:** chat.kidion.ru serves the chat UI independently.

### Nginx:
- Add server block for `chat.kidion.ru` → proxy to 127.0.0.1:8004
- SSL via certbot (same as kidion.ru)

### DNS:
- A-record: `chat.kidion.ru` → 72.56.126.111

### FastAPI routing:
- Add middleware or route prefix to detect subdomain
- Chat subdomain serves its own templates (`templates/spark/`)
- Auth cookies: set domain=`.kidion.ru` so they work on both subdomains
- If user comes from chat.kidion.ru without auth → chat login/register page
- If user comes from kidion.ru → existing kid login flow

### Files to create:
- `templates/spark/` — separate template folder for chat subdomain
- `templates/spark/base.html` — chat-specific base template
- `templates/spark/landing.html` — chat landing page
- `templates/spark/characters.html` — character selection
- `templates/spark/chat.html` — chat interface (evolved from kid/chat.html)

### Files to modify:
- `main.py` — subdomain detection, new routes
- `auth.py` — cookie domain configuration

**Estimate: ~1 day**

---

## Phase 3: Voice Messages (speech-to-text)

**Goal:** Children can speak instead of typing. Critical for ages 6-7.

### Approach:
- Browser Web Speech API (free, no backend cost)
- Fallback: Google Cloud Speech-to-Text API if Web Speech unavailable
- Speech recognition language: ru-RU

### Frontend:
- Microphone button in input area
- Recording state: pulsing circle animation, "Говори, я слушаю!"
- On stop: recognized text inserted into input field
- User can edit before sending

### Backend:
- No backend changes if using Web Speech API
- If fallback needed: `POST /api/kid/chat/voice` accepts audio blob, returns text

### Paywall:
- Voice input only for subscribers (check on frontend, validate on backend)

### Files to create:
- `static/spark/voice.js` — voice recording + recognition logic

### Files to modify:
- Chat template — microphone button UI
- `static/kid/chat.js` (or new `static/spark/chat.js`) — integrate voice

**Estimate: ~1 day**

---

## Phase 4: AI Image Generation in Chat

**Goal:** Character can "draw" pictures when child asks.

### Approach:
- Detect drawing intent in child's message (keywords: "нарисуй", "покажи", "нарисуй мне")
- Generate image via Gemini 2.5 Flash (Vertex AI, same as character images)
- Save to `content/chat_images/`
- Return image_url in chat response

### Safety:
- Image prompt filtered through same safety rules
- Only generate child-safe content
- Reject inappropriate requests with friendly message

### Backend:
- Add `generate_chat_image()` in `services/image_generator.py`
- Modify `kid_chat.py` — detect image requests, call generator
- Response includes both text and image_url

### Frontend:
- Drawing indicator animation (pencil/brush icon)
- Image displayed in message bubble (max 300px width)
- "Download" button under image

### Paywall:
- Image generation only for subscribers

### Files to modify:
- `services/kid_chat.py` — image request detection
- `services/image_generator.py` — chat image generation function
- `main.py` — updated send endpoint to handle images
- Chat template/JS — rendering images, loading state

**Estimate: ~2 days**

---

## Phase 5: Parent Reports

**Goal:** Parent sees summary of what child discussed with AI.

### Approach:
- After each chat session (or daily), generate summary via Gemini
- Extract topics/themes as tags
- Store in `chat_reports` table

### Backend:
- `POST /api/kid/chat/clear` triggers summary generation (background task)
- Daily cron job generates summaries for active chats
- `GET /api/children/{id}/chat-report` — returns reports with summaries
- `GET /api/children/{id}/chat-report/{date}` — full messages for a day

### Frontend (parent interface):
- New page: `/children/{id}/chat-report`
- Stats cards: messages/week, favorite character, top topics
- Daily cards with summaries, expandable to full dialog

### Files to create:
- `templates/chat_report.html` — parent report page
- `services/chat_reports.py` — summary generation logic

### Files to modify:
- `db.py` — chat_reports table + queries
- `main.py` — report API endpoints + page route

**Estimate: ~2 days**

---

## Phase 6: Landing Page + Independent Registration

**Goal:** chat.kidion.ru has its own landing and registration flow.

### Landing:
- Standalone page at chat.kidion.ru for non-authenticated users
- Hero, features, safety, characters, pricing sections
- CTA leads to registration

### Registration:
- Same registration form as kidion.ru (email + password)
- Creates account in shared `users` table
- Grants 60 crystals on registration (same as kidion)
- After registration: simplified flow — add child name + age → start chatting
- Skip universe/character generation (not needed for chat-only users)

### Login:
- Shared auth — if already registered on kidion.ru, same credentials work
- After parent login: child picker (same as kidion) → PIN → chat

### Files to create:
- `templates/spark/landing.html`
- `templates/spark/register.html`
- `templates/spark/login.html`

### Files to modify:
- `main.py` — landing route, simplified registration
- `auth.py` — cross-subdomain cookie

**Estimate: ~2 days**

---

## Phase 7: Chat Subscription from Kidion

**Goal:** Parents can buy chat subscription from both kidion.ru and chat.kidion.ru.

### Already implemented:
- `POST /api/chat/subscribe` — 300 crystals/month
- `GET /api/chat/subscription` — check status
- Subscription stored in `chat_subscriptions` table

### To add:
- Subscription purchase UI on chat.kidion.ru (for chat-only users)
- Cross-promotion: banner in kidion.ru parent dashboard "Try Spark Chat!"
- Cross-promotion: banner in chat.kidion.ru "Try Kidion lessons!"

### Files to modify:
- `templates/spark/` — subscription purchase page
- Parent dashboard template — cross-promo banner

**Estimate: ~1 day**

---

## Summary

| Phase | What | Estimate |
|-------|------|----------|
| 1 | Multi-character chat (backend) | ~2 days |
| 2 | Subdomain setup (infra + routing) | ~1 day |
| 3 | Voice messages (speech-to-text) | ~1 day |
| 4 | AI image generation in chat | ~2 days |
| 5 | Parent reports | ~2 days |
| 6 | Landing + independent registration | ~2 days |
| 7 | Subscription from kidion | ~1 day |

**Dependencies:** Phase 1 → Phase 2 → Phases 3-7 (can be parallelized).

**Priority order:** 1 → 2 → 6 → 3 → 4 → 5 → 7

Rationale: first make multi-character work, then deploy on subdomain with landing, then add premium features (voice, images, reports) that drive subscriptions.
