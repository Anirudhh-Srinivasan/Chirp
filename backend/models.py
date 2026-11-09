from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    # Legacy accounts have no recorded signup date; do not invent one on upgrade.
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )


class Post(Base):
    __tablename__ = 'posts'
    __table_args__ = (
        Index('ix_posts_user_id_id', 'user_id', 'id'),
        Index('ix_posts_user_created_id', 'user_id', 'created_at', 'id'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    author: Mapped[User] = relationship()


class Like(Base):
    __tablename__ = 'likes'
    __table_args__ = (Index('ix_likes_post_id', 'post_id'),)

    # A composite primary key prevents duplicate likes even across requests.
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True
    )


class Follow(Base):
    __tablename__ = 'follows'
    __table_args__ = (
        CheckConstraint('follower_id != followed_id', name='ck_no_self_follow'),
        # The PK covers following lookups; the reverse index covers followers.
        Index('ix_follows_followed_follower', 'followed_id', 'follower_id'),
    )

    follower_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    followed_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
