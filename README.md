# Chirp — a little more connected

A full-stack, Twitter-inspired microblog with a responsive dark interface. Sign up,
log in, share 280-character thoughts, follow people, explore profiles, search,
like posts, and delete your own posts. Data
persists in SQLite; the frontend uses plain HTML, CSS and JavaScript without a build step.

## Stack

- FastAPI, Pydantic 2, SQLAlchemy 2 and SQLite
- bcrypt password hashes and signed, expiring HS256 JWT access tokens
- Vanilla JavaScript Fetch API, localStorage sessions, accessible HTML and responsive CSS
- pytest + HTTPX integration tests; optional Docker backend
- Python 3.11+ (Docker uses 3.12). No Node.js required to run the app.

## Start locally

Run all commands from this project folder, `twiiter.clone/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python -m backend.init_env
python -m uvicorn backend.main:app --reload --port 8000
```

The setup helper generates a cryptographically random secret in `backend/.env`,
with owner-only permissions. It never overwrites an existing file or prints its secret.
Alternatively copy `backend/.env.example` to `backend/.env` and replace the placeholder
with the output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Missing/placeholder secrets intentionally prevent startup. Do not commit `.env`.

In a **second terminal**, from the same project folder:

```bash
python3 scripts/serve_frontend.py
```

Open **http://localhost:5500**. Keep both terminals running; stop them with Ctrl+C.
API docs: **http://localhost:8000/docs**. Health: **http://localhost:8000/health**.
The root `main.py` also supports the original `uvicorn main:app` command.
If an old backend already occupies port 8000, stop that instance first.

The included static server serves **only** the three public frontend files and binds
to localhost. Requests for secrets, databases, source files, or directory listings
are rejected. It is for local development, not production. For deployment serve only
`index.html`, `style.css`, and `script.js` from your web server.

### Configuration

`backend/config.py` loads `backend/.env` independently of the working directory.
Environment variables override the file. See `backend/.env.example` for names:

| Variable | Meaning |
| --- | --- |
| `SECRET_KEY` | Required random private signing key, minimum 32 characters |
| `DATABASE_URL` | Defaults to an absolute path to `backend/chirp.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime; default 60 minutes |
| `CORS_ORIGINS` | Comma-separated permitted frontend origins; default localhost/127.0.0.1 port 5500 |

If changing the API port/host, update `<meta name="api-base">` in `index.html`.
If changing the frontend origin, update `CORS_ORIGINS` and restart the API.
Use HTTP rather than opening the HTML as `file://`; that origin is not allowed.
Fonts are an optional Google Fonts enhancement, with system-font fallbacks.

## API

All request bodies are JSON. Protected endpoints require
`Authorization: Bearer <access_token>`.

| Method | Endpoint | Auth | Request / behavior |
| --- | --- | --- | --- |
| GET | `/health` | No | `{ "status": "ok" }` |
| POST | `/signup` | No | `{ "username": "alice", "email": "alice@example.com", "password": "password123" }`; returns user, 201 |
| POST | `/login` | No | `{ "username": "alice", "password": "password123" }`; returns access_token and token_type |
| GET | `/me` | Yes | Current user's id, username and email |
| GET | `/posts?limit=20&before=42` | Optional | Newest-first array; `before` is exclusive post ID cursor; max limit 100 |
| POST | `/posts` | Yes | `{ "content": "Hello, world!" }`; returns persisted post, 201 |
| POST | `/posts/{id}/like` | Yes | Toggle current user's like; returns updated post |
| DELETE | `/posts/{id}` | Yes | Owner only; 204 with no body; related likes cascade-delete |
| GET | `/posts?feed=following&limit=20&before=42` | Yes | Only followed users' posts; same exclusive ID cursor as Latest |
| GET | `/posts?user_id=7&limit=20&before=42` | Optional | One user's posts; missing user returns 404 |
| GET | `/users/{id}` | Optional | Public profile: username, joined_at, follower_count, following_count, followed_by_me |
| POST | `/users/{id}/follow` | Yes | Follow user; returns updated profile (200) |
| DELETE | `/users/{id}/follow` | Yes | Unfollow user; returns updated profile (200) |
| GET | `/users/{id}/followers?limit=20&before=42` | No | Public users following this user, descending user ID |
| GET | `/users/{id}/following?limit=20&before=42` | No | Public users this user follows, descending user ID |
| GET | `/search?q=hello&limit=20&user_before=42&post_before=99` | Optional | Search usernames and post text; separate result lists and cursors |

