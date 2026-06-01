function togglePw(btn) {
    btn.classList.add('fading');
    setTimeout(function() {
        const input = btn.previousElementSibling;
        const showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        btn.innerHTML = showing ? '<i data-lucide="eye"></i>' : '<i data-lucide="eye-off"></i>';
        if (window.lucide) lucide.createIcons();
        btn.classList.remove('fading');
    }, 150);
}

const dropBtn  = document.getElementById('userDropdownBtn');
const dropMenu = document.getElementById('userDropdownMenu');
if (dropBtn && dropMenu) {
    dropBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        const open = dropMenu.classList.toggle('open');
        dropBtn.classList.toggle('open', open);
        dropBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function() {
        dropMenu.classList.remove('open');
        dropBtn.classList.remove('open');
        dropBtn.setAttribute('aria-expanded', 'false');
    });
}

document.querySelectorAll('.nav-link[data-section]').forEach(function(link) {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        const target = this.getAttribute('data-section');

        document.querySelectorAll('.section').forEach(function(s) {
            s.classList.remove('active');
        });

        if (this.closest('.top-nav')) {
            document.querySelectorAll('.nav-link').forEach(function(l) {
                l.classList.remove('active');
            });
            this.classList.add('active');
        }

        const section = document.getElementById(target);
        if (section) section.classList.add('active');
    });
});

document.querySelectorAll('.nav-link-inline[data-section]').forEach(function(link) {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        const target = this.getAttribute('data-section');

        document.querySelectorAll('.section').forEach(function(s) {
            s.classList.remove('active');
        });

        document.querySelectorAll('.nav-link').forEach(function(l) {
            l.classList.remove('active');
        });

        const section = document.getElementById(target);
        if (section) section.classList.add('active');

        const navLink = document.querySelector('.top-nav .nav-link[data-section="' + target + '"]');
        if (navLink) navLink.classList.add('active');
    });
});

document.querySelectorAll('.about-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const club_id = this.getAttribute('data-club');
        const about = document.getElementById('about-' + club_id);
        if (!about) return;

        if (about.style.display === 'block') {
            about.style.display = 'none';
            this.textContent = 'About';
        } else {
            about.style.display = 'block';
            this.textContent = 'Hide';
        }
    });
});

function showJoinForm() {
    const btn = document.getElementById('join-btn');
    const form = document.getElementById('join-form');
    if (btn) btn.style.display = 'none';
    if (form) form.style.display = 'block';
}

function hideJoinForm() {
    const btn = document.getElementById('join-btn');
    const form = document.getElementById('join-form');
    if (btn) btn.style.display = 'inline-block';
    if (form) form.style.display = 'none';
}

const grantForm = document.getElementById('grantAdminForm');
const grantSelect = document.getElementById('grantUserSelect');
if (grantForm && grantSelect) {
    grantForm.addEventListener('submit', function(e) {
        if (!grantSelect.value) { e.preventDefault(); }
    });
}

document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const target = this.getAttribute('data-tab');

        document.querySelectorAll('.tab-content').forEach(function(t) {
            t.classList.remove('active');
        });

        document.querySelectorAll('.tab-btn').forEach(function(b) {
            b.classList.remove('active');
        });

        const tab = document.getElementById(target);
        if (tab) tab.classList.add('active');
        this.classList.add('active');
    });
});

function toggleClubEdit(club_id) {
    const row = document.getElementById('club-edit-' + club_id);
    if (!row) return;
    row.style.display = (row.style.display === 'table-row') ? 'none' : 'table-row';
}

function toggleLeaderEdit(club_id) {
    const row = document.getElementById('club-leader-' + club_id);
    if (!row) return;
    row.style.display = (row.style.display === 'table-row') ? 'none' : 'table-row';
}

function toggleResetPw(uid) {
    const form = document.getElementById('resetform-' + uid);
    if (!form) return;
    form.style.display = (form.style.display === 'none') ? 'block' : 'none';
}

function toggleEventEdit(event_id) {
    const row = document.getElementById('event-edit-' + event_id);
    if (!row) return;
    row.style.display = (row.style.display === 'table-row') ? 'none' : 'table-row';
}

function toggleAnnEdit(ann_id) {
    const view = document.getElementById('ann-view-' + ann_id);
    const edit = document.getElementById('ann-edit-' + ann_id);
    if (!view || !edit) return;
    const showing = edit.style.display !== 'none';
    view.style.display = showing ? 'block' : 'none';
    edit.style.display = showing ? 'none' : 'block';
}

(function() {
    const slides = document.querySelectorAll('.news-slide');
    const dots   = document.querySelectorAll('.news-dot');
    if (slides.length < 2) return;
    let current = 0;
    function goTo(idx) {
        slides[current].classList.remove('news-slide-active');
        if (dots[current]) dots[current].classList.remove('news-dot-active');
        current = (idx + slides.length) % slides.length;
        slides[current].classList.add('news-slide-active');
        if (dots[current]) dots[current].classList.add('news-dot-active');
    }
    dots.forEach(function(dot) {
        dot.addEventListener('click', function() { goTo(parseInt(this.getAttribute('data-idx'))); });
    });
    setInterval(function() { goTo(current + 1); }, 4000);
})();

(function() {
    const slides = document.querySelectorAll('.up-next-slide');
    const dots   = document.querySelectorAll('.up-next-dot');
    if (slides.length < 2) return;
    let current = 0;
    function goTo(idx) {
        slides[current].classList.remove('up-next-slide-active');
        if (dots[current]) dots[current].classList.remove('up-next-dot-active');
        current = (idx + slides.length) % slides.length;
        slides[current].classList.add('up-next-slide-active');
        if (dots[current]) dots[current].classList.add('up-next-dot-active');
    }
    dots.forEach(function(dot) {
        dot.addEventListener('click', function() { goTo(parseInt(this.getAttribute('data-idx'))); });
    });
    setInterval(function() { goTo(current + 1); }, 4000);
})();

document.querySelectorAll('.flash').forEach(function(msg) {
    if (msg.classList.contains('flash-permanent')) return;
    setTimeout(function() {
        msg.style.transition = 'opacity 0.5s';
        msg.style.opacity = '0';
        setTimeout(function() {
            if (msg.parentNode) msg.parentNode.removeChild(msg);
        }, 500);
    }, 4000);
});
