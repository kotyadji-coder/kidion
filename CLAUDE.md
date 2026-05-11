# Kidion — Project Context

## Rules

- **All documentation in English**, regardless of the language the user writes in.
- **Prompts (AI generation prompts) stay in Russian** — they are part of the product logic.
- **Keep this file updated** as the project evolves. Auto-update after significant changes.
- **Size limit: 200–300 lines** (optimal), max 400. Beyond 400 lines the model loses focus on instructions. Move details to `.claude/handoff/` or `docs/` if needed.
- **Do NOT modify** files outside `/Users/anastasiamisenko/Documents/projects/kidion/`.
- **Do NOT modify** the original `school-bot` or `tales` projects — generation logic is copied into `services/`.

## What This Is

**kidion.ru** — a personalized educational platform for children ages 6–10. Parents create child profiles with interests, AI generates a personalized universe and character, then creates interactive lessons set in that universe. Children access lessons through a kid-friendly interface with PIN login, earn stars, and spend them on character customization.

### Core Flow
Parent creates child (name, grade, interests) → AI generates universe + character + shop → parent generates lessons → child completes them → earns stars → customizes character in star shop.

## Stack

- **Backend:** FastAPI + uvicorn + SQLite (sqlite3, no ORM)
- **Frontend:** Jinja2 templates + vanilla JS (no React/Vue)
- **Auth:** bcrypt (passwords) + itsdangerous (signed cookies `kid_session` for parents, `kid_session_child` for kids)
- **AI Generation:** Google Vertex AI (Gemini 3.1 Pro for text, Gemini 2.5 Flash for images and kid chat)
- **Payments:** YooKassa Python SDK (not yet connected with real keys)
- **Tests:** pytest + pytest-asyncio + httpx (306 tests)

## File Structure

```
kidion/
├── main.py                    # FastAPI app, all routes (~3000 lines)
├── db.py                      # SQLite: 17 tables, all CRUD functions
├── auth.py                    # bcrypt, session tokens (parent + child)
├── payments.py                # YooKassa integration, crystal packages
├── referral.py                # Referral codes, bonuses
├── callbacks.py               # HMAC validation for legacy bot callbacks
├── services/
│   ├── generation.py          # Generation Adapter: build_question() + generate_lesson_content()
│   ├── gemini_client.py       # Vertex AI calls (stub mode without GOOGLE_CLOUD_PROJECT)
│   ├── prompts.py             # Russian prompts for Methodologist + Tutor-Gamer
│   ├── image_generator.py     # Gemini 2.5 Flash lesson image generation
│   ├── content_generator.py   # Saves lesson HTML/PNG/JSON to content/
│   ├── curricula.py           # Load/search curriculum JSON files
│   ├── universe.py            # Universe/character/shop generation (Gemini)
│   ├── kid_chat.py            # Spark AI chat: single character, safety prompts, Gemini 2.5 Flash
│   └── worksheet/             # Printable worksheet generation (from metodist)
│       ├── models.py           # Pydantic models: 24 task types + 3 activities
│       ├── prompts.py          # Prompts for worksheet/activity generation
│       ├── grids.py            # Word search & crossword grid builders
│       └── generator.py        # Orchestrates generation, renders HTML, stubs
├── templates/worksheets/
│   ├── worksheet.html          # 4-task A4 worksheet (lessons 1-4)
│   ├── base_activity.html      # Base for full-page activities
│   ├── cipher.html             # Cipher activity (lesson 5)
│   ├── cafe.html               # Cafe activity (lesson 5, math)
│   └── shop.html               # Shop activity (lesson 5, math)
├── templates/kid/
│   ├── base.html              # Kid base template (nav: home, name, stars, logout)
│   ├── login.html             # Child picker cards + PIN keyboard
│   ├── onboarding.html        # First-login: name the character
│   ├── home.html              # Kid home: character avatar + subjects + streak + shop btn
│   ├── character.html         # RPG character page + star shop + name editing + speech bubble
│   ├── subject_map.html       # Duolingo-style vertical lesson map with tooltip
│   ├── chat.html              # Spark AI chat (single assistant, simple layout)
│   ├── lesson.html            # Lesson iframe + auto-score via postMessage
│   └── result.html            # Stars animation + confetti + shop button
├── static/kid/style.css       # Kid CSS (Nunito, pastels, mobile-first)
├── static/kid/img/spark.png   # Spark avatar image
├── static/kid/chat.js         # Chat page JS (CRUD, send, typing, attachments)
├── content/                   # Generated lesson HTML/PNG + characters/ (gitignored)
├── content/characters/        # Generated character PNGs: {child_id}.png
└── tests/                     # 306 tests across 16 test files
```