Posts include `id`, `user_id`, `username`, `content`, UTC `created_at`, `like_count`,
and `liked_by_me`. Public reads return `liked_by_me: false`. Errors use FastAPI's
`detail` field: 401 invalid credentials/token, 403 wrong owner, 404 absent post,
400 self-follow/self-unfollow, 409 duplicate account/conflicting like, 422 invalid input.

Usernames are 3–30 letters/numbers/underscores, normalized to lowercase. Emails
are validated and normalized to lowercase. Passwords require 8+ characters and
at most 72 UTF-8 **bytes**, because bcrypt has a byte limit. Posts are trimmed,
nonblank and at most 280 characters. Feed IDs track insertion order with UTC timestamps.
The app loads 20 posts at a time and supports loading older posts. Feed refresh is
manual; posting in Latest inserts the real saved response immediately without a page reload.

## Social features and pagination

- **Latest** remains the default (`GET /posts` or `feed=latest`), preserving the original API.
- **Following** strictly excludes your own posts and everyone you do not follow.
  Posting while on Following saves your chirp but does not insert it into the wrong feed.
- Follow/unfollow are **idempotent**: following twice leaves one relation; unfollowing
  twice leaves none. Both return 200 with the current profile. Self-follow and
  self-unfollow return 400; absent targets return 404. The database also enforces
  uniqueness and the no-self-follow rule, not just Python checks.
- Click a post author, search result or **My profile** to open a profile. Follower
  and following counts link to paginated user lists. Profiles use hash routes such
  as `#profile/7`, so bookmarks, reload and browser back work without a new framework.
- Public user responses never include email or password hashes. New users have a UTC
  `joined_at`; old accounts show “Joined before signup dates were recorded”.
- Search matches literal **substrings**, case-insensitively for ASCII (SQLite's
  built-in case folding is not full Unicode case folding). `%`, `_`, and SQL-looking
  text are treated as text, not wildcard patterns or SQL. `q` is trimmed, nonblank,
  and at most 100 characters; all page limits are 1–100, default 20.
- Search returns `{users, posts, next_user_before, next_post_before}`. Each cursor is
  an exclusive ID boundary for its own result type; `null` means that list is exhausted.
  Fetch more users with `user_before`, or more posts with `post_before`, consuming
  only that list from the response. The UI has independent load-more buttons so a
  short users list cannot truncate the posts list (or vice versa).
- Post/user lists are sorted by descending ID for deterministic keyset pagination,
  not offsets that shift when new rows arrive. Existing insertion-order feed semantics
  remain unchanged. Relationship lists are ordered by user ID, not by follow date.

### Existing SQLite databases

Restart the backend normally: `backend/migrations.py` runs an idempotent, additive
startup upgrade **before accepting requests**. It adds the nullable `users.joined_at`
column, creates the follows table, and adds missing indexes even on existing tables.
It does not drop tables, rewrite posts, change passwords, or invent legacy signup dates.
No environment variables or dependencies changed; `.env.example` is unchanged.
Back up valuable database files before any schema upgrade, with the server stopped.
This is a small single-process SQLite upgrade path, not a general migration framework;
run one backend process during the upgrade. Tests exercise an actual stage-one schema,
preserve its data, and run the upgrade twice to verify repeatability.

### Index choices

| Index | Why |
| --- | --- |
| Follows primary key `(follower_id, followed_id)` | Prevents duplicates; indexed existence checks, following lists/counts and followed-user subquery |
| `ix_follows_followed_follower (followed_id, follower_id)` | Reverse lookup for followers, their counts and user-ID pagination, without scanning all relationships |
| `ix_posts_user_id_id (user_id, id)` | Profile posts and author-filtered cursor scans: equality on author then an ID range/order |
| `ix_posts_user_created_id (user_id, created_at, id)` | Author + chronological retrieval; ID breaks equal timestamp ties for chronological SQL queries |
| Existing `ix_posts_created_at` | Retains timestamp range/order access across all authors; no redundant second global timestamp index added |
| `ix_likes_post_id (post_id)` | Post like counts and cascading deletion; the existing likes PK starts with user_id, not post_id |
| Existing unique username/email indexes and primary keys | Account lookups and ID-ordered Latest pagination |

