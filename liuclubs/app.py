import os
import re
import base64
import random
import secrets
from flask import Flask, render_template, request, redirect, session, Response, abort, jsonify, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_compress import Compress
from sqlalchemy import func as _func, text as _t, update as _sa_update
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

app = Flask(__name__)
Compress(app)
app.secret_key = os.environ.get('SECRET_KEY', 'liu_clubs_secret_2024')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('RAILWAY_ENVIRONMENT'))


_db_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
    'pool_size': 5,
    'max_overflow': 5,
    'pool_timeout': 20,
}

db = SQLAlchemy(app)


def _migrate():
    stmts = [
        "ALTER TABLE event ADD COLUMN status VARCHAR(20) DEFAULT 'approved'",
        "ALTER TABLE event ADD COLUMN proposed_by INTEGER",
        "ALTER TABLE event ADD COLUMN leader_note TEXT",
        "ALTER TABLE announcement ADD COLUMN status VARCHAR(20) DEFAULT 'approved'",
        "ALTER TABLE announcement ADD COLUMN proposed_by INTEGER",
        "ALTER TABLE announcement ADD COLUMN leader_note TEXT",
        "ALTER TABLE \"user\" ADD COLUMN last_seen_announcements TIMESTAMP",
        "ALTER TABLE club ADD COLUMN clear_chat_requested INTEGER DEFAULT 0",
        "ALTER TABLE announcement ADD COLUMN pinned BOOLEAN DEFAULT 0",
        "ALTER TABLE club ADD COLUMN accepting_members BOOLEAN DEFAULT 1",
        "ALTER TABLE event ADD COLUMN rsvp_limit INTEGER",
        "ALTER TABLE event ADD COLUMN campus VARCHAR(50)",
        "ALTER TABLE announcement ADD COLUMN publish_at TIMESTAMP",
        "ALTER TABLE \"user\" ADD COLUMN calendar_token VARCHAR(64)",
        "ALTER TABLE notification ADD COLUMN admin_message_id INTEGER",
        "DELETE FROM notification WHERE message LIKE 'Your announcement %was approved!' OR message LIKE 'Your announcement %was not approved.' OR message LIKE 'Your event %was approved!' OR message LIKE 'Your event %was not approved.'",
    ]
    with db.engine.connect() as conn:
        for s in stmts:
            try:
                conn.execute(_t(s))
                conn.commit()
            except Exception:
                try: conn.rollback()
                except: pass

SUPER_ADMIN_EMAIL = 'fares@liu.edu'


@app.context_processor
def inject_super_admin_email():
    return {'super_admin_email': SUPER_ADMIN_EMAIL}


@app.template_filter('club_icon')
def club_icon_filter(name):
    n = (name or '').lower()
    if any(k in n for k in ('cod', 'tech', 'program', 'dev', 'software', 'cyber', 'comput', 'web', 'data', 'ai', 'ml')):
        return 'code-2'
    if any(k in n for k in ('read', 'book', 'lit', 'writ', 'poet', 'journal', 'stor', 'novel', 'press')):
        return 'book-open'
    if any(k in n for k in ('foot', 'sport', 'soccer', 'basket', 'tennis', 'swim', 'run', 'athlet', 'gym', 'volley', 'ball', 'fit')):
        return 'trophy'
    if any(k in n for k in ('gam', 'esport', 'video game', 'chess', 'play')):
        return 'gamepad-2'
    if any(k in n for k in ('music', 'band', 'choir', 'orchestr', 'sing')):
        return 'music'
    if any(k in n for k in ('art', 'design', 'paint', 'draw', 'craft', 'sketch')):
        return 'palette'
    if any(k in n for k in ('photo', 'camera', 'film', 'cinema')):
        return 'camera'
    if any(k in n for k in ('business', 'financ', 'entrepreneur', 'market', 'invest', 'econ')):
        return 'briefcase'
    if any(k in n for k in ('scienc', 'chem', 'bio', 'physic', 'lab', 'research')):
        return 'flask-conical'
    if any(k in n for k in ('drama', 'theater', 'theatre', 'perform', 'stage', 'debat')):
        return 'mic-2'
    if any(k in n for k in ('volunteer', 'communit', 'social', 'charit', 'environment', 'eco', 'green')):
        return 'heart'
    if any(k in n for k in ('languag', 'cultur', 'international', 'global')):
        return 'globe'
    return 'users'


limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

@app.after_request
def _cache_static(response):
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 86400
        response.cache_control.public = True
    return response

def _reset_serializer():
    return URLSafeTimedSerializer(app.secret_key)


CAMPUSES = ['Beirut', 'Bekaa', 'Saida', 'Nabatieh', 'Tripoli', 'Mount Lebanon', 'Tyre', 'Rayak', 'Akkar']

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), default='member')
    campus = db.Column(db.String(50), nullable=True)
    gender = db.Column(db.String(10), default='male')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_announcements = db.Column(db.DateTime, nullable=True)
    calendar_token = db.Column(db.String(64), nullable=True)

class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    logo_emoji = db.Column(db.String(10), default='🏫')
    president_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    cover_url = db.Column(db.String(300), nullable=True)
    logo_url = db.Column(db.String(300), nullable=True)
    about_us = db.Column(db.Text, nullable=True)
    instagram = db.Column(db.String(200), nullable=True)
    twitter = db.Column(db.String(200), nullable=True)
    facebook = db.Column(db.String(200), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    clear_chat_requested = db.Column(db.Integer, default=0)
    accepting_members = db.Column(db.Boolean, default=True)

class ClubMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    reason = db.Column(db.Text)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    description = db.Column(db.Text)
    poster_url = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='approved')
    proposed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    leader_note = db.Column(db.Text, nullable=True)
    rsvp_limit = db.Column(db.Integer, nullable=True)
    campus = db.Column(db.String(50), nullable=True)

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    status = db.Column(db.String(20), default='approved')
    proposed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    leader_note = db.Column(db.Text, nullable=True)
    pinned = db.Column(db.Boolean, default=False)
    publish_at = db.Column(db.DateTime, nullable=True)

class ClubMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LiuNews(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatReaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('club_message.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    emoji = db.Column(db.String(10), nullable=False)
    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', 'emoji'),)

class EventRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('event_id', 'user_id'),)

class EventWaitlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('event_id', 'user_id'),)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(300), nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_message_id = db.Column(db.Integer, db.ForeignKey('admin_message.id'), nullable=True)

class AdminMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    recipient_ids = db.Column(db.Text, nullable=False)
    recipient_label = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            session['role'] = user.role if user else 'member'
            return redirect('/')
        session['role'] = 'admin'
        return f(*args, **kwargs)
    return wrapper

def get_membership_status(user_id, club_id):
    m = ClubMember.query.filter_by(user_id=user_id, club_id=club_id).first()
    if m:
        return m.status
    return None

def get_leader_club(user_id):
    return Club.query.filter_by(president_id=user_id).first()

_ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
_URL_RE = re.compile(r'^https?://', re.IGNORECASE)

def _safe_url(value, max_len=300):
    """Return value only if it is a valid http/https URL, else None."""
    v = (value or '').strip()[:max_len]
    return v if v and _URL_RE.match(v) else None

def _notify(user_id, message, link=None, admin_message_id=None):
    if link and not re.match(r'^/(?:[^/]|$)', link):
        link = None
    db.session.add(Notification(user_id=user_id, message=str(message)[:300], link=link,
                                admin_message_id=admin_message_id))

def _notify_announcement_members(ann):
    snippet = ann.content[:120] + ('…' if len(ann.content) > 120 else '')
    msg = f'Announcement — {ann.title}: {snippet}'
    link = f'/club/{ann.club_id}' if ann.club_id else '/'
    notified = set()
    if ann.club_id:
        members = ClubMember.query.filter_by(club_id=ann.club_id, status='approved').all()
        for m in members:
            if m.user_id != ann.proposed_by:
                _notify(m.user_id, msg, link)
                notified.add(m.user_id)
        club = Club.query.get(ann.club_id)
        if club and club.president_id and club.president_id != ann.proposed_by and club.president_id not in notified:
            _notify(club.president_id, msg, link)
    else:
        for u in User.query.all():
            if u.id != ann.proposed_by:
                _notify(u.id, msg, link)

_last_publish_check = None

def _publish_scheduled():
    """Promote scheduled announcements at most once per 60 s.
    Atomic UPDATE ensures only the worker that actually changes rows sends notifications."""
    global _last_publish_check
    now = datetime.utcnow()
    if _last_publish_check and (now - _last_publish_check).total_seconds() < 60:
        return
    _last_publish_check = now
    candidates = Announcement.query.filter(
        Announcement.status == 'pending',
        Announcement.publish_at.isnot(None),
        Announcement.publish_at <= now,
        Announcement.proposed_by.is_(None)
    ).all()
    if not candidates:
        return
    result = db.session.execute(
        _sa_update(Announcement)
        .where(
            Announcement.id.in_([a.id for a in candidates]),
            Announcement.status == 'pending'
        )
        .values(status='approved')
    )
    if not result.rowcount:
        db.session.rollback()
        return
    db.session.commit()
    for a in candidates:
        _notify_announcement_members(a)
    db.session.commit()

def _promote_waitlist(event_id):
    """Auto-RSVP the first person on the waitlist. Returns True if someone was promoted."""
    first = EventWaitlist.query.filter_by(event_id=event_id).order_by(EventWaitlist.created_at).first()
    if not first:
        return False
    db.session.add(EventRSVP(event_id=event_id, user_id=first.user_id))
    db.session.delete(first)
    e = Event.query.get(event_id)
    if e:
        _notify(first.user_id,
                f'A spot opened for "{e.title}" — you\'ve been added to the attendee list!',
                f'/club/{e.club_id}' if e.club_id else None)
    return True

