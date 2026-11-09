from contextlib import asynccontextmanager
from datetime import timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .config import settings
from .database import engine, get_db
from .migrations import upgrade


@asynccontextmanager
async def lifespan(app: FastAPI):
    upgrade(engine)
    yield


app = FastAPI(title='Chirp API', version='1.0.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(',') if origin.strip()],
    allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Authorization', 'Content-Type'],
)


@app.get('/health')
def healthcheck():
    return {'status': 'ok'}


@app.post('/signup', response_model=schemas.UserOut, status_code=201)
def signup(data: schemas.Signup, db: Session = Depends(get_db)):
    for field, value in [('username', data.username), ('email', str(data.email))]:
        if db.scalar(select(models.User).where(getattr(models.User, field) == value)):
            raise HTTPException(409, f'That {field} is already taken.')
    user = models.User(username=data.username, email=str(data.email),
                       password_hash=auth.hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Database uniqueness remains authoritative for concurrent signups.
        db.rollback()
        raise HTTPException(409, 'That username or email is already taken.')
    db.refresh(user)
    return user


@app.post('/login', response_model=schemas.Token)
def login(data: schemas.Login, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == data.username.strip().lower()))
    hashed = user.password_hash if user else auth.DUMMY_HASH.decode()
    valid = auth.verify_password(data.password, hashed)
    if not user or not valid:
        raise HTTPException(401, 'Incorrect username or password.',
                            headers={'WWW-Authenticate': 'Bearer'})
    return schemas.Token(access_token=auth.create_token(user.id))


