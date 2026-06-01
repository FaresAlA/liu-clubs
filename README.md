# LIU Clubs — University Club Management System

A full-stack web application for managing student clubs at Lebanese International University (LIU). Built with Flask and deployed on Railway.

**Live:** https://liu.clubs.fares7.me

---

## Features

### For Students
- Register and log in with your LIU student ID and email
- Browse all clubs, view descriptions and member counts
- Join a club (one club at a time) with a join reason
- View and RSVP to upcoming events (with waitlist if full)
- Export events to Google Calendar or Apple/Outlook (.ics)
- Read club announcements (pinned posts shown first)
- Chat with club members in real-time club chat
- React to chat messages with emoji reactions
- Receive in-app notifications via bell dropdown
- Filter events by campus

### For Club Leaders
- Manage your club's page (cover image, description, social links, about section)
- Approve or reject member join requests
- Propose events and announcements (go to admin for approval)
- Pin/unpin club announcements
- View full member list
- Request to clear club chat

### For Admins
- Full admin panel with tabbed dashboard
- Approve/reject member join requests across all clubs
- Create, edit, delete, and pin announcements (system-wide or club-specific)
- Schedule announcements for future publishing
- Add and manage events (all campuses)
- Approve/reject leader-proposed events and announcements
- Send direct private messages to specific club leaders (or all at once)
- View message history log (who sent what to whom)
- Manage clubs: create, set leaders, toggle member acceptance
- Post LIU News items
- Analytics reports: member growth chart, events chart, top RSVP'd events, club sizes
- Reset any user's password
- Promote/demote admins (super-admin only)
- View RSVP attendee lists per event

### System
- Glassmorphism UI with LIU navy/gold theme
- Lucide icon set throughout
- Responsive layout
- Notification bell with popup dropdown (marks read on open)
- Announcement dot clears separately from bell dot
- Scheduled announcement auto-publishing
- Gzip compression on all responses
- DB indexes on all hot query paths

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask 3 |
| ORM | Flask-SQLAlchemy |
| Database | SQLite (local) / PostgreSQL (production) |
| Auth | Session-based, Werkzeug password hashing |
| Rate limiting | Flask-Limiter |
| Compression | Flask-Compress (gzip) |
| Server | Gunicorn (3 sync workers) |
| Deployment | Railway |
| Frontend | Vanilla JS, Lucide icons, custom CSS |

---

## Local Setup

**Requirements:** Python 3.10+

```bash
# 1. Clone
git clone https://github.com/FaresAlA/liu-clubs.git
cd liu-clubs/university-club-system

# 2. Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

The database and super-admin account are created automatically on first run.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes (prod) | Flask session secret — set a long random string |
| `DATABASE_URL` | Yes (prod) | PostgreSQL URL from Railway (`postgresql://...`) |
| `RAILWAY_ENVIRONMENT` | Auto-set | Enables secure cookies when on Railway |

Local development uses SQLite (`database.db`) with no extra config needed.

---

## Deployment (Railway)

1. Push to GitHub (this repo is already connected)
2. Railway auto-deploys on every push to `main`
3. Add `DATABASE_URL` and `SECRET_KEY` environment variables in Railway dashboard
4. The `Procfile` configures Gunicorn: `gunicorn app:app --workers 3 --timeout 30 --keep-alive 5`
5. Database schema and super-admin are auto-created on first boot

---

## Role System

| Role | How to get it | What they can do |
|---|---|---|
| `member` | Register | Browse, join one club, RSVP, chat, notifications |
| `admin` | Promoted by super-admin | Everything above + full admin panel |
| Super-admin | Hard-coded email | Everything + promote/demote admins, clear chats |

Club leaders are regular members or admins designated as a club's president via the admin panel. Leadership is tracked by `Club.president_id`, not a separate role.

---

## Project Structure

```
university-club-system/
├── app.py                  # All routes, models, helpers (~2000 lines)
├── requirements.txt
├── Procfile
├── static/
│   ├── style.css           # All styles including glassmorphism design
│   ├── main.js             # Tab switching, dropdowns, nav behavior
│   └── liu-bg.png          # Navbar logo
└── templates/
    ├── home.html           # Main app (clubs, announcements, calendar, home)
    ├── admin.html          # Admin dashboard
    ├── club.html           # Individual club page
    ├── profile.html        # My profile
    ├── user_profile.html   # View another user's profile
    ├── notifications.html  # Full notifications list
    ├── login.html
    ├── signup.html
    ├── forgot_password.html
    └── reset_password.html
```

---

## Key Models

```
User            — student_id, email, role, campus, gender, calendar_token
Club            — name, description, president_id, social links, accepting_members
ClubMember      — user_id, club_id, status (pending/approved/rejected), reason
Event           — title, date, location, campus, rsvp_limit, poster_url, status
EventRSVP       — event_id, user_id
EventWaitlist   — event_id, user_id (auto-promoted when spot opens)
Announcement    — title, content, club_id, pinned, publish_at, status
Notification    — user_id, message, link, read
AdminMessage    — sender_id, recipient_ids, message, sent_at (leader DMs)
LiuNews         — title, content (admin-posted campus news)
ClubMessage     — club_id, user_id, content (club chat)
ChatReaction    — message_id, user_id, emoji
```

---

## Developer Notes

- One-club rule: regular members can only belong to one club at a time. Admins bypass this.
- `Club.president_id` is the DB column name. UI shows "Club Leader" — never rename the column.
- `SUPER_ADMIN_EMAIL = 'fares@liu.edu'` — this and the seeding block at the bottom of `app.py` must never be changed.
- Connection pooling: `pool_pre_ping=True` and `pool_recycle=280` prevent stale connection hangs on Railway's 300s idle timeout.
- Scheduled announcements: `_publish_scheduled()` is called on each home page load, throttled to once per 60s per worker via `_last_publish_check`.
- DB indexes are created at startup via `CREATE INDEX IF NOT EXISTS` — idempotent and safe to run on every deploy.

---

*Built by Fares Al Ahmed — Lebanese International University*