## Database Schema (20 tables)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `users` | Parent accounts | email, password_hash, crystals, ref_code |
| `children` | Child profiles | parent_id, name, gender, grade, universe, pin_hash, difficulty_level, **stars**, **interests** (JSON), **universe_description**, **character_prompt**, **character_image_url**, **character_name**, **character_onboarded** |
| `lessons` | All lessons | child_id, mode, topic_title, subject, status, worksheet_url |
| `lesson_results` | Completion results | lesson_id, child_id, correct_answers, stars (1-3) |
| `curriculum_topics` | Seeded topics (12 per subject/grade) | subject, grade, theme_order, title_ru, icon |
| `curriculum_lessons` | Seeded lessons (5 per topic) | topic_id, lesson_order, title_ru |
| `child_lesson_progress` | Per-child progress | child_id, curriculum_lesson_id, status, stars_earned |
| `**shop_items**` | **Per-child shop catalog** (AI-generated) | child_id, category, title_ru, emoji, price_stars |
| `**child_items**` | **Purchased/equipped items** | child_id, item_id, equipped |
| `streaks` | Daily activity streaks | child_id, current_streak, longest_streak |
| `curriculum_templates` | FGOS curricula (legacy JSON) | subject, grade, topics_json |
| `curriculum_enrollments` | Program routes (legacy) | child_id, curriculum_id, current_topic_index |
| `weekly_plans` | Weekly topic plans | child_id, curriculum_id, topic_ids_json |
| `transactions` | Crystal transaction log | user_id, delta, reason |
| `payments` | YooKassa payments | user_id, yookassa_payment_id, amount_rub, crystals, status |
| `generations` | Legacy generation records | user_id, type, status, result_url |
| `referrals` | Referral relationships | referrer_id, referred_id |
| `kid_chats` | Kid AI chat sessions | child_id, character_key, title |
| `kid_chat_messages` | Chat messages | chat_id, role (user/assistant), content, image_url |
| `chat_subscriptions` | Chat subscription (parent) | user_id, started_at, expires_at |

## Personalized Universe & Character System

### Child Creation Flow
1. Parent fills form: name, gender, grade, **interests** (free text, comma-separated)
2. `POST /api/children` creates child record, then fires `_setup_child_universe()` as background task
3. Background task calls `services/universe.py`:
   - `generate_universe()` → Gemini generates universe_description + character_prompt (stored in children table)
   - `generate_character_image()` → Gemini Flash generates PNG → saved to `content/characters/{child_id}.png`
   - `generate_shop_items()` → Gemini generates ~20 themed items → saved to `shop_items` table

### Stub Mode
All generation functions return predefined defaults when `GOOGLE_CLOUD_PROJECT` is not set. Character image returns `None` (UI shows placeholder).

### Kid Onboarding (`/kid/onboarding`)
- First login redirects here if `character_onboarded=0`
- Shows character image + speech bubble: "Привет! Я твой новый друг. Как меня зовут?"
- Child enters character name (default: "Искатель") → `POST /api/kid/character/name`
- Sets `character_onboarded=1`, redirects to `/kid/home`

### Character Page (`/kid/character`)
- Left: character PNG + **character name with edit pencil** + speech bubble (contextual phrases based on star count)
- Right: star shop with category tabs (outfit, accessory, pet, background, special)
- Buying item: deducts stars → creates `child_items` record → triggers background character regeneration
- Insufficient stars: grey button, tooltip on click "Нужно еще немного поучиться!"
- Equip/unequip: toggles `child_items.equipped` → triggers background character regeneration

### Kid Login (`/kid/login`)
- Multi-child: shows child picker cards (avatar + name), click → PIN keyboard
- Single child: shows avatar + PIN keyboard directly
- PIN label: "Введи свой секретный код"

### Shop Item Categories & Pricing
- outfit (5 items, 5-20 stars), accessory (5 items, 10-25 stars), pet (4 items, 20-40 stars), background (3 items, 15-30 stars), special (3 items, 30-50 stars)

## Two Currencies

- **Crystals**: Parent currency. Bought with real money, spent on lesson generation and chat subscription. Child never sees crystals.
- **Stars**: Child currency. Earned by completing lessons (+1 per correct task, max 5 per lesson). Spent in character shop. Stored in `children.stars`.

## Kid AI Chat System

### Spark — Single AI Assistant
One universal character **Spark** (friendly fire creature in glasses and purple robe). Avatar: `static/kid/img/spark.png`.
- Single chat per child, auto-created on first visit
- No chat list, no character selection — just open and talk
- DB keeps only last 30 messages (auto-trimmed on insert)
- "New conversation" button clears message history

### Safety
- Strict system prompt: no violence, politics, adult content, no personal data requests
- Gemini safety filters at `BLOCK_LOW_AND_ABOVE`
- Input sanitization against prompt injection
- Responses adapted for ages 6-10

