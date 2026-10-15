"""Regression checks for native-video upgrades and preservation of existing media."""
import copy
import hashlib
import json
import pathlib
import subprocess
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

import app
import native_video


class NativeVideoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name).resolve()
        self.source = self.root / 'piece.mscz'
        self.write_score(0)
        self.old = self.root / 'old.mp4'
        self.old.write_bytes(b'original video')
        self.ident = hashlib.sha256(str(self.source).encode()).hexdigest()[:24]
        self.row = {'id': self.ident, 'path': str(self.source), 'filename': self.source.name,
                    'hash': app.metadata(self.source)[1], 'sourceHash': app.file_fingerprint(self.source),
                    'video': str(self.old), 'status': 'Ready', 'selected': False}
        state = {'folder': str(self.root), 'pieces': {self.ident: self.row}}
        for name, value in [('DATA', self.root), ('VIDEOS', self.root), ('STATE', state)]:
            mock = patch.object(app, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        app.STOP.clear()

    def write_score(self, volume):
        with zipfile.ZipFile(self.source, 'w') as archive:
            archive.writestr('piece.mscx', '<museScore><Score/></museScore>')
            archive.writestr('audiosettings.json', json.dumps({'volume': volume}))

    def export(self, executable, score, destination, work, log, stopped):
        self.assertNotEqual(score, self.source)
        self.assertEqual(score.read_bytes(), self.source.read_bytes())
        destination.write_bytes(b'new native video')

    def test_upgrade_does_not_reuse_legacy_media(self):
        self.assertTrue(app.needs_native_video(self.row))
        before = self.source.read_bytes()
        with patch.object(app, 'export_native', side_effect=self.export) as export, patch.object(app, 'validate_video'):
            app.render(copy.deepcopy(self.row))
        export.assert_called_once()
        self.assertEqual(self.old.read_bytes(), b'original video')
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(app.video_path(self.row).read_bytes(), b'new native video')
        self.assertFalse(app.needs_native_video(self.row))
        self.assertEqual(self.row['videoRenderer'], native_video.RENDERER)

    def test_current_native_video_is_reused(self):
        self.row.update(videoRenderer=native_video.RENDERER, videoSourceHash=self.row['sourceHash'])
        with patch.object(app, 'export_native') as export, patch.object(app, 'validate_video'):
            app.render(copy.deepcopy(self.row))
        export.assert_not_called()

    def test_failed_export_keeps_previous_video_and_cleans_partial(self):
        def fail(*args):
            args[2].write_bytes(b'incomplete')
            raise ValueError('export failed')
        with patch.object(app, 'export_native', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'export failed'):
                app.render(copy.deepcopy(self.row))
        self.assertEqual(app.video_path(self.row), self.old)
        self.assertEqual(self.old.read_bytes(), b'original video')
        self.assertFalse(list(self.root.glob('*.partial.mp4')))
        self.assertFalse(list(self.root.glob('native-*')))

    def test_invalid_video_is_not_published(self):
        with patch.object(app, 'export_native', side_effect=self.export), patch.object(app, 'validate_video', side_effect=ValueError('invalid media')):
            with self.assertRaisesRegex(ValueError, 'invalid media'):
                app.render(copy.deepcopy(self.row))
        self.assertEqual(app.video_path(self.row), self.old)
        self.assertFalse(app.generated_video_path(self.row).exists())

    def test_source_change_during_export_is_not_published(self):
        def change(*args):
            args[2].write_bytes(b'new native video')
            self.write_score(1)
        with patch.object(app, 'export_native', side_effect=change), patch.object(app, 'validate_video'):
            with self.assertRaisesRegex(ValueError, 'changed during rendering'):
                app.render(copy.deepcopy(self.row))
        self.assertEqual(app.video_path(self.row), self.old)
        self.assertFalse(app.generated_video_path(self.row).exists())

    def test_attached_video_is_reused(self):
        self.row['videoSource'] = 'attached'
        self.assertFalse(app.needs_native_video(self.row))
        with patch.object(app, 'export_native') as export, patch.object(app, 'validate_video'):
            app.render(copy.deepcopy(self.row))
        export.assert_not_called()

    def test_upload_records_protect_original_bytes(self):
        for field in ('youtube', 'session'):
            with self.subTest(field=field):
                row = dict(self.row, **{field: 'existing-record'})
                self.assertFalse(app.needs_native_video(row))
                with patch.object(app, 'export_native') as export:
                    with self.assertRaisesRegex(ValueError, 'upload record'):
                        app.render(row)
                export.assert_not_called()
                self.assertEqual(app.video_path(row).read_bytes(), b'original video')

    def test_refresh_detects_audio_changes_with_unchanged_notation(self):
        self.row.update(videoSource='generated', videoRenderer=native_video.RENDERER,
                        videoSourceHash=self.row['sourceHash'])
        notation_hash = self.row['hash']
        self.write_score(6)
        rows = app.scan(self.root)
        self.assertEqual(rows[0]['hash'], notation_hash)
        self.assertTrue(app.needs_native_video(rows[0]))
        self.assertEqual(app.video_path(rows[0]), self.old)


class LibraryTests(unittest.TestCase):
    def test_incorrect_prepared_profile_cannot_start_native_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            executable = root / 'mscore'
            executable.touch()
            def prepare(*args, **kwargs):
                with zipfile.ZipFile(root / 'playback.mscz', 'w') as archive:
                    archive.writestr('audiosettings.json', json.dumps({'activeSoundProfile': 'MuseScore Basic'}))
                return subprocess.CompletedProcess(args[0], 0)
            with patch.object(native_video, 'compatible_ffmpeg_dir', return_value=root), patch.object(native_video.subprocess, 'run', side_effect=prepare) as run:
                with self.assertRaisesRegex(ValueError, 'could not select Muse Sounds'):
                    native_video.export_native(str(executable), root / 'source.mscz', root / 'video.mp4', root, root / 'export.log', threading.Event())
                self.assertEqual(run.call_count, 1)

    def test_ffmpeg_8_is_found_but_9_alone_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config = subprocess.CompletedProcess([], 0, str(root), '')
            with patch.object(native_video.subprocess, 'run', return_value=config), patch.object(native_video, 'DEFAULT_LIB_FOLDERS', ()), patch.object(native_video, 'PROVIDERS', root / 'absent'):
                for name, version in zip(native_video.LIBRARY_NAMES, (63, 61, 63, 10, 7)):
                    (root / f'lib{name}.{version}.dylib').touch()
                with self.assertRaisesRegex(ValueError, 'compatible FFmpeg'):
                    native_video.compatible_ffmpeg_dir()
                for name, version in zip(native_video.LIBRARY_NAMES, (62, 60, 62, 9, 6)):
                    (root / f'lib{name}.{version}.dylib').touch()
                self.assertEqual(native_video.compatible_ffmpeg_dir(), root)


if __name__ == '__main__':
    unittest.main()
