from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread

import httpx

from scripts.serve_frontend import PublicFilesHandler, ROOT


def test_static_server_only_exposes_public_assets():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(PublicFilesHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with httpx.Client(base_url=base) as client:
            for path in ['/', '/index.html', '/style.css', '/script.js']:
                assert client.get(path).status_code == 200
            for path in ['/backend/.env', '/backend/chirp.db', '/backend/', '/README.md', '/%2e%2e/.env']:
                assert client.get(path).status_code == 404
                assert client.head(path).status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
