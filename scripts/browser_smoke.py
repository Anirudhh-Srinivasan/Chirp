"""Optional real-browser regression: isolated servers/database, no developer data."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from urllib.request import urlopen

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class FrontendHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            content = (ROOT / 'index.html').read_text().replace('http://localhost:8000', 'http://127.0.0.1:18000').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        elif self.path in ('/script.js', '/style.css'):
            super().do_GET()
        else:
            self.send_error(404)

    def log_message(self, *_):
        pass


def main():
    with TemporaryDirectory(prefix='chirp-smoke-') as temp:
        env = {**os.environ, 'SECRET_KEY': secrets.token_urlsafe(48),
               'DATABASE_URL': f'sqlite:///{temp}/test.db',
               'CORS_ORIGINS': 'http://127.0.0.1:15500'}
        server = ThreadingHTTPServer(('127.0.0.1', 15500), partial(FrontendHandler, directory=str(ROOT)))
        Thread(target=server.serve_forever, daemon=True).start()
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app', '--port', '18000'],
                                   cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError('Test backend did not start. Check port 18000 is free.')
                try:
                    with urlopen('http://127.0.0.1:18000/health') as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Timed out waiting for the test backend')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto('http://127.0.0.1:15500')
                page.locator('#signupTab').click()
                page.locator('#newUsername').fill('browser_user')
                page.locator('#email').fill('browser@example.com')
                page.locator('#newPassword').fill('password123')
                page.locator('#signupForm button[type=submit]').click()
                expect(page.locator('#feedSection')).to_be_visible()
                expect(page.locator('#feedStatus')).to_contain_text('No chirps yet')
                content = 'My first chirp! <script>this is text, not code</script>'
                page.locator('#postContent').fill(content)
                page.locator('#postButton').click()
                expect(page.locator('.post-content')).to_have_text(content)
                expect(page.locator('.post time')).to_have_text('just now')
                page.locator('.like-button').click()
                expect(page.locator('.like-button')).to_have_attribute('aria-pressed', 'true')
                page.reload()
                expect(page.locator('.post-content')).to_have_text(content)
                expect(page.locator('.like-button')).to_have_attribute('aria-pressed', 'true')
                page.locator('.like-button').click()
                expect(page.locator('.like-button')).to_have_attribute('aria-pressed', 'false')
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
                page.locator('.delete-button').click()
                page.locator('#deleteDialog button[value=cancel]').click()
                expect(page.locator('.post')).to_have_count(1)
                page.locator('.delete-button').click()
                page.locator('#deleteDialog button[value=delete]').click()
                expect(page.locator('.post')).to_have_count(0)
                page.locator('#logoutButton').click()
                expect(page.locator('#authSection')).to_be_visible()
                assert page.evaluate('localStorage.getItem("chirp_token")') is None
                page.locator('#username').fill('browser_user')
                page.locator('#password').fill('wrong-password')
                page.locator('#loginForm button[type=submit]').click()
                expect(page.locator('#loginError')).to_contain_text('Incorrect username or password')
                page.locator('#password').fill('password123')
                page.locator('#loginForm button[type=submit]').click()
                expect(page.locator('#feedSection')).to_be_visible()
                expect(page.locator('#feedStatus')).to_contain_text('No chirps yet')
                # Seed a second real account through the API, then interact entirely via UI.
                with httpx.Client(base_url='http://127.0.0.1:18000') as api:
                    other = api.post('/signup', json={'username': 'social_friend', 'email': 'friend@example.com', 'password': 'password123'}).json()
                    friend_token = api.post('/login', json={'username': 'social_friend', 'password': 'password123'}).json()['access_token']
                    friend_headers = {'Authorization': f'Bearer {friend_token}'}
                    for number in range(21):
                        assert api.post('/posts', headers=friend_headers, json={'content': f'Social discovery {number}'}).status_code == 201
                page.locator('#followingTab').click()
                expect(page.locator('#feedStatus')).to_contain_text('Follow someone')
                page.locator('#searchInput').fill('social')
                page.locator('#searchForm button').click()
                expect(page.locator('.person-card')).to_contain_text('social_friend')
                expect(page.locator('.post')).to_have_count(20)
                page.locator('#loadMoreButton').click()
                expect(page.locator('.post')).to_have_count(21)
                page.locator('.person-card').click()
                expect(page.locator('#profileCard')).to_contain_text('Joined')
                expect(page.locator('#profileCard')).to_contain_text('0 followers')
                expect(page.locator('.post')).to_have_count(20)
                page.locator('#followButton').click()
                expect(page.locator('#followButton')).to_have_text('Unfollow')
                expect(page.locator('#profileCard')).to_contain_text('1 followers')
                page.locator('#followingTab').click()
                expect(page.locator('.post')).to_have_count(20)
                page.locator('#loadMoreButton').click()
                expect(page.locator('.post')).to_have_count(21)
                page.locator('.post-author').first.click()
                expect(page.locator('#followButton')).to_have_text('Unfollow')
                page.locator('.profile-counts a').first.click()
                expect(page.locator('.person-card')).to_contain_text('browser_user')
                page.go_back()
                expect(page.locator('#followButton')).to_be_visible()
                page.locator('#followButton').click()
                expect(page.locator('#followButton')).to_have_text('Follow')
                page.locator('#followingTab').click()
                expect(page.locator('.post')).to_have_count(0)
                expect(page.locator('#feedStatus')).to_contain_text('Follow someone')
                page.locator('#myProfileLink').click()
                expect(page.locator('#profileCard')).to_contain_text('@browser_user')
                expect(page.locator('#followButton')).to_have_count(0)
                page.reload()
                expect(page.locator('#profileCard')).to_contain_text('@browser_user')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Social UI mobile horizontal overflow'
                assert not errors, errors
                browser.close()
            print('Browser smoke passed: original auth/posts/likes flow plus search pagination, profiles, follow/unfollow, Following pagination, follower lists, back navigation, profile reload and mobile. No JS runtime errors.')
        finally:
            process.terminate()
            process.wait(timeout=10)
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
