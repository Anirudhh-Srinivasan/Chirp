"""Small additive SQLite upgrade, safe to rerun for existing stage-one databases."""
from sqlalchemy import inspect

from .database import Base


def upgrade(engine):
    # Run once during startup before accepting requests, not per request.
    with engine.begin() as connection:
        inspector = inspect(connection)
        if 'users' in inspector.get_table_names():
            columns = {column['name'] for column in inspector.get_columns('users')}
            if 'joined_at' not in columns:
                connection.exec_driver_sql('ALTER TABLE users ADD COLUMN joined_at DATETIME')
        Base.metadata.create_all(connection)
        # create_all skips indexes on tables that already exist; add them explicitly.
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(connection, checkfirst=True)