The current API deliberately keeps its **ID cursors**: its hot author-feed path uses
`(user_id, id)`, not the timestamp composite index. Timestamp indexes support direct
chronological/range database queries; they do not change API ordering. Existing indexes
are retained for compatibility. SQLite can scan these B-tree indexes backwards for
descending order; separate descending duplicates are unnecessary. Substring search
with a leading wildcard **does scan text**: an ordinary text B-tree cannot accelerate
arbitrary substring matches, so no misleading content index was added. For a much
larger dataset use FTS with a deliberately chosen tokenizer/search contract.

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
node --check script.js  # optional JS syntax check if Node is installed
```

Optional real Chromium browser regression (starts/stops its own test servers on
15500 and 18000, uses a temporary database, leaves your development data untouched):

```bash
python -m pip install -r backend/requirements-browser.txt
python -m playwright install --with-deps chromium
python scripts/browser_smoke.py
```

The browser check covers signup, posting, XSS-safe text, likes, session restoration,
mobile overflow, delete/cancel, logout, wrong-password feedback, login, search pagination,
profiles, follow/unfollow, Following pagination, follower lists, back and profile reload.
API tests additionally cover self/duplicate/missing-target follows, independent search
cursors, literal wildcard handling, profile privacy, constraints, and legacy upgrades.

Tests use isolated in-memory SQLite databases and a random test signing key,
not your `.env` secret or persisted development database. `pytest.ini` deliberately
limits discovery to `backend/tests/`: the pre-existing root `test.py` is an unrelated,
unfinished calculator scratch file and has been left untouched. The old empty Pipfile
and lockfile are also untouched; the requirements files are the supported install path.

### Manual acceptance checklist

1. Create an account; auth disappears and the empty feed/composer appears.
2. Post a thought. It appears immediately with your username and “just now”.
3. Like, unlike, refresh, and reload the page: counts, posts and login persist.
4. Log out, try a wrong password, then log in correctly. Errors appear inline.
5. Try duplicate usernames/emails and invalid form values; expect useful errors.
6. Create a second account; it can like the first user's post but cannot delete it.
7. Delete your own post; cancel once, then confirm. It disappears after confirmation.
8. Check at a narrow mobile width, navigate forms using Tab and switch account tabs
   with arrow keys. Stop the backend and use Refresh to see the connection error.
9. If a JWT expires, the next protected request returns you to login with an explanation.
10. Search for the second account, open its profile, follow it and verify follower counts.
11. Switch to Following: only that account's posts appear. Unfollow; they disappear.
12. Search a matching post phrase; try a literal `%` or `_`. Load older matches/posts
    and more people separately when enough results exist.
13. Open your profile via My profile; it must not offer a self-follow button. Click
    follower/following counts, test browser Back, reload a profile, and retry on mobile.

## Docker (backend only)

Generate `backend/.env` first, then from the project root:

```bash
docker build -t chirp-api ./backend
docker volume create chirp-data
docker run --rm --name chirp-api -p 127.0.0.1:8000:8000 \
  --env-file backend/.env -e DATABASE_URL=sqlite:////data/chirp.db \
  -v chirp-data:/data chirp-api
```

The container runs as a non-root user. The named volume preserves SQLite across
container restarts. Run the frontend static server separately as above.
Do not put the secret into an image or build argument.

## Code map & learning notes

```text
index.html / style.css / script.js  Interface, styling, API calls and UI state
backend/config.py                  Validated environment configuration
backend/database.py                Engine, request-scoped sessions, SQLite foreign keys
backend/models.py                  Users, posts, composite-key likes and follows; indexes
backend/migrations.py              Additive, repeatable stage-one SQLite upgrade
backend/schemas.py                 Request validation and safe response shapes
backend/auth.py                    bcrypt, JWT creation/verification, auth dependencies
backend/main.py                    Routes, CORS, startup table creation
backend/init_env.py                Safe local secret generation
backend/tests/                     Isolated API regression tests
scripts/serve_frontend.py           Local public-assets-only frontend server
scripts/browser_smoke.py            Optional real-browser integration check
```

Comments explain SQLite timezones, uniqueness/races, bcrypt byte limits, and safe
DOM rendering. Password hashes never leave the backend. User content goes through
`textContent`, not `innerHTML`. Logout clears the local token; browser tabs notice
session changes. Tokens expire after one hour and are not server-revoked on logout.

### Scope and deployment caveats

This is a complete local learning app, not a hardened public social network.
Before public deployment add HTTPS, reverse-proxy rate limits (especially login/signup),
email verification/reset, abuse moderation, monitoring, and a migration tool such as
Alembic. The included additive upgrade handles this stage only; `create_all` by
itself does not migrate existing schemas.
SQLite is suitable for this small app; avoid many concurrent writers or multiple
backend replicas against the same SQLite file. Likes are toggles, so a client must
not automatically retry a timed-out toggle without reading the current state.
JWTs are stored in localStorage as requested: any future XSS could steal them;
an HttpOnly-cookie design would be a separate production security improvement.
Use a restrictive CSP on the deployed frontend and keep dependencies security-patched.
No seeded fake users/posts, email service, password reset, uploads, or refresh tokens
are included.
