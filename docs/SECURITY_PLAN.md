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

### BLOCK B: What Anastasia needs to do (non-technical)

#### B1. Register as Personal Data Operator
- Check if notification to Roskomnadzor is required
- If yes: submit notification at pd.rkn.gov.ru
- Assign yourself as responsible person
- **When:** Before public launch

#### B2. Consult IT Lawyer
- Find a Russian IT lawyer specializing in 152-FZ / children's services
- Key questions:
  1. Cross-border data transfer to Google (Gemini API) — is it legal for children's data?
  2. What consent model is needed for parent + child?
  3. Do we need to register as data operator with RKN?
  4. What age marking (6+/12+) should the service have per 436-FZ?
  5. Are current privacy policy + terms sufficient?
- **When:** Before public launch
- **Budget:** ~15,000-30,000 RUB for initial consultation

#### B3. Google Gemini API Terms
- Review Google AI Studio terms of service
- Confirm: does Google use API data for training? (Usually no for API, but verify)
- Check if there's a Data Processing Agreement available
- Document the finding
- **Where to check:** https://ai.google.dev/terms

#### B4. Legal Entity
- Decide: ИП or ООО for operating the service
- Register if not done yet
- This affects all legal documents
- **When:** Before accepting real payments

#### B5. YooKassa Integration
- Get real SHOP_ID and SECRET_KEY
- Enable fiscalization (чеки) — required by law for online payments
- **When:** Before accepting real payments

#### B6. Domain & SSL
- Ensure COOKIE_SECURE=true in production .env
- Verify SSL certificate auto-renewal
- **When:** Already done, just verify

#### B7. Backup Strategy
- Set up automated DB backups (daily)
- Store backups in Russia (not abroad)
- Test restore procedure
- **When:** Before public launch

#### B8. Support Channel
- Create a support email (e.g., support@kidion.ru)
- Add it to privacy policy and terms
- This is required for privacy/deletion requests
- **When:** Before public launch

#### B9. Red Team Testing (Together with Claude)
- After all technical security is implemented
- Test with Russian children's slang, translit, emoji evasion
- Test crisis topics
- Test PII extraction attempts
- Test prompt injection
- Claude Code will help create test scripts
- **When:** After Block A is complete

---

### BLOCK C: Future (when scaling)

- ML-based PII detector (instead of regex)
- Human moderation queue with SLA
- Extended parent dashboard (time limits, character blocking)
- Rate limiting with Redis (instead of in-memory)
- Structured logging with log aggregation
- SIEM / security monitoring
- Penetration testing by external team
- Regular security audits
- Bug bounty program
- DDoS protection (Cloudflare)
- Database encryption at rest
- Key management service (KMS)
- Incident response playbook with team roles
- Regular data retention audits
- Vendor security assessments

---

## Implementation Order

Claude Code will implement in this order:

1. **A1** Rate limiting (highest risk — brute force)
2. **A12** Weak PIN prevention
3. **A2** Security headers
4. **A3** PII scrubber
5. **A4** Crisis response system
6. **A5** Output moderation
7. **A6** Audit logging
8. **A7** Chat data retention
9. **A8** Parent account deletion
10. **A9** Parental consent flow
11. **A10** Enhanced legal pages
12. **A11** Content report button

Total: 12 technical tasks, implemented as code changes to the existing monolith.
