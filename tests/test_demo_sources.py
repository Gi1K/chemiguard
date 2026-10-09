from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from chemiguard.sources import Sources


class DemoSourcesTests(unittest.TestCase):
    def test_high_frame_rate_gets_local_compatible_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'input.mp4'
            path.write_bytes(b'original')
            stream = {'codec_name': 'h264', 'pix_fmt': 'yuv420p', 'level': 42,
                      'avg_frame_rate': '50/1', 'width': 1920, 'height': 1080}
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                if command[0] == 'ffprobe':
                    return subprocess.CompletedProcess(command, 0, json.dumps({'streams': [stream]}))
                Path(command[-1]).write_bytes(b'compatible')
                return subprocess.CompletedProcess(command, 0)

            with patch.object(Sources, 'refresh'), patch('chemiguard.sources.DATA', Path(folder)), \
                 patch('chemiguard.sources.subprocess.run', side_effect=run):
                sources = Sources()
                output = sources._playback(str(path), 1, 8)
                self.assertNotEqual(output, path)
                self.assertEqual(path.read_bytes(), b'original')
                self.assertEqual(output.read_bytes(), b'compatible')
                self.assertIn('fps=30', commands[1][commands[1].index('-vf')+1])
                self.assertEqual(sources._playback(str(path), 1, 8), output)
                self.assertEqual(len(commands), 2)

    def test_compatible_h264_keeps_original(self):
        stream = {'codec_name': 'h264', 'pix_fmt': 'yuv420p', 'level': 40,
                  'avg_frame_rate': '30000/1001', 'width': 1280, 'height': 720}
        with patch.object(Sources, 'refresh'), patch('chemiguard.sources.subprocess.run',
                return_value=subprocess.CompletedProcess([], 0, json.dumps({'streams': [stream]}))) as run:
            self.assertEqual(Sources()._playback('/video.mp4', 1, 8), Path('/video.mp4'))
            self.assertEqual(run.call_count, 1)

    def test_three_demo_selection_preserves_archived_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets, ppe, demo = root/'assets', root/'ppe/demo/video', root/'demo'
            assets.mkdir()
            ppe.mkdir(parents=True)
            demo.mkdir()
            (assets/'00_최신편집_데모').mkdir()
            selected = [ppe/'V08_wide_205_222_5s.mp4', demo/'Tychem4000S_착용_동작_시연.mp4',
                        assets/'00_최신편집_데모/receiver_valve_centered.mp4']
            archived = assets/'other.mp4'
            for path in [*selected, archived, ppe/'V08_donning_76_90s.mp4']:
                path.touch()
            with patch('chemiguard.sources.ASSETS', assets), patch('chemiguard.sources.PPE_MEDIA', ppe), \
                 patch('chemiguard.sources.DEMO_MEDIA', demo), patch('chemiguard.sources.store.list', return_value=[]):
                sources = Sources()
                rows = sources.list()
                self.assertEqual([sources.path(row['id']) for row in rows], selected)
                self.assertEqual([row['demo_order'] for row in rows], [0, 1, 2])
                self.assertEqual(rows[1]['case'], '착용 동작')
                archive_rows = sources.list(include_archive=True)
                self.assertEqual(len(archive_rows), 5)
                archive_id = next(row['id'] for row in archive_rows if row['name'] == 'other')
                self.assertEqual(sources.path(archive_id), archived)
                selected[1].unlink()
                self.assertEqual(len(sources.list()), 2)
                self.assertEqual(sources.path(archive_id), archived)


if __name__ == '__main__':
    unittest.main()
