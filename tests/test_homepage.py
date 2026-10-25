"""Homepage integration checks, separate from the unchanged backend suite."""

from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = set()
        self.anchors = []
        self.assets = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.anchors.append(attrs['href'][1:])
        if tag in ('script', 'link'):
            url = attrs.get('src') or attrs.get('href', '')
            if url.startswith('/static/'):
                self.assets.add(url)


class HomepageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_browser_receives_homepage_and_vary_header(self):
        response = self.client.get('/', headers={'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/html')
        self.assertIn('Accept', response.vary)
        html = response.get_data(as_text=True)
        for section in ('hero-title', 'beyond-title', 'archive-title', 'method-title', 'invitation-title'):
            self.assertIn(f'id="{section}"', html)

    def test_legacy_json_contract_and_explicit_api_home(self):
        for accept in ('', '*/*', 'application/json', 'application/json,text/html;q=0.5'):
            with self.subTest(accept=accept):
                response = self.client.get('/', headers={'Accept': accept})
                self.assertEqual(response.mimetype, 'application/json')
                self.assertEqual(response.json['project'], 'Exoplanet Hunter')
        self.assertEqual(self.client.get('/api').json, self.client.get('/').json)

    def test_all_homepage_anchors_have_real_targets(self):
        page = PageParser(self.client.get('/', headers={'Accept': 'text/html'}).get_data(as_text=True))
        self.assertTrue(page.anchors)
        self.assertTrue(set(page.anchors).issubset(page.ids), set(page.anchors) - page.ids)

    def test_local_assets_are_served(self):
        page = PageParser(self.client.get('/', headers={'Accept': 'text/html'}).get_data(as_text=True))
        self.assertGreaterEqual(len(page.assets), 4)
        for url in page.assets:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 20)
                response.close()

    def test_homepage_does_not_embed_mock_counts(self):
        html = self.client.get('/', headers={'Accept': 'text/html'}).get_data(as_text=True)
        self.assertIn('data-stats-url="/api/stats"', html)
        self.assertIn('data-stat="total_observations">—', html)
        self.assertEqual(self.client.get('/api/stats').status_code, 200)

    def test_approved_stage_two_pages_are_available(self):
        for route in ('/explore', '/predict', '/model', '/about'):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'text/html')


if __name__ == '__main__':
    unittest.main()