### Subscription & Limits
- **Free:** 5 messages/day per parent account (all children share)
- **Subscription:** 300 crystals/month → 50 messages/day
- Limits counted across all children of the same parent
- Subscription bought on `/buy` page (parent auth)

### Chat API
- `GET /api/kid/chat` — get chat + messages + limits
- `POST /api/kid/chat/send` — send message, get AI response
- `POST /api/kid/chat/clear` — clear history (new conversation)

## Key Business Logic

- **Crystals:** 60 on registration (120 with referral). Prices: 1 lesson=20, 1 topic (5 lessons)=100, 1 month (20 lessons)=400. Skip test=FREE. **First 1 lesson per subject=FREE** (auto-generated on first enrollment).
- **Stars:** +1 per correct task (5 tasks = 5 max per lesson).
- **Packages:** 60/60 rub, 360/320 rub, 600/490 rub, 1000/800 rub
- **Adaptive difficulty** (1-3): auto-adjusts based on last 2 lesson results
- **Auto-scoring:** iframe postMessage → auto-submit result. Stub mode → 5/5.
- **Chat subscription:** 300 crystals/month, 50 msg/day (5 free). Per account, all children.

## API Endpoints

### Auth
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`

### Children (parent auth)
- CRUD: `POST /api/children` (max 3, accepts `interests: list[str]`), `GET`, `PUT`, `DELETE`
- Progress: `/stats`, `/lessons`, `/program-progress`, `/curriculum/{subject}`, `/free-lessons`, `/enrolled-subjects`, `/subject-progress/{subject}`
- Actions: `/enroll-subject` (auto-generates first 4 lessons FREE), `/skip-test` (inline fullscreen test), `/generate-topic`, `/generate-month`

### Kid Interface (child auth via PIN)
- Auth: `POST /api/kid/auth`, `POST /api/kid/logout`
- Data: `GET /api/kid/me` (includes character_image_url, universe_description), `/lessons`, `/lessons/{id}`, `/subjects`, `/subject/{s}/map`, `/free-lessons`
- Actions: `POST /api/kid/lessons/{curriculum_lesson_id}/start`
- **Character & Shop:** `GET /api/kid/character`, `POST /api/kid/character/name`, `POST /api/kid/shop/buy/{item_id}`, `POST /api/kid/shop/equip/{item_id}`
- **Chat:** `GET /api/kid/chat`, `POST /api/kid/chat/send`, `POST /api/kid/chat/clear`

### Payments & Lessons (parent auth)
- `POST /api/lessons/generate`, `POST /api/lessons/generate-topic`, `GET /api/lessons/{id}/poll`, `POST /api/lessons/{id}/result`
- `POST /api/payment/create`, `POST /api/payment/webhook`, `GET /api/payment/status/{id}`
- `GET /api/children/{id}/worksheets?topic_id=X` — batch print worksheets for topic (5 pages)
- `GET /api/children/{id}/worksheets?subject=X` — batch print all worksheets for subject
- `POST /api/chat/subscribe` — buy chat subscription (300 crystals/month)
- `GET /api/chat/subscription` — check subscription status

## Pages

### Kid
- `/kid/login` — child picker cards + PIN keyboard
- `/kid/onboarding` — first-login character naming (redirects to home after)
- `/kid/home` — character avatar + subjects + streak + shop button
- `/kid/character` — RPG character page + star shop + name editing + speech bubble
- `/kid/subject/{subject}` — Duolingo-style lesson map with tooltip
- `/kid/lesson/{id}` — lesson iframe + print button
- `/kid/chat` — AI chat with 3 characters (Owl, Dreamer, Professor)
- `/kid/result/{id}` — confetti + stars animation + shop button

### Parent
- `/dashboard`, `/children/new`, `/children/{id}`, `/children/{id}/subject/{subject}`, `/children/{id}/history`
- `/profile`, `/buy`, `/login`, `/register`

## Running

```bash
cd /Users/anastasiamisenko/Documents/projects/kidion
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
# Tests: pytest tests/ -v
```

## Deploy

- **Domain:** kidion.ru
- **VPS:** 72.56.126.111, SSH: `ssh -i ~/.ssh/vps_key root@72.56.126.111`
- **Port:** 8004, **Path:** /opt/kidion
- **GitHub:** https://github.com/kotyadji-coder/kidion
- **Status:** deployed (SSL active)

## TODO

- [x] Deploy to VPS (systemd + nginx + certbot SSL)
- [x] DNS: A-record kidion.ru -> 72.56.126.111
- [ ] YooKassa: get real SHOP_ID and SECRET_KEY
- [x] Connect print worksheet generation (worksheets generated alongside lessons)
- [ ] Add curricula for grades 3-4 and more subjects (world)
- [ ] Pass universe_description into lesson generation prompts (so lessons are themed)
- [ ] Update registry.json with kidion entry
- [ ] Favicon, 404 page, rate limiting on auth
