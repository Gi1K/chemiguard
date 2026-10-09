import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from chemiguard.app import app


class TrackingResponseTests(unittest.TestCase):
    def test_compression_preserves_snapshot_and_uncompressed_clients(self):
        payload = {'generation': 2, 'overlay_frames': [
            {'source_time_s': i / 5, 'tracks': [{'track_token': 'one', 'reason': 'x' * 2048}]}
            for i in range(20)]}
        with patch('chemiguard.app.monitor.active', Mock(snapshot=Mock(return_value=payload))):
            client = TestClient(app)
            compressed = client.get('/api/runs/active', headers={'Accept-Encoding': 'gzip'})
            plain = client.get('/api/runs/active', headers={'Accept-Encoding': 'identity'})
        self.assertEqual(compressed.json(), payload)
        self.assertEqual(plain.json(), payload)
        self.assertEqual(compressed.headers['Content-Encoding'], 'gzip')
        self.assertIn('Accept-Encoding', compressed.headers['Vary'])
        self.assertNotIn('Content-Encoding', plain.headers)
        self.assertLess(int(compressed.headers['Content-Length']), len(plain.content) / 4)

    def test_empty_run_and_other_routes_keep_existing_behavior(self):
        with patch('chemiguard.app.monitor.active', None), \
             patch('chemiguard.app.sources.list', return_value=[{'name': 'x' * 2048}]):
            client = TestClient(app)
            self.assertIsNone(client.get('/api/runs/active').json())
            response = client.get('/api/sources', headers={'Accept-Encoding': 'gzip'})
        self.assertNotIn('Content-Encoding', response.headers)
        self.assertEqual(response.json(), [{'name': 'x' * 2048}])


if __name__ == '__main__':
    unittest.main()