def _get_calendar_token(user):
    if not user.calendar_token:
        user.calendar_token = secrets.token_hex(16)
        db.session.commit()
    return user.calendar_token

def read_uploaded_image(field_name):
    """Return a base64 data-URL from a file upload field, or None."""
    f = request.files.get(field_name)
    if f and f.filename:
        data = f.read()
        if len(data) > 8 * 1024 * 1024:
            flash('Image not saved — file must be under 8 MB.', 'error')
            return None
        mime = (f.content_type or '').lower().split(';')[0].strip()
        if mime not in _ALLOWED_IMAGE_MIMES:
            flash('Image not saved — only JPG, PNG, GIF and WebP are accepted.', 'error')
            return None
        return 'data:{};base64,{}'.format(mime, base64.b64encode(data).decode())
    return None


@app.errorhandler(429)
def ratelimit_handler(e):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(error='Too many requests. Please wait a moment.'), 429
    if 'user_id' in session:
        return redirect(request.referrer or '/'), 429
    return render_template('login.html',
        error='Too many requests. Please wait a minute and try again.',
        error_field='rate_limit'), 429

@app.errorhandler(404)
def not_found(e):
    if 'user_id' in session:
        return redirect('/')
    return redirect('/login')

@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<title>LIU Clubs — Something went wrong</title>'
        '<style>body{font-family:sans-serif;display:flex;align-items:center;'
        'justify-content:center;min-height:100vh;margin:0;background:#f8f9fa}'
        '.box{text-align:center;padding:2rem;max-width:400px}'
        'h2{color:#c0392b}a{color:#2980b9}</style></head><body>'
        '<div class="box"><h2>Something went wrong</h2>'
        '<p>We hit an unexpected error. Please try again in a moment.</p>'
        '<a href="/">← Back to home</a></div></body></html>'
    )
    return html, 500

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return 'OK', 200
    except Exception:
        return 'DB unavailable', 500

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if 'user_id' in session:
        return redirect('/')
    error = None
    error_field = None
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = (request.form.get('password') or '')[:128]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            permanent = bool(request.form.get('remember_me'))
            session.clear()
            session.permanent = permanent
            session['user_id'] = user.id
            session['role'] = user.role
            session['user_name'] = user.full_name
            return redirect('/')
        if not user:
            error = 'No account found with this email address.'
            error_field = 'email'
        else:
            error = 'Incorrect password. Please try again.'
            error_field = 'password'
    return render_template('login.html', error=error, error_field=error_field)

@app.route('/forgot-password')
def forgot_password():
    if 'user_id' in session:
        return redirect('/')
    return render_template('forgot_password.html', super_admin_email=SUPER_ADMIN_EMAIL)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    error = None
    try:
        email = _reset_serializer().loads(token, salt='pw-reset', max_age=3600)
    except SignatureExpired:
        return render_template('reset_password.html',
            error='This reset link has expired. Please request a new one.', token=None)
    except BadSignature:
        return render_template('reset_password.html',
            error='Invalid reset link.', token=None)

    if request.method == 'POST':
        password = request.form.get('password', '')[:128]
        confirm  = request.form.get('confirm_password', '')
        if len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                user.password = generate_password_hash(password)
                db.session.commit()
                return redirect('/login?reset=1')
    return render_template('reset_password.html', token=token, error=error)

def _new_captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    session['captcha_answer'] = a + b
    q = f'{a} + {b}'
    session['captcha_q'] = q
    return q

def _current_captcha():
    """Return the stored captcha question without regenerating it."""
    if 'captcha_answer' not in session:
        return _new_captcha()
    return session.get('captcha_q') or _new_captcha()

