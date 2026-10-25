"""Stage 2 route, presentation contract, and backend integration checks."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import app
from backend import FEATURES
from frontend import FEATURE_INFO, VALIDATION_RESULTS


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def html(self, route):
        response = self.client.get(route, headers={'Accept': 'text/html'})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_each_page_has_correct_title_and_active_navigation(self):
        for route, title in [('explore', 'Explore the Kepler Catalog'), ('predict', 'Predict Exoplanet Candidate'),
                             ('model', 'Our Machine Learning Model'), ('about', 'About the Project')]:
            with self.subTest(route=route):
                html = self.html('/' + route)
                self.assertIn(f'<title>{title} — Exoplanet Hunter</title>', html)
                active = [attrs['href'] for tag, attrs in Markup(html).elements
                          if tag == 'a' and attrs.get('aria-current') == 'page']
                self.assertEqual(active, ['/' + route])

    def test_all_page_assets_exist_and_interior_styles_are_isolated(self):
        for route in ('/', '/explore', '/predict', '/model', '/about'):
            with self.subTest(route=route):
                html = self.html(route)
                self.assertEqual('css/interior.css' in html, route != '/')
                self.assertEqual('js/home.js' in html, route == '/')
                for tag, attrs in Markup(html).elements:
                    url = attrs.get('src', attrs.get('href', ''))
                    if url.startswith('/static/'):
                        response = self.client.get(url)
                        self.assertEqual(response.status_code, 200, url)
                        response.close()

    def test_homepage_calls_to_action_open_finished_pages(self):
        html = self.html('/')
        self.assertNotIn('data-preview=', html)
        links = [attrs['href'] for tag, attrs in Markup(html).elements if tag == 'a']
        for route in ('/explore', '/predict', '/model', '/about'):
            self.assertIn(route, links)

    def test_prediction_inputs_match_saved_feature_order_and_accessible_help(self):
        html = self.html('/predict')
        fields = [attrs for tag, attrs in Markup(html).elements if tag == 'input' and attrs.get('name') in FEATURES]
        self.assertEqual([field['name'] for field in fields], FEATURES)
        self.assertEqual([item[0] for item in FEATURE_INFO], FEATURES)
        for field in fields:
            self.assertEqual(field['type'], 'number')
            self.assertIn('help-' + field['name'], field['aria-describedby'])
            self.assertIn('error-' + field['name'], field['aria-describedby'])

    def test_unique_markup_ids_and_resolvable_labels(self):
        for route in ('/explore', '/predict', '/model', '/about'):
            with self.subTest(route=route):
                nodes = Markup(self.html(route)).elements
                ids = [attrs['id'] for _, attrs in nodes if 'id' in attrs]
                self.assertEqual(len(ids), len(set(ids)))
                for tag, attrs in nodes:
                    if tag == 'label' and 'for' in attrs:
                        self.assertIn(attrs['for'], ids)

    def test_model_report_separates_validation_and_test_results(self):
        html = self.html('/model')
        self.assertIn('RECORDED VALIDATION RESULTS', html)
        self.assertIn('HISTORICAL FINAL TEST RESULTS', html)
        self.assertIn('test set was inspected during development', html)
        self.assertIn('1,902', html)
        self.assertEqual([r['accuracy'] for r in VALIDATION_RESULTS], [.7600, .8358, .8178])
        self.assertEqual([r['f1'] for r in VALIDATION_RESULTS], [.7720, .8262, .8121])
        self.assertEqual([r['auc'] for r in VALIDATION_RESULTS], [.8218, .9231, .9005])
        self.assertFalse(self.client.get('/api/model/info').json['historical_evaluation']['calculated_by_api'])

    def test_pages_render_when_resources_are_unavailable(self):
        with patch.dict(app.extensions, {'catalog': None, 'predictor': None}):
            for route in ('/explore', '/predict', '/model', '/about'):
                self.html(route)
            self.assertEqual(self.client.get('/api/objects').status_code, 503)
            self.assertEqual(self.client.post('/api/predict', json={}).status_code, 503)

    def test_selected_observation_payload_matches_existing_prediction_route(self):
        objects = self.client.get('/api/objects?per_page=2').json['objects']
        for obj in objects:
            identifier = obj['object_id']
            self.html('/predict?object_id=' + identifier)
            detail = self.client.get('/api/objects/' + identifier).json['object']
            manual = self.client.post('/api/predict', json=detail['features']).json
            automatic = self.client.get('/api/objects/' + identifier + '/predict').json['model_prediction']
            self.assertEqual(manual['prediction'], automatic['prediction'])
            self.assertEqual(manual['planet_like_score'], automatic['planet_like_score'])

    def test_approved_homepage_styles_and_original_image_unchanged(self):
        # The approved styles are frozen; new page styles must stay in interior.css.
        expected = {
            'static/css/site.css': 'f71eb3bf47a1a9084a3952ba0ca548997ef0acf2aa7d23bcd87fe980d915e7b7',
            'static/images/starfield.png': '45222a2b017f5138ced31e4cec9260378a9295c03d40f3266db8d4a063aaeaea',
            'static/js/home.js': '5ab97f0ad1b728b6566602d7ebb179217b153f3b95fffc9a29d0874047c41c11',
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
