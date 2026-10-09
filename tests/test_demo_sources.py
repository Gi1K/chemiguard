from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chemiguard.sources import Sources


class DemoSourcesTests(unittest.TestCase):
    def test_three_demo_selection_preserves_archived_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets, ppe, demo = root/'assets', root/'ppe/demo/video', root/'demo'
            assets.mkdir()
            ppe.mkdir(parents=True)
            demo.mkdir()
            (assets/'00_최신편집_데모').mkdir()
            selected = [assets/'00_최신편집_데모/receiver_valve_centered.mp4',
                        ppe/'V08_wide_205_222_5s.mp4', demo/'Tychem4000S_착용_동작_시연.mp4']
            archived = assets/'other.mp4'
            for path in [*selected, archived, ppe/'V08_donning_76_90s.mp4']:
                path.touch()
            with patch('chemiguard.sources.ASSETS', assets), patch('chemiguard.sources.PPE_MEDIA', ppe), \
                 patch('chemiguard.sources.DEMO_MEDIA', demo), patch('chemiguard.sources.store.list', return_value=[]):
                sources = Sources()
                rows = sources.list()
                self.assertEqual([sources.path(row['id']) for row in rows], selected)
                self.assertEqual([row['demo_order'] for row in rows], [0, 1, 2])
                self.assertEqual(rows[2]['case'], '착용 동작')
                archive_rows = sources.list(include_archive=True)
                self.assertEqual(len(archive_rows), 5)
                archive_id = next(row['id'] for row in archive_rows if row['name'] == 'other')
                self.assertEqual(sources.path(archive_id), archived)
                selected[2].unlink()
                self.assertEqual(len(sources.list()), 2)
                self.assertEqual(sources.path(archive_id), archived)


if __name__ == '__main__':
    unittest.main()