@app.get('/me', response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user


def post_data(post: models.Post, db: Session, user: models.User | None):
    # SQLite returns naive UTC datetimes; label them explicitly for browsers.
    created = post.created_at.replace(tzinfo=timezone.utc)
    count = db.scalar(select(func.count()).select_from(models.Like).where(models.Like.post_id == post.id))
    return schemas.PostOut(id=post.id, user_id=post.user_id, username=post.author.username,
                           content=post.content, created_at=created, like_count=count,
                           liked_by_me=bool(user and db.get(models.Like, (user.id, post.id))))


@app.get('/posts', response_model=list[schemas.PostOut])
def posts(limit: int = Query(20, ge=1, le=100), before: int | None = Query(None, ge=1),
          feed: Literal['latest', 'following'] = 'latest', user_id: int | None = Query(None, ge=1),
          db: Session = Depends(get_db), user: models.User | None = Depends(auth.optional_user)):
    statement = select(models.Post).order_by(models.Post.id.desc()).limit(limit)
    if feed == 'following':
        if user is None:
            raise auth.unauthorized()
        statement = statement.where(models.Post.user_id.in_(
            select(models.Follow.followed_id).where(models.Follow.follower_id == user.id)))
    if user_id is not None:
        require_user(user_id, db)
        statement = statement.where(models.Post.user_id == user_id)
    if before is not None:
        statement = statement.where(models.Post.id < before)
    return [post_data(post, db, user) for post in db.scalars(statement)]


@app.post('/posts', response_model=schemas.PostOut, status_code=201)
def create_post(data: schemas.PostCreate, db: Session = Depends(get_db),
                user: models.User = Depends(auth.get_current_user)):
    post = models.Post(content=data.content, user_id=user.id)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post_data(post, db, user)


@app.post('/posts/{post_id}/like', response_model=schemas.PostOut)
def toggle_like(post_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(auth.get_current_user)):
    post = db.get(models.Post, post_id)
    if not post:
        raise HTTPException(404, 'Post not found.')
    like = db.get(models.Like, (user.id, post_id))
    if like:
        db.delete(like)
    else:
        db.add(models.Like(user_id=user.id, post_id=post_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This post changed. Refresh and try again.')
    return post_data(post, db, user)


@app.delete('/posts/{post_id}', status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(auth.get_current_user)):
    post = db.get(models.Post, post_id)
    if not post:
        raise HTTPException(404, 'Post not found.')
    if post.user_id != user.id:
        raise HTTPException(403, 'You can only delete your own posts.')
    db.delete(post)
    db.commit()
    return Response(status_code=204)


def require_user(user_id: int, db: Session) -> models.User:
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(404, 'User not found.')
    return target


def public_user(user: models.User) -> schemas.PublicUser:
    return schemas.PublicUser(id=user.id, username=user.username,
                              joined_at=user.joined_at.replace(tzinfo=timezone.utc) if user.joined_at else None)


def profile_data(target: models.User, db: Session, viewer: models.User | None):
    return schemas.Profile(
        **public_user(target).model_dump(),
        follower_count=db.scalar(select(func.count()).select_from(models.Follow).where(models.Follow.followed_id == target.id)),
        following_count=db.scalar(select(func.count()).select_from(models.Follow).where(models.Follow.follower_id == target.id)),
        followed_by_me=bool(viewer and db.get(models.Follow, (viewer.id, target.id))),
    )


@app.get('/users/{user_id}', response_model=schemas.Profile)
def profile(user_id: int, db: Session = Depends(get_db),
            viewer: models.User | None = Depends(auth.optional_user)):
    return profile_data(require_user(user_id, db), db, viewer)


@app.post('/users/{user_id}/follow', response_model=schemas.Profile)
def follow(user_id: int, db: Session = Depends(get_db),
           viewer: models.User = Depends(auth.get_current_user)):
    target = require_user(user_id, db)
    if user_id == viewer.id:
        raise HTTPException(400, 'You cannot follow yourself.')
    # Explicit set/unset operations are idempotent, unlike a retry-unsafe toggle.
    if not db.get(models.Follow, (viewer.id, user_id)):
        db.add(models.Follow(follower_id=viewer.id, followed_id=user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if not db.get(models.Follow, (viewer.id, user_id)):
                raise HTTPException(409, 'User changed. Refresh and try again.')
    return profile_data(target, db, viewer)


@app.delete('/users/{user_id}/follow', response_model=schemas.Profile)
def unfollow(user_id: int, db: Session = Depends(get_db),
             viewer: models.User = Depends(auth.get_current_user)):
    target = require_user(user_id, db)
    if user_id == viewer.id:
        raise HTTPException(400, 'You cannot follow yourself.')
    relation = db.get(models.Follow, (viewer.id, user_id))
    if relation:
        db.delete(relation)
        db.commit()
    return profile_data(target, db, viewer)


@app.get('/users/{user_id}/{direction}', response_model=list[schemas.PublicUser])
def connections(user_id: int, direction: Literal['followers', 'following'],
                limit: int = Query(20, ge=1, le=100), before: int | None = Query(None, ge=1),
                db: Session = Depends(get_db)):
    require_user(user_id, db)
    follows = models.Follow
    match = follows.follower_id if direction == 'followers' else follows.followed_id
    owner = follows.followed_id if direction == 'followers' else follows.follower_id
    statement = select(models.User).join(follows, models.User.id == match).where(owner == user_id)
    if before is not None:
        statement = statement.where(models.User.id < before)
    return [public_user(user) for user in db.scalars(statement.order_by(models.User.id.desc()).limit(limit))]


@app.get('/search', response_model=schemas.SearchResults)
def search(q: str = Query(min_length=1, max_length=100), limit: int = Query(20, ge=1, le=100),
           user_before: int | None = Query(None, ge=1), post_before: int | None = Query(None, ge=1),
           db: Session = Depends(get_db), viewer: models.User | None = Depends(auth.optional_user)):
    query = q.strip()
    if not query:
        raise HTTPException(422, 'Search cannot be blank.')
    # autoescape treats % and _ literally, rather than letting search become a wildcard query.
    users = select(models.User).where(models.User.username.icontains(query, autoescape=True))
    posts = select(models.Post).where(models.Post.content.icontains(query, autoescape=True))
    if user_before is not None:
        users = users.where(models.User.id < user_before)
    if post_before is not None:
        posts = posts.where(models.Post.id < post_before)
    user_rows = list(db.scalars(users.order_by(models.User.id.desc()).limit(limit + 1)))
    post_rows = list(db.scalars(posts.order_by(models.Post.id.desc()).limit(limit + 1)))
    # Independent cursors prevent one result type from skipping the other's matches.
    return schemas.SearchResults(
        users=[public_user(user) for user in user_rows[:limit]],
        posts=[post_data(post, db, viewer) for post in post_rows[:limit]],
        next_user_before=user_rows[limit - 1].id if len(user_rows) > limit else None,
        next_post_before=post_rows[limit - 1].id if len(post_rows) > limit else None,
    )