@app.route('/signup', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def signup():
    if 'user_id' in session:
        return redirect('/')
    error = None
    if request.method == 'POST':
        try:
            user_ans = int(request.form.get('captcha_ans', ''))
        except ValueError:
            user_ans = -1
        if user_ans != session.get('captcha_answer'):
            error = 'Incorrect answer — please try again.'
            return render_template('signup.html', error=error, captcha_q=_new_captcha())
        session.pop('captcha_answer', None)
        session.pop('captcha_q', None)

        name       = (request.form.get('full_name') or '').strip()[:100]
        student_id = (request.form.get('student_id') or '').strip()[:20]
        email      = (request.form.get('email') or '').strip().lower()[:100]
        password   = request.form.get('password', '')[:128]
        confirm    = request.form.get('confirm_password', '')
        campus     = request.form.get('campus', '').strip()
        gender     = request.form.get('gender', 'male')
        if gender not in ('male', 'female'):
            gender = 'male'

        if not name or not student_id or not email:
            error = 'Please fill in all required fields.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != confirm:
            error = 'Passwords do not match'
        elif campus not in CAMPUSES:
            error = 'Please select a valid campus'
        elif User.query.filter_by(email=email).first():
            error = 'Email already registered'
        elif User.query.filter_by(student_id=student_id).first():
            error = 'Student ID already registered'
        else:
            hashed = generate_password_hash(password)
            user = User(full_name=name, student_id=student_id, email=email, password=hashed, campus=campus, gender=gender)
            db.session.add(user)
            db.session.commit()
            return redirect('/login?success=1')

    return render_template('signup.html', error=error, captcha_q=_current_captcha())

@app.route('/user/<int:user_id>')
@login_required
def view_profile(user_id):
    if user_id == session['user_id']:
        return redirect('/profile')
    target = User.query.get_or_404(user_id)
    viewer = User.query.get(session['user_id'])
    if not viewer:
        session.clear()
        return redirect('/login')

    # Only share-a-club members/leaders (or admin) can view
    if viewer.role != 'admin':
        my_ids = {m.club_id for m in ClubMember.query.filter_by(user_id=session['user_id'], status='approved')}
        viewer_leader = get_leader_club(session['user_id'])
        if viewer_leader:
            my_ids.add(viewer_leader.id)
        their_ids = {m.club_id for m in ClubMember.query.filter_by(user_id=user_id, status='approved')}
        target_leader = get_leader_club(user_id)
        if target_leader:
            their_ids.add(target_leader.id)
        if not my_ids & their_ids:
            return redirect('/')

    memberships = ClubMember.query.filter_by(user_id=user_id, status='approved').all()
    club_ids = [m.club_id for m in memberships]
    clubs = Club.query.filter(Club.id.in_(club_ids)).all() if club_ids else []
    leader_club = get_leader_club(user_id)

    return render_template('user_profile.html',
        target=target,
        clubs=clubs,
        leader_club=leader_club,
        super_admin_email=SUPER_ADMIN_EMAIL
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')
    memberships = ClubMember.query.filter_by(user_id=user.id).all()
    club_ids = [m.club_id for m in memberships]
    clubs_map = {c.id: c for c in Club.query.filter(Club.id.in_(club_ids)).all()} if club_ids else {}
    my_clubs = [{'club': clubs_map[m.club_id], 'membership': m} for m in memberships if m.club_id in clubs_map]
    leader_club = get_leader_club(user.id)
    return render_template('profile.html', user=user, my_clubs=my_clubs, leader_club=leader_club, super_admin_email=SUPER_ADMIN_EMAIL)


@app.route('/')
@login_required
def home():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')
    clubs = Club.query.all()
    clubs_by_id = {c.id: c for c in clubs}

    my_memberships = ClubMember.query.filter_by(user_id=user.id, status='approved').all()
    my_club_ids = [m.club_id for m in my_memberships]
    my_clubs = [clubs_by_id[cid] for cid in my_club_ids if cid in clubs_by_id]

    now = datetime.utcnow()
    leader_club = next((c for c in clubs if c.president_id == user.id), None)
    see_all = user.role == 'admin' or leader_club is not None

    if see_all or not my_club_ids:
        ev_filter  = (Event.club_id.is_(None)) if not see_all else None
        ann_filter = (Announcement.club_id.is_(None)) if not see_all else None
    else:
        ev_filter  = (Event.club_id.is_(None)) | (Event.club_id.in_(my_club_ids))
        ann_filter = (Announcement.club_id.is_(None)) | (Announcement.club_id.in_(my_club_ids))

    def _eq(q, f): return q.filter(f) if f is not None else q
    def _approved_ev(q):  return q.filter(db.or_(Event.status == 'approved',        Event.status.is_(None)))
    def _approved_an(q):  return q.filter(db.or_(Announcement.status == 'approved', Announcement.status.is_(None)))

    upcoming_events = _approved_ev(Event.query.filter(Event.date >= now)).order_by(Event.date.asc()).limit(30).all()
    if ev_filter is None:
        all_events = upcoming_events
    else:
        all_events = _approved_ev(_eq(Event.query.filter(Event.date >= now), ev_filter)).order_by(Event.date.asc()).all()
    past_events = _approved_ev(_eq(Event.query.filter(Event.date < now), ev_filter)).order_by(Event.date.desc()).limit(20).all()
    event_clubs = clubs_by_id

    _publish_scheduled()
    announcements = _approved_an(_eq(Announcement.query, ann_filter)).order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).all()

    _cnt_rows = db.session.query(ClubMember.club_id, _func.count(ClubMember.id)) \
        .filter(ClubMember.status == 'approved').group_by(ClubMember.club_id).all()
    club_member_counts = {cid: cnt for cid, cnt in _cnt_rows}
    for c in clubs:
        club_member_counts.setdefault(c.id, 0)
    notif_count = ClubMember.query.filter_by(club_id=leader_club.id, status='pending').count() if leader_club else 0
    if user.role == 'admin':
        _pending = db.session.execute(_t(
            "SELECT (SELECT COUNT(*) FROM event WHERE status='pending') + "
            "(SELECT COUNT(*) FROM announcement WHERE status='pending')"
        )).scalar() or 0
        notif_count += int(_pending)
    liu_news = LiuNews.query.order_by(LiuNews.created_at.desc()).all()

    if user.last_seen_announcements:
        new_ann_count = sum(1 for a in announcements if a.created_at > user.last_seen_announcements)
    else:
        new_ann_count = len(announcements)

    unread_notif_count = Notification.query.filter_by(user_id=user.id, read=False).count()

    user_rsvp_ids = {r.event_id for r in EventRSVP.query.filter_by(user_id=user.id).all()}
    user_waitlist_ids = {w.event_id for w in EventWaitlist.query.filter_by(user_id=user.id).all()}
    all_event_ids = [e.id for e in all_events] + [e.id for e in past_events] + [e.id for e in upcoming_events]
    all_event_ids = list(set(all_event_ids))
    rsvp_counts = {}
    waitlist_counts = {}
    if all_event_ids:
        for _eid, _cnt in db.session.query(EventRSVP.event_id, _func.count(EventRSVP.id)).filter(
            EventRSVP.event_id.in_(all_event_ids)
        ).group_by(EventRSVP.event_id).all():
            rsvp_counts[_eid] = _cnt
        for _eid, _cnt in db.session.query(EventWaitlist.event_id, _func.count(EventWaitlist.id)).filter(
            EventWaitlist.event_id.in_(all_event_ids)
        ).group_by(EventWaitlist.event_id).all():
            waitlist_counts[_eid] = _cnt

    calendar_token = _get_calendar_token(user)

    def _gcal_url(e):
        start = e.date.strftime('%Y%m%dT%H%M%SZ')
        end   = (e.date + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')
        return 'https://calendar.google.com/calendar/render?' + urlencode({
            'action':   'TEMPLATE',
            'text':     e.title,
            'dates':    f'{start}/{end}',
            'details':  e.description or '',
            'location': e.location or '',
        })
    google_cal_urls = {e.id: _gcal_url(e) for e in all_events + past_events + upcoming_events}
    recent_notifs = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(8).all()

    return render_template('home.html',
        user=user,
        clubs=clubs,
        my_clubs=my_clubs,
        upcoming_events=upcoming_events,
        all_events=all_events,
        past_events=past_events,
        event_clubs=event_clubs,
        announcements=announcements,
        club_member_counts=club_member_counts,
        leader_club=leader_club,
        notif_count=notif_count,
        new_ann_count=new_ann_count,
        liu_news=liu_news,
        unread_notif_count=unread_notif_count,
        user_rsvp_ids=user_rsvp_ids,
        user_waitlist_ids=user_waitlist_ids,
        rsvp_counts=rsvp_counts,
        waitlist_counts=waitlist_counts,
        calendar_token=calendar_token,
        google_cal_urls=google_cal_urls,
        campuses=CAMPUSES,
        recent_notifs=recent_notifs
    )

@app.route('/mark_announcements_seen', methods=['POST'])
@login_required
def mark_announcements_seen():
    u = User.query.get(session['user_id'])
    if u:
        u.last_seen_announcements = datetime.utcnow()
        db.session.commit()
    return '', 204

@app.route('/mark_notif_read', methods=['POST'])
@login_required
def mark_notif_read():
    """Mark all notifications as read (called when bell dropdown is opened)."""
    Notification.query.filter_by(user_id=session['user_id'], read=False).update({'read': True})
    db.session.commit()
    return '', 204


@app.route('/club/<int:club_id>')
@login_required
def club_page(club_id):
    _publish_scheduled()
    club = Club.query.get_or_404(club_id)
    user_id = session['user_id']

    status = get_membership_status(user_id, club_id)
    error = request.args.get('error')
    is_leader = club.president_id == user_id

    now = datetime.utcnow()
    _ev_ok = db.or_(Event.status == 'approved', Event.status.is_(None))
    events = Event.query.filter(
        (Event.club_id == club_id) | (Event.club_id.is_(None)), Event.date >= now, _ev_ok
    ).order_by(Event.date.asc()).all()

    past_events = Event.query.filter(
        (Event.club_id == club_id) | (Event.club_id.is_(None)), Event.date < now, _ev_ok
    ).order_by(Event.date.desc()).all()

    memberships = ClubMember.query.filter_by(club_id=club_id, status='approved').all()
    member_user_ids = [m.user_id for m in memberships]
    member_users = User.query.filter(User.id.in_(member_user_ids)).all() if member_user_ids else []
    member_users.sort(key=lambda u: (0 if u.email == SUPER_ADMIN_EMAIL else 1 if u.role == 'admin' else 2))

    leader = User.query.filter_by(id=club.president_id).first() if club.president_id else None

    messages = list(reversed(
        ClubMessage.query.filter_by(club_id=club_id)
            .order_by(ClubMessage.created_at.desc()).limit(100).all()
    ))
    msg_user_ids = list({msg.user_id for msg in messages})
    msg_users_list = User.query.filter(User.id.in_(msg_user_ids)).all() if msg_user_ids else []
    msg_users = {u.id: u for u in msg_users_list}

    _ann_ok = db.or_(Announcement.status == 'approved', Announcement.status.is_(None))
    club_announcements = Announcement.query.filter(
        db.or_(Announcement.club_id == club_id, Announcement.club_id.is_(None))
    ).filter(_ann_ok).order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).all()
    current_user = User.query.get(user_id)

    pending_requests = []
    approved_rows = []
    proposed_events_leader = []
    proposed_announcements_leader = []
    if is_leader:
        _pm = ClubMember.query.filter_by(club_id=club_id, status='pending').all()
        _pu_ids = [m.user_id for m in _pm]
        _pu_map = {u.id: u for u in User.query.filter(User.id.in_(_pu_ids)).all()} if _pu_ids else {}
        pending_requests = [{'membership': m, 'user': _pu_map[m.user_id]} for m in _pm if m.user_id in _pu_map]
        _mem_map = {m.user_id: m for m in memberships}
        approved_rows = [{'membership': _mem_map[u.id], 'user': u} for u in member_users if u.id in _mem_map]
        proposed_events_leader = Event.query.filter_by(club_id=club_id).filter(
            Event.status.in_(['pending', 'rejected'])
        ).order_by(Event.date.asc()).all()
        proposed_announcements_leader = Announcement.query.filter_by(club_id=club_id).filter(
            Announcement.status.in_(['pending', 'rejected'])
        ).order_by(Announcement.created_at.desc()).all()

    msg_ids = [m.id for m in messages]
    msg_reactions = {}
    user_reactions = {}
    if msg_ids:
        for r in ChatReaction.query.filter(ChatReaction.message_id.in_(msg_ids)).all():
            msg_reactions.setdefault(r.message_id, {})
            msg_reactions[r.message_id][r.emoji] = msg_reactions[r.message_id].get(r.emoji, 0) + 1
            if r.user_id == user_id:
                user_reactions.setdefault(r.message_id, []).append(r.emoji)

    return render_template('club.html',
        club=club,
        status=status,
        error=error,
        is_leader=is_leader,
        current_user_id=user_id,
        events=events,
        past_events=past_events,
        member_users=member_users,
        leader=leader,
        messages=messages,
        msg_users=msg_users,
        msg_reactions=msg_reactions,
        user_reactions=user_reactions,
        announcements=club_announcements,
        current_user=current_user,
        pending_requests=pending_requests,
        approved_rows=approved_rows,
        proposed_events_leader=proposed_events_leader,
        proposed_announcements_leader=proposed_announcements_leader,
        campuses=CAMPUSES,
        super_admin_email=SUPER_ADMIN_EMAIL
    )

@app.route('/club/<int:club_id>/join', methods=['POST'])
@login_required
def join_club(club_id):
    user_id = session['user_id']
    _viewer = User.query.get(user_id)
    is_admin = _viewer and _viewer.role == 'admin'
    club = Club.query.get_or_404(club_id)

    if not is_admin:
        if not club.accepting_members:
            return redirect(f'/club/{club_id}?error=not_recruiting')
        active = ClubMember.query.filter_by(user_id=user_id).filter(
            ClubMember.status.in_(['approved', 'pending'])
        ).first()
        if active:
            return redirect(f'/club/{club_id}?error=one_club')

    existing = ClubMember.query.filter_by(user_id=user_id, club_id=club_id).first()
    if existing:
        if existing.status == 'rejected':
            db.session.delete(existing)
            db.session.commit()
        else:
            return redirect(f'/club/{club_id}')

    reason = request.form.get('reason', '').strip()[:2000]
    status = 'approved' if is_admin else 'pending'
    m = ClubMember(user_id=user_id, club_id=club_id, reason=reason, status=status)
    db.session.add(m)
    db.session.commit()
    if status == 'pending':
        flash('Your membership request has been submitted!', 'success')
    else:
        flash('You have joined the club.', 'success')
    return redirect(f'/club/{club_id}')

@app.route('/club/<int:club_id>/leave', methods=['POST'])
@login_required
def leave_club(club_id):
    user_id = session['user_id']
    club = Club.query.get_or_404(club_id)
    if club.president_id == user_id:
        return redirect(f'/club/{club_id}')
    m = ClubMember.query.filter_by(user_id=user_id, club_id=club_id).first()
    if m:
        db.session.delete(m)
        db.session.commit()
        flash(f'You have left {club.name}.', 'success')
    return redirect('/')

@app.route('/leader')
@login_required
def leader_panel():
    club = get_leader_club(session['user_id'])
    return redirect(f'/club/{club.id}') if club else redirect('/')

@app.route('/leader/approve/<int:member_id>', methods=['POST'])
@login_required
def leader_approve(member_id):
    club = get_leader_club(session['user_id'])
    m = ClubMember.query.get_or_404(member_id)
    if not club or m.club_id != club.id or m.user_id == session['user_id']:
        return redirect('/')
    other = ClubMember.query.filter_by(user_id=m.user_id, status='approved').filter(
        ClubMember.club_id != m.club_id
    ).first()
    if other:
        return redirect(f'/club/{club.id}')
    m.status = 'approved'
    m.joined_at = datetime.utcnow()
    _notify(m.user_id, f'Your application to join {club.name} was approved!', f'/club/{club.id}')
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/leader/reject/<int:member_id>', methods=['POST'])
@login_required
def leader_reject(member_id):
    club = get_leader_club(session['user_id'])
    m = ClubMember.query.get_or_404(member_id)
    if not club or m.club_id != club.id or m.user_id == session['user_id']:
        return redirect('/')
    m.status = 'rejected'
    _notify(m.user_id, f'Your application to join {club.name} was not approved.', f'/club/{club.id}')
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/leader/remove_member/<int:member_id>', methods=['POST'])
@login_required
def leader_remove_member(member_id):
    m = ClubMember.query.get_or_404(member_id)
    club = Club.query.get(m.club_id)
    if not club or club.president_id != session['user_id']:
        return redirect('/')
    target = User.query.get(m.user_id)
    if target and (target.role == 'admin' or target.id == session['user_id']):
        return redirect(f'/club/{club.id}')
    db.session.delete(m)
    db.session.commit()
    flash('Member removed from the club.', 'success')
    return redirect(f'/club/{club.id}')

@app.route('/leader/edit_club', methods=['POST'])
@login_required
def leader_edit_club():
    club = get_leader_club(session['user_id'])
    if not club:
        return redirect('/')
    club.description = (request.form.get('description') or '').strip()[:500] or None
    club.about_us    = request.form.get('about_us', '').strip()[:5000] or None
    club.cover_url   = _safe_url(request.form.get('cover_url', ''))
    club.logo_url    = _safe_url(request.form.get('logo_url', ''))
    club.instagram   = _safe_url(request.form.get('instagram', ''), max_len=200)
    club.twitter     = _safe_url(request.form.get('twitter', ''), max_len=200)
    club.facebook    = _safe_url(request.form.get('facebook', ''), max_len=200)
    club.website     = _safe_url(request.form.get('website', ''), max_len=200)
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/leader/add_announcement', methods=['POST'])
@login_required
def leader_add_announcement():
    club = get_leader_club(session['user_id'])
    if not club:
        return redirect('/')
    title   = request.form.get('title', '').strip()[:200]
    content = request.form.get('content', '').strip()[:2000]
    leader_note = request.form.get('leader_note', '').strip()[:500]
    publish_at = None
    publish_at_str = request.form.get('publish_at', '').strip()
    if publish_at_str:
        try:
            publish_at = datetime.strptime(publish_at_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            pass
    if title and content:
        a = Announcement(title=title, content=content, club_id=club.id,
                         status='pending', proposed_by=session['user_id'],
                         leader_note=leader_note or None, publish_at=publish_at)
        db.session.add(a)
        db.session.commit()
        flash('Announcement submitted for approval.', 'success')
    return redirect(f'/club/{club.id}')

@app.route('/leader/delete_announcement/<int:ann_id>', methods=['POST'])
@login_required
def leader_delete_announcement(ann_id):
    club = get_leader_club(session['user_id'])
    a = Announcement.query.get_or_404(ann_id)
    if not club or a.club_id != club.id or a.status == 'approved':
        return redirect(f'/club/{club.id}' if club else '/')
    Notification.query.filter(
        Notification.user_id == a.proposed_by,
        Notification.message == f'Your announcement "{a.title}" was not approved.'
    ).delete(synchronize_session=False)
    db.session.delete(a)
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/leader/propose_event', methods=['POST'])
@login_required
def leader_propose_event():
    club = get_leader_club(session['user_id'])
    if not club:
        return redirect('/')
    title       = request.form.get('title', '').strip()[:200]
    date_str    = request.form.get('date', '')
    location    = request.form.get('location', '').strip()[:200]
    description = request.form.get('description', '').strip()[:2000]
    leader_note = request.form.get('leader_note', '').strip()[:500]
    poster_url  = read_uploaded_image('poster_file')
    campus      = request.form.get('campus', '').strip()
    if campus not in CAMPUSES:
        campus = None
    try:
        rsvp_limit = int(request.form.get('rsvp_limit', 0)) or None
        if rsvp_limit is not None and rsvp_limit <= 0:
            rsvp_limit = None
    except (ValueError, TypeError):
        rsvp_limit = None
    if not title or not date_str:
        return redirect(f'/club/{club.id}')
    try:
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        return redirect(f'/club/{club.id}')
    e = Event(club_id=club.id, title=title, date=date, location=location,
              description=description, poster_url=poster_url,
              campus=campus, rsvp_limit=rsvp_limit,
              status='pending', proposed_by=session['user_id'],
              leader_note=leader_note or None)
    db.session.add(e)
    db.session.commit()
    flash('Event proposal submitted for approval.', 'success')
    return redirect(f'/club/{club.id}')

@app.route('/leader/delete_event_proposal/<int:event_id>', methods=['POST'])
@login_required
def leader_delete_event_proposal(event_id):
    club = get_leader_club(session['user_id'])
    e = Event.query.get_or_404(event_id)
    if not club or e.club_id != club.id or e.status == 'approved':
        return redirect(f'/club/{club.id}' if club else '/')
    EventRSVP.query.filter_by(event_id=event_id).delete(synchronize_session=False)
    EventWaitlist.query.filter_by(event_id=event_id).delete(synchronize_session=False)
    if e.proposed_by:
        Notification.query.filter(
            Notification.user_id == e.proposed_by,
            Notification.message == f'Your event "{e.title}" was not approved.'
        ).delete(synchronize_session=False)
    db.session.delete(e)
    db.session.commit()
    return redirect(f'/club/{club.id}')


@app.route('/club/<int:club_id>/edit_about', methods=['POST'])
@login_required
def edit_about(club_id):
    club = Club.query.get_or_404(club_id)
    if club.president_id != session['user_id']:
        return redirect(f'/club/{club_id}')
    club.about_us = request.form.get('about_us', '').strip()[:5000] or None
    db.session.commit()
    return redirect(f'/club/{club_id}')

@app.route('/club/<int:club_id>/send_message', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def send_message(club_id):
    user_id = session['user_id']
    club = Club.query.get_or_404(club_id)
    is_leader = club.president_id == user_id
    membership = ClubMember.query.filter_by(user_id=user_id, club_id=club_id, status='approved').first()
    if not is_leader and not membership:
        return redirect(f'/club/{club_id}')
    content = request.form.get('content', '').strip()[:2000]
    if content:
        msg = ClubMessage(club_id=club_id, user_id=user_id, content=content)
        db.session.add(msg)
        db.session.commit()
    return redirect(f'/club/{club_id}#chat')


@app.route('/club/<int:club_id>/request_clear_chat', methods=['POST'])
@login_required
def request_clear_chat(club_id):
    club = Club.query.get_or_404(club_id)
    if club.president_id != session['user_id']:
        return redirect(f'/club/{club_id}')
    club.clear_chat_requested = 1
    db.session.commit()
    return redirect(f'/club/{club_id}')


@app.route('/event/<int:event_id>/calendar.ics')
def event_ics(event_id):
    e = Event.query.get_or_404(event_id)
    if e.status != 'approved':
        abort(404)
    def esc(s):
        return (s or '').replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;').replace('\n', '\\n')
    dtstart = e.date.strftime('%Y%m%dT%H%M%SZ')
    dtend   = (e.date + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')
    uid     = f'liu-clubs-event-{e.id}@liu.edu.lb'
    ics = '\r\n'.join([
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//LIU Clubs//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTART:{dtstart}',
        f'DTEND:{dtend}',
        f'SUMMARY:{esc(e.title)}',
        f'DESCRIPTION:{esc(e.description)}',
        f'LOCATION:{esc(e.location)}',
        'END:VEVENT',
        'END:VCALENDAR',
    ])
    return Response(ics, mimetype='text/calendar',
                    headers={'Content-Disposition': f'attachment; filename="event-{e.id}.ics"'})


@app.route('/admin')
@admin_required
def admin():
    users = User.query.filter_by(role='member').all()
    clubs = Club.query.all()
    _not_pending = lambda col: db.or_(col.is_(None), col != 'pending')
    events = Event.query.filter(
        db.or_(Event.status == 'approved', Event.status.is_(None))
    ).order_by(Event.date.asc()).all()
    announcements = Announcement.query.filter(_not_pending(Announcement.status)).order_by(Announcement.created_at.desc()).all()
    event_clubs = {c.id: c for c in clubs}

    all_admins = User.query.filter_by(role='admin').all()
    all_admins.sort(key=lambda u: 0 if u.email == SUPER_ADMIN_EMAIL else 1)
    _all_uids = [u.id for u in users] + [u.id for u in all_admins]
    _bulk_ms = ClubMember.query.filter(ClubMember.user_id.in_(_all_uids)).all() if _all_uids else []
    _ms_by_user = {}
    for _m in _bulk_ms:
        _ms_by_user.setdefault(_m.user_id, []).append(_m)

    member_rows = []
    for u in users:
        memberships = _ms_by_user.get(u.id, [])
        if memberships:
            for m in memberships:
                member_rows.append({'membership': m, 'user': u, 'club': event_clubs.get(m.club_id)})
        else:
            member_rows.append({'membership': None, 'user': u, 'club': None})

    admin_rows = []
    for admin_user in all_admins:
        admin_memberships = _ms_by_user.get(admin_user.id, [])
        if admin_memberships:
            for m in admin_memberships:
                admin_rows.append({'membership': m, 'user': admin_user, 'club': event_clubs.get(m.club_id)})
        else:
            admin_rows.append({'membership': None, 'user': admin_user, 'club': None})
    member_rows = admin_rows + member_rows

    _umap = {}
    for _row in member_rows:
        _uid = _row['user'].id
        if _uid not in _umap:
            _umap[_uid] = {'user': _row['user'], 'memberships': []}
        if _row['membership']:
            _umap[_uid]['memberships'].append({'membership': _row['membership'], 'club': _row['club']})
    users_list = list(_umap.values())

    leader_map = {c.president_id: c for c in clubs if c.president_id}

    _admin_id_set = {u.id for u in all_admins}
    _admin_entries = [e for e in users_list if e['user'].id in _admin_id_set]
    _member_entries = [e for e in users_list if e['user'].id not in _admin_id_set]

    def _member_sort_key(entry):
        u = entry['user']
        ms = entry['memberships']
        if not ms:
            return (99999, '', 1)
        approved_ms = [m for m in ms if m['membership'].status == 'approved']
        primary = approved_ms[0] if approved_ms else ms[0]
        club_id = primary['membership'].club_id
        is_not_leader = 0 if u.id in leader_map else 1
        return (club_id, '', is_not_leader)

    _member_entries.sort(key=_member_sort_key)
    users_list = _admin_entries + _member_entries

    _leader_uid_list = list(leader_map.keys())
    _leader_users_q = User.query.filter(User.id.in_(_leader_uid_list)).all() if _leader_uid_list else []
    _leader_user_map2 = {u.id: u for u in _leader_users_q}
    leaders_list = [(c, _leader_user_map2[c.president_id]) for c in clubs if c.president_id and c.president_id in _leader_user_map2]
    leaders_list.sort(key=lambda x: x[0].name)

    admin_messages = AdminMessage.query.order_by(AdminMessage.sent_at.desc()).limit(30).all()
    _msg_sender_ids = list({m.sender_id for m in admin_messages})
    admin_msg_senders = {u.id: u for u in User.query.filter(User.id.in_(_msg_sender_ids)).all()} if _msg_sender_ids else {}

    _ac_rows = db.session.query(ClubMember.club_id, _func.count(ClubMember.id)) \
        .filter(ClubMember.status == 'approved').group_by(ClubMember.club_id).all()
    _ac_map = {cid: cnt for cid, cnt in _ac_rows}
    club_member_counts = [{'club': c, 'count': _ac_map.get(c.id, 0)} for c in clubs]

    total_users = User.query.count()
    pending_count = ClubMember.query.filter_by(status='pending').count()
    live_event_count = Event.query.filter_by(status='approved').count()
    total_messages = ClubMessage.query.count()
    liu_news = LiuNews.query.order_by(LiuNews.created_at.desc()).all()

    all_approved = ClubMember.query.filter_by(status='approved').all()
    _uid_set = list({m.user_id for m in all_approved})
    _users_cache = {u.id: u for u in User.query.filter(User.id.in_(_uid_set)).all()} if _uid_set else {}
    club_approved_users = {}
    for m in all_approved:
        u = _users_cache.get(m.user_id)
        if u:
            club_approved_users.setdefault(m.club_id, []).append(u)

    current_user = User.query.get(session['user_id'])
    is_super_admin = current_user and current_user.email == SUPER_ADMIN_EMAIL
    non_super_admins = [u for u in all_admins if u.email != SUPER_ADMIN_EMAIL]

    _now = datetime.utcnow()
    _month_labels = []
    _monthly_members = []
    _monthly_events = []
    for _i in range(5, -1, -1):
        _mo = _now.month - _i
        _yr = _now.year
        while _mo < 1:
            _mo += 12
            _yr -= 1
        _start = datetime(_yr, _mo, 1)
        _end_mo = _mo + 1 if _mo < 12 else 1
        _end_yr = _yr if _mo < 12 else _yr + 1
        _end = datetime(_end_yr, _end_mo, 1)
        _month_labels.append(_start.strftime('%b %Y'))
        _monthly_members.append(
            ClubMember.query.filter(
                ClubMember.status == 'approved',
                ClubMember.joined_at >= _start,
                ClubMember.joined_at < _end
            ).count()
        )
        _monthly_events.append(
            Event.query.filter(
                Event.status == 'approved',
                Event.date >= _start,
                Event.date < _end
            ).count()
        )

    clear_chat_clubs = Club.query.filter(Club.clear_chat_requested == 1).all()
    pending_event_proposals = Event.query.filter_by(status='pending').order_by(Event.date.asc()).all()
    pending_ann_proposals   = Announcement.query.filter_by(status='pending').order_by(Announcement.created_at.desc()).all()
    _prop_ids = list({e.proposed_by for e in pending_event_proposals if e.proposed_by} |
                     {a.proposed_by for a in pending_ann_proposals   if a.proposed_by})
    proposers = {u.id: u for u in User.query.filter(User.id.in_(_prop_ids)).all()} if _prop_ids else {}
    proposal_clubs = {c.id: c for c in clubs}

    all_rsvps = EventRSVP.query.all()
    event_rsvp_counts = {}
    event_rsvp_user_ids = {}
    for r in all_rsvps:
        event_rsvp_counts[r.event_id] = event_rsvp_counts.get(r.event_id, 0) + 1
        event_rsvp_user_ids.setdefault(r.event_id, []).append(r.user_id)

    _all_rsvp_uid = list({uid for uids in event_rsvp_user_ids.values() for uid in uids})
    _rsvp_users_map = {u.id: u for u in User.query.filter(User.id.in_(_all_rsvp_uid)).all()} if _all_rsvp_uid else {}
    event_attendees = {
        eid: [_rsvp_users_map[uid] for uid in uids if uid in _rsvp_users_map]
        for eid, uids in event_rsvp_user_ids.items()
    }

    total_rsvps = sum(event_rsvp_counts.values())
    top_events = sorted(events, key=lambda e: event_rsvp_counts.get(e.id, 0), reverse=True)[:5]

    event_waitlist_counts = {}
    _event_ids = [e.id for e in events]
    if _event_ids:
        for _eid, _cnt in db.session.query(EventWaitlist.event_id, _func.count(EventWaitlist.id)).filter(
            EventWaitlist.event_id.in_(_event_ids)
        ).group_by(EventWaitlist.event_id).all():
            event_waitlist_counts[_eid] = _cnt

    return render_template('admin.html',
        users=users,
        clubs=clubs,
        events=events,
        announcements=announcements,
        users_list=users_list,
        club_member_counts=club_member_counts,
        total_users=total_users,
        pending_count=pending_count,
        live_event_count=live_event_count,
        event_clubs=event_clubs,
        liu_news=liu_news,
        club_approved_users=club_approved_users,
        leader_map=leader_map,
        is_super_admin=is_super_admin,
        non_super_admins=non_super_admins,
        all_members=users,
        pending_event_proposals=pending_event_proposals,
        pending_ann_proposals=pending_ann_proposals,
        proposers=proposers,
        proposal_clubs=proposal_clubs,
        clear_chat_clubs=clear_chat_clubs,
        month_labels=_month_labels,
        monthly_members=_monthly_members,
        monthly_events=_monthly_events,
        campuses=CAMPUSES,
        event_rsvp_counts=event_rsvp_counts,
        event_attendees=event_attendees,
        event_waitlist_counts=event_waitlist_counts,
        total_rsvps=total_rsvps,
        total_messages=total_messages,
        top_events=top_events,
        report_date=datetime.utcnow().strftime('%B %d, %Y at %I:%M %p') + ' UTC',
        leaders_list=leaders_list,
        admin_messages=admin_messages,
        admin_msg_senders=admin_msg_senders,
    )

@app.route('/admin/approve/<int:member_id>', methods=['POST'])
@admin_required
def approve_member(member_id):
    m = ClubMember.query.get_or_404(member_id)
    other = ClubMember.query.filter_by(user_id=m.user_id, status='approved').filter(
        ClubMember.club_id != m.club_id
    ).first()
    if other:
        return redirect('/admin')
    m.status = 'approved'
    m.joined_at = datetime.utcnow()
    _c = Club.query.get(m.club_id)
    if _c:
        _notify(m.user_id, f'Your application to join {_c.name} was approved!', f'/club/{m.club_id}')
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/grant_admin', methods=['POST'])
@admin_required
def grant_admin():
    current = User.query.get(session['user_id'])
    if not current or current.email != SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    try:
        user_id = int(request.form.get('user_id', 0))
    except (ValueError, TypeError):
        return redirect('/admin')
    target = User.query.get_or_404(user_id)
    if target.role == 'member':
        target.role = 'admin'
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/revoke_admin/<int:user_id>', methods=['POST'])
@admin_required
def revoke_admin(user_id):
    current = User.query.get(session['user_id'])
    if not current or current.email != SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    target = User.query.get_or_404(user_id)
    if target.email != SUPER_ADMIN_EMAIL and target.role == 'admin':
        target.role = 'member'
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    new_password = request.form.get('new_password', '')[:128]
    if len(new_password) >= 6:
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Password updated.', 'success')
    else:
        flash('Password must be at least 6 characters.', 'error')
    return redirect('/admin')

@app.route('/admin/reject/<int:member_id>', methods=['POST'])
@admin_required
def reject_member(member_id):
    m = ClubMember.query.get_or_404(member_id)
    club = Club.query.get(m.club_id)
    if club and club.president_id == m.user_id:
        return redirect('/admin')
    m.status = 'rejected'
    if club:
        _notify(m.user_id, f'Your application to join {club.name} was not approved.', f'/club/{m.club_id}')
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        return redirect('/admin')
    target = User.query.get_or_404(user_id)
    if target.email == SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    current = User.query.get(session['user_id'])
    if target.role == 'admin' and (not current or current.email != SUPER_ADMIN_EMAIL):
        return redirect('/admin')
    ClubMember.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ChatReaction.query.filter(ChatReaction.message_id.in_(
        db.session.query(ClubMessage.id).filter_by(user_id=user_id)
    )).delete(synchronize_session=False)
    ClubMessage.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ChatReaction.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    EventRSVP.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    EventWaitlist.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Club.query.filter_by(president_id=user_id).update({'president_id': None})
    Event.query.filter_by(proposed_by=user_id).update({'proposed_by': None})
    Announcement.query.filter_by(proposed_by=user_id).update({'proposed_by': None})
    db.session.delete(target)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/remove_from_club/<int:member_id>', methods=['POST'])
@admin_required
def remove_from_club(member_id):
    m = ClubMember.query.get_or_404(member_id)
    club = Club.query.get(m.club_id)
    if club and club.president_id == m.user_id:
        return redirect('/admin')
    db.session.delete(m)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/add_club', methods=['POST'])
@admin_required
def add_club():
    name = request.form.get('name', '').strip()[:100]
    if not name:
        return redirect('/admin')
    desc = request.form.get('description', '').strip()[:500]
    emoji = request.form.get('emoji', '🏫').strip()[:10] or '🏫'
    c = Club(name=name, description=desc, logo_emoji=emoji)
    db.session.add(c)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/edit_club/<int:club_id>', methods=['POST'])
@admin_required
def edit_club(club_id):
    c = Club.query.get_or_404(club_id)
    c.name = request.form.get('name', '').strip()[:100] or c.name
    c.description = request.form.get('description', '').strip()[:500]
    c.logo_emoji = request.form.get('emoji', '').strip()[:10] or c.logo_emoji
    c.cover_url = _safe_url(request.form.get('cover_url', ''))
    c.logo_url = _safe_url(request.form.get('logo_url', ''))
    c.instagram = _safe_url(request.form.get('instagram', ''), max_len=200)
    c.twitter = _safe_url(request.form.get('twitter', ''), max_len=200)
    c.facebook = _safe_url(request.form.get('facebook', ''), max_len=200)
    c.website = _safe_url(request.form.get('website', ''), max_len=200)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/set_president/<int:club_id>', methods=['POST'])
@admin_required
def set_president(club_id):
    club = Club.query.get_or_404(club_id)
    president_id = request.form.get('president_id')
    if not president_id:
        club.president_id = None
    else:
        try:
            pid = int(president_id)
        except (ValueError, TypeError):
            return redirect('/admin')
        membership = ClubMember.query.filter_by(
            user_id=pid, club_id=club_id, status='approved'
        ).first()
        if not membership:
            return redirect('/admin')
        club.president_id = pid
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/delete_club/<int:club_id>', methods=['POST'])
@admin_required
def delete_club(club_id):
    ChatReaction.query.filter(ChatReaction.message_id.in_(
        db.session.query(ClubMessage.id).filter_by(club_id=club_id)
    )).delete(synchronize_session=False)
    EventRSVP.query.filter(EventRSVP.event_id.in_(
        db.session.query(Event.id).filter_by(club_id=club_id)
    )).delete(synchronize_session=False)
    EventWaitlist.query.filter(EventWaitlist.event_id.in_(
        db.session.query(Event.id).filter_by(club_id=club_id)
    )).delete(synchronize_session=False)
    ClubMember.query.filter_by(club_id=club_id).delete(synchronize_session=False)
    ClubMessage.query.filter_by(club_id=club_id).delete(synchronize_session=False)
    Event.query.filter_by(club_id=club_id).delete(synchronize_session=False)
    Announcement.query.filter_by(club_id=club_id).delete(synchronize_session=False)
    c = Club.query.get_or_404(club_id)
    db.session.delete(c)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/add_event', methods=['POST'])
@admin_required
def add_event():
    title       = (request.form.get('title') or '').strip()[:200]
    club_id_str = request.form.get('club_id', '').strip()
    try:
        club_id = None if not club_id_str else int(club_id_str)
    except (ValueError, TypeError):
        club_id = None
    date_str    = request.form.get('date')
    location    = request.form.get('location', '').strip()[:200]
    description = request.form.get('description', '').strip()[:2000]
    poster_url  = read_uploaded_image('poster_file')
    campus      = request.form.get('campus', '').strip()
    if campus not in CAMPUSES:
        campus = None
    try:
        rsvp_limit = int(request.form.get('rsvp_limit', 0)) or None
        if rsvp_limit is not None and rsvp_limit <= 0:
            rsvp_limit = None
    except (ValueError, TypeError):
        rsvp_limit = None
    if not title or not date_str:
        return redirect('/admin')
    try:
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        return redirect('/admin')
    e = Event(club_id=club_id, title=title, date=date, location=location,
              description=description, poster_url=poster_url,
              campus=campus, rsvp_limit=rsvp_limit)
    db.session.add(e)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/edit_event/<int:event_id>', methods=['POST'])
@admin_required
def edit_event(event_id):
    e = Event.query.get_or_404(event_id)
    e.title       = request.form.get('title', '').strip()[:200] or e.title
    e.location    = request.form.get('location', '').strip()[:200] or None
    e.description = request.form.get('description', '').strip()[:2000] or None
    new_poster    = read_uploaded_image('poster_file')
    if new_poster:
        e.poster_url = new_poster
    date_str = request.form.get('date')
    if date_str:
        try:
            e.date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            pass
    campus = request.form.get('campus', '').strip()
    if campus in CAMPUSES:
        e.campus = campus
    elif campus == '':
        e.campus = None
    try:
        rl = request.form.get('rsvp_limit', '').strip()
        val = int(rl) if rl else None
        e.rsvp_limit = val if (val is None or val > 0) else None
    except (ValueError, TypeError):
        pass
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/delete_event/<int:event_id>', methods=['POST'])
@admin_required
def delete_event(event_id):
    e = Event.query.get_or_404(event_id)
    EventRSVP.query.filter_by(event_id=event_id).delete(synchronize_session=False)
    EventWaitlist.query.filter_by(event_id=event_id).delete(synchronize_session=False)
    if e.proposed_by:
        Notification.query.filter(
            Notification.user_id == e.proposed_by,
            Notification.message.in_([
                f'Your event "{e.title}" was approved!',
                f'Your event "{e.title}" was not approved.',
            ])
        ).delete(synchronize_session=False)
    db.session.delete(e)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/approve_event_proposal/<int:event_id>', methods=['POST'])
@admin_required
def approve_event_proposal(event_id):
    e = Event.query.get_or_404(event_id)
    e.status = 'approved'
    if e.proposed_by:
        club_exists = e.club_id and Club.query.get(e.club_id)
        _notify(e.proposed_by, f'Your event "{e.title}" was approved!',
                f'/club/{e.club_id}' if club_exists else '/')
    db.session.commit()
    flash(f'Event "{e.title}" approved.', 'success')
    return redirect('/admin')

@app.route('/admin/reject_event_proposal/<int:event_id>', methods=['POST'])
@admin_required
def reject_event_proposal(event_id):
    e = Event.query.get_or_404(event_id)
    e.status = 'rejected'
    if e.proposed_by:
        _notify(e.proposed_by, f'Your event "{e.title}" was not approved.', f'/club/{e.club_id}' if e.club_id else '/')
    db.session.commit()
    flash(f'Event "{e.title}" rejected.', 'success')
    return redirect('/admin')

@app.route('/admin/approve_ann_proposal/<int:ann_id>', methods=['POST'])
@admin_required
def approve_ann_proposal(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    a.status = 'approved'
    if a.proposed_by:
        _notify(a.proposed_by, f'Your announcement "{a.title}" was approved!', f'/club/{a.club_id}' if a.club_id else '/')
    _notify_announcement_members(a)
    db.session.commit()
    flash(f'Announcement "{a.title}" approved.', 'success')
    return redirect('/admin')

@app.route('/admin/reject_ann_proposal/<int:ann_id>', methods=['POST'])
@admin_required
def reject_ann_proposal(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    a.status = 'rejected'
    if a.proposed_by:
        _notify(a.proposed_by, f'Your announcement "{a.title}" was not approved.', f'/club/{a.club_id}' if a.club_id else '/')
    db.session.commit()
    flash(f'Announcement "{a.title}" rejected.', 'success')
    return redirect('/admin')

@app.route('/admin/message_leaders', methods=['POST'])
@admin_required
def admin_message_leaders():
    message = (request.form.get('message') or '').strip()
    leader_ids_raw = request.form.getlist('leader_ids')
    if not message:
        flash('Message cannot be empty.', 'error')
        return redirect('/admin')
    if not leader_ids_raw:
        flash('Select at least one leader.', 'error')
        return redirect('/admin')
    try:
        leader_ids = [int(x) for x in leader_ids_raw]
    except (ValueError, TypeError):
        flash('Invalid leader selection.', 'error')
        return redirect('/admin')
    leaders = User.query.filter(User.id.in_(leader_ids)).all()
    _all_clubs = Club.query.all()
    _lmap = {c.president_id: c for c in _all_clubs if c.president_id}
    labels = []
    for u in leaders:
        club = _lmap.get(u.id)
        labels.append(f"{u.full_name} ({club.name if club else '?'})")
    recipient_label = ', '.join(labels) if len(labels) <= 4 else f"{len(labels)} leaders"
    sender_id = session['user_id']
    sender = User.query.get(sender_id)
    sender_name = sender.full_name if sender else 'Admin'
    if sender and sender.email == SUPER_ADMIN_EMAIL:
        sender_role = 'Host'
    else:
        sender_role = 'Admin'
    msg = AdminMessage(
        sender_id=sender_id,
        message=message,
        recipient_ids=','.join(str(x) for x in leader_ids),
        recipient_label=recipient_label,
    )
    db.session.add(msg)
    db.session.flush()
    sent_count = 0
    for uid in leader_ids:
        _notify(uid, f'Direct message from {sender_name} ({sender_role}): {message}', '/',
                admin_message_id=msg.id)
        sent_count += 1
    db.session.commit()
    flash(f'Message sent to {sent_count} leader(s).', 'success')
    return redirect('/admin')

@app.route('/admin/delete_admin_message/<int:msg_id>', methods=['POST'])
@admin_required
def delete_admin_message(msg_id):
    msg = AdminMessage.query.get_or_404(msg_id)
    Notification.query.filter_by(admin_message_id=msg_id).delete(synchronize_session=False)
    db.session.delete(msg)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/bulk_delete_admin_messages', methods=['POST'])
@admin_required
def bulk_delete_admin_messages():
    ids = [int(x) for x in request.form.getlist('ids') if x]
    if ids:
        Notification.query.filter(Notification.admin_message_id.in_(ids)).delete(synchronize_session=False)
        AdminMessage.query.filter(AdminMessage.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/bulk_delete_announcements', methods=['POST'])
@admin_required
def bulk_delete_announcements():
    ids = [int(x) for x in request.form.getlist('ids') if x]
    if ids:
        anns = Announcement.query.filter(Announcement.id.in_(ids)).all()
        for a in anns:
            Notification.query.filter(
                Notification.message.like('Announcement — {}:%'.format(
                    a.title.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                ), escape='\\')
            ).delete(synchronize_session=False)
            if a.proposed_by:
                Notification.query.filter(
                    Notification.user_id == a.proposed_by,
                    Notification.message.in_([
                        f'Your announcement "{a.title}" was approved!',
                        f'Your announcement "{a.title}" was not approved.',
                    ])
                ).delete(synchronize_session=False)
            db.session.delete(a)
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/bulk_delete_news', methods=['POST'])
@admin_required
def bulk_delete_news():
    ids = [int(x) for x in request.form.getlist('ids') if x]
    if ids:
        LiuNews.query.filter(LiuNews.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/clear_chat/<int:club_id>', methods=['POST'])
@admin_required
def admin_clear_chat(club_id):
    current = User.query.get(session['user_id'])
    if not current or current.email != SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    ChatReaction.query.filter(ChatReaction.message_id.in_(
        db.session.query(ClubMessage.id).filter_by(club_id=club_id)
    )).delete(synchronize_session=False)
    ClubMessage.query.filter_by(club_id=club_id).delete(synchronize_session=False)
    club = Club.query.get_or_404(club_id)
    club.clear_chat_requested = 0
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/dismiss_clear_chat/<int:club_id>', methods=['POST'])
@admin_required
def admin_dismiss_clear_chat(club_id):
    current = User.query.get(session['user_id'])
    if not current or current.email != SUPER_ADMIN_EMAIL:
        return redirect('/admin')
    club = Club.query.get_or_404(club_id)
    club.clear_chat_requested = 0
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/add_news', methods=['POST'])
@admin_required
def add_news():
    title   = request.form.get('title', '').strip()[:200]
    content = request.form.get('content', '').strip()[:5000]
    if title and content:
        n = LiuNews(title=title, content=content)
        db.session.add(n)
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/delete_news/<int:news_id>', methods=['POST'])
@admin_required
def delete_news(news_id):
    n = LiuNews.query.get_or_404(news_id)
    db.session.delete(n)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/add_announcement', methods=['POST'])
@admin_required
def add_announcement():
    title   = request.form.get('title', '').strip()[:200]
    content = request.form.get('content', '').strip()[:2000]
    try:
        club_id = int(request.form.get('club_id')) if request.form.get('club_id') else None
    except (ValueError, TypeError):
        club_id = None
    publish_at = None
    status = 'approved'
    publish_at_str = request.form.get('publish_at', '').strip()
    if publish_at_str:
        try:
            publish_at = datetime.strptime(publish_at_str, '%Y-%m-%dT%H:%M')
            if publish_at > datetime.utcnow():
                status = 'pending'
        except (ValueError, TypeError):
            pass
    if title and content:
        a = Announcement(title=title, content=content, club_id=club_id,
                         status=status, publish_at=publish_at)
        db.session.add(a)
        db.session.flush()
        if status == 'approved':
            _notify_announcement_members(a)
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/edit_announcement/<int:ann_id>', methods=['POST'])
@admin_required
def edit_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    title   = request.form.get('title', '').strip()[:200]
    content = request.form.get('content', '').strip()[:2000]
    if title and content:
        a.title   = title
        a.content = content
        db.session.commit()
    return redirect('/admin')

@app.route('/admin/delete_announcement/<int:ann_id>', methods=['POST'])
@admin_required
def delete_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    _safe_title = a.title.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    Notification.query.filter(
        Notification.message.like(f'Announcement — {_safe_title}:%', escape='\\')
    ).delete(synchronize_session=False)
    if a.proposed_by:
        Notification.query.filter(
            Notification.user_id == a.proposed_by,
            Notification.message.in_([
                f'Your announcement "{a.title}" was approved!',
                f'Your announcement "{a.title}" was not approved.',
            ])
        ).delete(synchronize_session=False)
    db.session.delete(a)
    db.session.commit()
    return redirect('/admin')


ALLOWED_REACTION_EMOJIS = {'👍', '❤️', '😂', '😮', '👏'}

@app.route('/club/<int:club_id>/react/<int:msg_id>', methods=['POST'])
@login_required
def react_message(club_id, msg_id):
    user_id = session['user_id']
    club = Club.query.get_or_404(club_id)
    is_leader = club.president_id == user_id
    membership = ClubMember.query.filter_by(user_id=user_id, club_id=club_id, status='approved').first()
    if not is_leader and not membership:
        return jsonify({'error': 'unauthorized'}), 403
    emoji = request.form.get('emoji', '')
    if emoji not in ALLOWED_REACTION_EMOJIS:
        return jsonify({'error': 'invalid emoji'}), 400
    msg = ClubMessage.query.get_or_404(msg_id)
    if msg.club_id != club_id:
        return jsonify({'error': 'not found'}), 404
    existing = ChatReaction.query.filter_by(message_id=msg_id, user_id=user_id, emoji=emoji).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(ChatReaction(message_id=msg_id, user_id=user_id, emoji=emoji))
    db.session.commit()
    counts = {}
    for r in ChatReaction.query.filter_by(message_id=msg_id).all():
        counts[r.emoji] = counts.get(r.emoji, 0) + 1
    user_emojis = [r.emoji for r in ChatReaction.query.filter_by(message_id=msg_id, user_id=user_id).all()]
    return jsonify({'counts': counts, 'user_emojis': user_emojis})

@app.route('/admin/pin_announcement/<int:ann_id>', methods=['POST'])
@admin_required
def admin_pin_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    a.pinned = not bool(a.pinned)
    db.session.commit()
    return redirect('/admin')

@app.route('/leader/pin_announcement/<int:ann_id>', methods=['POST'])
@login_required
def leader_pin_announcement(ann_id):
    club = get_leader_club(session['user_id'])
    a = Announcement.query.get_or_404(ann_id)
    if not club or a.club_id != club.id or a.status != 'approved':
        return redirect(f'/club/{club.id}' if club else '/')
    a.pinned = not bool(a.pinned)
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/admin/toggle_recruitment/<int:club_id>', methods=['POST'])
@admin_required
def admin_toggle_recruitment(club_id):
    c = Club.query.get_or_404(club_id)
    c.accepting_members = not bool(c.accepting_members)
    db.session.commit()
    return redirect('/admin')

@app.route('/leader/toggle_recruitment', methods=['POST'])
@login_required
def leader_toggle_recruitment():
    club = get_leader_club(session['user_id'])
    if not club:
        return redirect('/')
    club.accepting_members = not bool(club.accepting_members)
    db.session.commit()
    return redirect(f'/club/{club.id}')

@app.route('/event/<int:event_id>/rsvp', methods=['POST'])
@login_required
def toggle_rsvp(event_id):
    user_id = session['user_id']
    # with_for_update() locks the event row so concurrent requests serialize,
    # preventing two users from both passing the capacity check simultaneously.
    e = db.session.query(Event).with_for_update().filter_by(id=event_id).first()
    if not e:
        abort(404)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if e.status != 'approved':
        return (jsonify(error='not_approved'), 400) if is_ajax else redirect('/')
    existing = EventRSVP.query.filter_by(event_id=event_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.flush()
        _promote_waitlist(event_id)
        db.session.commit()
        count = EventRSVP.query.filter_by(event_id=event_id).count()
        wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
        if is_ajax:
            return jsonify(rsvped=False, count=count, rsvp_limit=e.rsvp_limit, waitlist_count=wl_count)
    else:
        count = EventRSVP.query.filter_by(event_id=event_id).count()
        if e.rsvp_limit and count >= e.rsvp_limit:
            wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
            return (jsonify(error='full', count=count, rsvp_limit=e.rsvp_limit, waitlist_count=wl_count), 409) if is_ajax else redirect(request.referrer or '/')
        db.session.add(EventRSVP(event_id=event_id, user_id=user_id))
        db.session.commit()
        count = EventRSVP.query.filter_by(event_id=event_id).count()
        wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
        if is_ajax:
            return jsonify(rsvped=True, count=count, rsvp_limit=e.rsvp_limit, waitlist_count=wl_count)
    return redirect(request.referrer or '/')

@app.route('/event/<int:event_id>/waitlist', methods=['POST'])
@login_required
def toggle_waitlist(event_id):
    user_id = session['user_id']
    e = db.session.query(Event).with_for_update().filter_by(id=event_id).first()
    if not e:
        abort(404)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if e.status != 'approved':
        return (jsonify(error='not_approved'), 400) if is_ajax else redirect('/')
    if EventRSVP.query.filter_by(event_id=event_id, user_id=user_id).first():
        return (jsonify(error='already_rsvped'), 400) if is_ajax else redirect(request.referrer or '/')
    existing = EventWaitlist.query.filter_by(event_id=event_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
        if is_ajax:
            return jsonify(on_waitlist=False, waitlist_count=wl_count)
    else:
        rsvp_count = EventRSVP.query.filter_by(event_id=event_id).count()
        if not e.rsvp_limit or rsvp_count < e.rsvp_limit:
            db.session.add(EventRSVP(event_id=event_id, user_id=user_id))
            db.session.commit()
            count = EventRSVP.query.filter_by(event_id=event_id).count()
            wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
            if is_ajax:
                return jsonify(rsvped=True, count=count, rsvp_limit=e.rsvp_limit,
                               on_waitlist=False, waitlist_count=wl_count)
        else:
            db.session.add(EventWaitlist(event_id=event_id, user_id=user_id))
            db.session.commit()
            wl_count = EventWaitlist.query.filter_by(event_id=event_id).count()
            if is_ajax:
                return jsonify(on_waitlist=True, waitlist_count=wl_count)
    return redirect(request.referrer or '/')


@app.route('/calendar/<string:token>.ics')
def calendar_feed(token):
    user = User.query.filter_by(calendar_token=token).first()
    if not user:
        abort(404)
    def esc(s):
        return (s or '').replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;').replace('\n', '\\n')
    user_club_ids = [m.club_id for m in ClubMember.query.filter_by(user_id=user.id, status='approved').all()]
    rsvp_event_ids = [r.event_id for r in EventRSVP.query.filter_by(user_id=user.id).all()]
    or_conds = []
    if user_club_ids:
        or_conds.append(Event.club_id.in_(user_club_ids))
    if rsvp_event_ids:
        or_conds.append(Event.id.in_(rsvp_event_ids))
    events = Event.query.filter(Event.status == 'approved', db.or_(*or_conds)).all() if or_conds else []
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        'PRODID:-//LIU Clubs//Personal Feed//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
        f'X-WR-CALNAME:LIU Clubs — {esc(user.full_name)}',
    ]
    for ev in events:
        dtstart = ev.date.strftime('%Y%m%dT%H%M%SZ')
        dtend   = (ev.date + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')
        lines += [
            'BEGIN:VEVENT',
            f'UID:liu-clubs-event-{ev.id}@liu.edu.lb',
            f'DTSTART:{dtstart}', f'DTEND:{dtend}',
            f'SUMMARY:{esc(ev.title)}',
            f'DESCRIPTION:{esc(ev.description)}',
            f'LOCATION:{esc(ev.location)}',
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    return Response('\r\n'.join(lines), mimetype='text/calendar',
                    headers={'Content-Disposition': 'attachment; filename="liu-clubs.ics"'})


@app.route('/notifications')
@login_required
def notifications_page():
    user_id = session['user_id']
    user = User.query.get(user_id)
    if not user:
        session.clear()
        return redirect('/login')
    notifs = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(100).all()
    Notification.query.filter_by(user_id=user_id, read=False).update({'read': True})
    db.session.commit()
    return render_template('notifications.html', notifications=notifs, user=user)

@app.route('/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=session['user_id'], read=False).update({'read': True})
    db.session.commit()
    return redirect('/notifications')


with app.app_context():
    db.create_all()
    _migrate()

    if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']:
        for stmt in [
            'ALTER TABLE event ALTER COLUMN club_id DROP NOT NULL',
            'ALTER TABLE event ALTER COLUMN poster_url TYPE TEXT',
            'ALTER TABLE "user" ADD COLUMN campus VARCHAR(50)',
            'ALTER TABLE "user" ADD COLUMN gender VARCHAR(10) DEFAULT \'male\'',
            'ALTER TABLE club ADD COLUMN clear_chat_requested INTEGER DEFAULT 0',
            'ALTER TABLE club ADD COLUMN accepting_members BOOLEAN DEFAULT TRUE',
            'ALTER TABLE announcement ADD COLUMN pinned BOOLEAN DEFAULT FALSE',
            'ALTER TABLE event ADD COLUMN rsvp_limit INTEGER',
            'ALTER TABLE event ADD COLUMN campus VARCHAR(50)',
            'ALTER TABLE "user" ADD COLUMN last_seen_announcements TIMESTAMP',
            'ALTER TABLE announcement ADD COLUMN publish_at TIMESTAMP',
            'ALTER TABLE "user" ADD COLUMN calendar_token VARCHAR(64)',
            "ALTER TABLE event ADD COLUMN status VARCHAR(20) DEFAULT 'approved'",
            'ALTER TABLE event ADD COLUMN proposed_by INTEGER',
            'ALTER TABLE event ADD COLUMN leader_note TEXT',
            "ALTER TABLE announcement ADD COLUMN status VARCHAR(20) DEFAULT 'approved'",
            'ALTER TABLE announcement ADD COLUMN proposed_by INTEGER',
            'ALTER TABLE announcement ADD COLUMN leader_note TEXT',
            'CREATE INDEX IF NOT EXISTS idx_clubmember_user_status ON club_member(user_id, status)',
            'CREATE INDEX IF NOT EXISTS idx_clubmember_club_status ON club_member(club_id, status)',
            'CREATE INDEX IF NOT EXISTS idx_notification_user_read ON notification(user_id, read)',
            'CREATE INDEX IF NOT EXISTS idx_notification_user_created ON notification(user_id, created_at DESC)',
            'CREATE INDEX IF NOT EXISTS idx_event_date_status ON event(date, status)',
            'CREATE INDEX IF NOT EXISTS idx_eventrsvp_user ON event_rsvp(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_eventwaitlist_user ON event_waitlist(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_club_president ON club(president_id)',
            'CREATE INDEX IF NOT EXISTS idx_announcement_status_created ON announcement(status, created_at DESC)',
            'CREATE INDEX IF NOT EXISTS idx_announcement_club ON announcement(club_id)',
            'ALTER TABLE notification ADD COLUMN admin_message_id INTEGER',
        ]:
            try:
                db.session.execute(_t(stmt))
                db.session.commit()
            except Exception:
                db.session.rollback()

    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        try:
            club_cols = [c['name'] for c in inspector.get_columns('club')]
            for col, typ in [
                ('president_id', 'INTEGER'),
                ('cover_url',    'VARCHAR(300)'),
                ('logo_url',     'VARCHAR(300)'),
                ('about_us',     'TEXT'),
                ('instagram',    'VARCHAR(200)'),
                ('twitter',      'VARCHAR(200)'),
                ('facebook',     'VARCHAR(200)'),
                ('website',      'VARCHAR(200)'),
            ]:
                if col not in club_cols:
                    db.session.execute(_t(f'ALTER TABLE club ADD COLUMN {col} {typ}'))

            event_cols = [c['name'] for c in inspector.get_columns('event')]
            if 'poster_url' not in event_cols:
                db.session.execute(_t('ALTER TABLE event ADD COLUMN poster_url VARCHAR(300)'))

            user_cols = [c['name'] for c in inspector.get_columns('user')]
            if 'campus' not in user_cols:
                db.session.execute(_t('ALTER TABLE user ADD COLUMN campus VARCHAR(50)'))
            if 'gender' not in user_cols:
                db.session.execute(_t("ALTER TABLE user ADD COLUMN gender VARCHAR(10) DEFAULT 'male'"))

            db.session.commit()
        except Exception:
            db.session.rollback()

    admin = User.query.filter_by(email=SUPER_ADMIN_EMAIL).first()
    if not admin:
        admin = User(password=generate_password_hash('admin123'))
        db.session.add(admin)
    admin.full_name  = 'Fares Al Ahmed'
    admin.student_id = '32330006'
    admin.email      = SUPER_ADMIN_EMAIL
    admin.role       = 'admin'
    db.session.commit()

    _existing_news_titles = {n.title for n in LiuNews.query.all()}
    _seed_news = [
        ('Pre-Fall 2026/2027 Registration',
         "Mark your calendars! Registration for the Pre-Fall 2026/2027 session opens on Friday, May 15 at 10:00 am. Don't miss your chance to secure your courses."),
        ('97% Passing Rate & Nutrition Colloquium — Winter 2025',
         'We are proud to announce an outstanding 97% passing rate across programs. Additionally, the Nutrition Colloquium for the Winter 2025 session will take place soon. Stay tuned for more details!'),
        ('New Online Library Website is Officially Live!',
         'Explore our brand-new online library website. Access resources anytime, anywhere. Visit: https://library.liu.edu.lb/'),
    ]
    for _title, _content in _seed_news:
        if _title not in _existing_news_titles:
            db.session.add(LiuNews(title=_title, content=_content))
    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

