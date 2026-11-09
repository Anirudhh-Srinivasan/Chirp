from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, connect_args={'check_same_thread': False})


@event.listens_for(engine, 'connect')
def enable_foreign_keys(connection, _):
    # SQLite does not enforce cascading foreign keys unless explicitly enabled.
    connection.execute('PRAGMA foreign_keys=ON')


SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    with SessionLocal() as db:
        yield db
