"""Local frontend server: expose only public assets, never .env or the database."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class PublicFilesHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = urlsplit(self.path).path
        if path not in {'/', '/index.html', '/style.css', '/script.js'}:
            self.send_error(404, 'Not found')
            return None
        if path == '/':
            self.path = '/index.html'
        return super().send_head()


def main():
    handler = partial(PublicFilesHandler, directory=str(ROOT))
    with ThreadingHTTPServer(('127.0.0.1', 5500), handler) as server:
        print('Chirp frontend: http://localhost:5500 (Ctrl+C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
