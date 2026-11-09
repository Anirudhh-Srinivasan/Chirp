from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Signup(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)

    @field_validator('username', 'email')
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.lower()

    @field_validator('password')
    @classmethod
    def bcrypt_byte_limit(cls, value: str) -> str:
        # bcrypt limits bytes, not Unicode characters. Never silently truncate.
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=280)

    @field_validator('content')
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Write something before posting')
        return value.strip()


class PostOut(BaseModel):
    id: int
    user_id: int
    username: str
    content: str
    created_at: datetime
    like_count: int
    liked_by_me: bool


class PublicUser(BaseModel):
    id: int
    username: str
    joined_at: datetime | None


class Profile(PublicUser):
    follower_count: int
    following_count: int
    followed_by_me: bool


class SearchResults(BaseModel):
    users: list[PublicUser]
    posts: list[PostOut]
    next_user_before: int | None
    next_post_before: int | None
