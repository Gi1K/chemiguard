import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chemiguard.app import app
from chemiguard.store import Store


class SiteRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        with patch('chemiguard.store.DATA', Path(self.folder.name)):
            self.store = Store()
        for product_id in ('P11', 'P12', 'P04'):
            self.store.put('reference', {'product_id': product_id, 'reference_kind': 'product_photo'})
        self.patch = patch('chemiguard.app.store', self.store)
        self.patch.start()
        self.client = TestClient(app)
        self.payload = {'purpose': 'acid', 'protection_type': 'Type 3', 'color': 'white', 'product_id': 'P11'}

    def tearDown(self):
        self.client.close()
        self.patch.stop()
        self.store.db.close()
        self.folder.cleanup()

    def test_revision_replaces_slot_without_deleting_history(self):
        first = self.client.post('/api/site-products', json=self.payload)
        self.assertEqual(first.status_code, 200)
        second = self.client.post('/api/site-products', json=self.payload | {'enabled': False})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['supersedes'], first.json()['id'])
        rows = self.client.get('/api/site-products').json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['revision'], 2)
        self.assertFalse(rows[0]['enabled'])
        self.assertEqual(len(self.store.list('site_product')), 2)
        self.assertEqual(rows[0]['chemical_suitability'], 'NOT_ASSESSED')

    def test_unregistered_or_conflicting_product_cannot_be_assigned(self):
        for product_id in ('MISSING', 'P12'):
            response = self.client.post('/api/site-products', json=self.payload | {'product_id': product_id})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.store.list('site_product'), [])

    def test_color_slots_coexist_and_preserve_revisions_without_purpose_claims(self):
        white = {'registration_mode': 'color', 'color': 'white', 'product_id': 'P11'}
        first = self.client.post('/api/site-products', json=white)
        gray = self.client.post('/api/site-products', json=white | {'color': 'gray', 'product_id': 'P04'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(gray.status_code, 200)
        rows = self.client.get('/api/site-products').json()
        self.assertEqual({row['product_id'] for row in rows}, {'P11', 'P04'})
        self.assertTrue(all(row['purpose'] is None and row['protection_type'] is None for row in rows))
        updated = self.client.post('/api/site-products', json=white | {'enabled': False}).json()
        self.assertEqual(updated['supersedes'], first.json()['id'])
        self.assertEqual(updated['revision'], 2)
        rows = self.client.get('/api/site-products').json()
        self.assertEqual(len(rows), 2)
        self.assertTrue(next(row for row in rows if row['color'] == 'gray')['enabled'])
        self.assertEqual(len(self.store.list('site_product')), 3)

    def test_registration_modes_reject_missing_or_unwanted_purpose(self):
        color = {'registration_mode': 'color', 'color': 'white', 'product_id': 'P11'}
        for payload in (color | {'purpose': 'acid'}, color | {'registration_mode': 'purpose_type'}):
            self.assertEqual(self.client.post('/api/site-products', json=payload).status_code, 422)


if __name__ == '__main__':
    unittest.main()
