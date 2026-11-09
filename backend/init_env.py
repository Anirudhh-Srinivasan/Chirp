"""Run with python -m backend.init_env. Never overwrites existing configuration."""
import os
from pathlib import Path
import secrets


def main():
    path = Path(__file__).resolve().parent / '.env'
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print('backend/.env already exists; left unchanged.')
        return
    with os.fdopen(descriptor, 'w') as file:
        file.write(f'SECRET_KEY={secrets.token_urlsafe(48)}\n'
                   'ACCESS_TOKEN_EXPIRE_MINUTES=60\n'
                   'CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500\n')
    print('Created private backend/.env with a random secret.')


if __name__ == '__main__':
    main()
