"""MuseScore 4.7 native playback-video export, with a compatible-library check."""
import pathlib
import subprocess
import zipfile
import json

RENDERER = 'native-musesounds-1080p30-v1'

# FFmpeg versions 8 through 4, as supported by MuseScore Studio 4.7.
LIBRARY_VERSIONS = ((62, 60, 62, 9, 6), (61, 59, 61, 8, 5),
                    (60, 58, 60, 7, 4), (59, 57, 59, 6, 4), (58, 56, 58, 5, 3))
LIBRARY_NAMES = ('avformat', 'avutil', 'avcodec', 'swscale', 'swresample')
DEFAULT_LIB_FOLDERS = ('/opt/homebrew/lib', '/usr/local/lib')
PROVIDERS = pathlib.Path('/Library/Application Support/FFmpeg/Providers')


def compatible_ffmpeg_dir():
    """Mirror MuseScore's search; FFmpeg 9 alone otherwise causes a null dereference."""
    setting = subprocess.run(['defaults', 'read', 'org.musescore.MuseScore4',
                              'application.ffmpegLibsDir'], capture_output=True, text=True, timeout=10)
    folders = []
    if setting.returncode == 0 and setting.stdout.strip():
        path = pathlib.Path(setting.stdout.strip())
        folders.append(path if path.is_dir() else path.parent)
    if PROVIDERS.is_dir():
        folders.extend(p / 'lib' for p in PROVIDERS.iterdir() if p.is_dir())
    folders.extend(map(pathlib.Path, DEFAULT_LIB_FOLDERS))
    for folder in folders:
        for versions in LIBRARY_VERSIONS:
            if all((folder / f'lib{name}.{version}.dylib').is_file()
                   for name, version in zip(LIBRARY_NAMES, versions)):
                return folder
    raise ValueError('MuseScore needs compatible FFmpeg libraries for native video export. '
                     'Install ffmpeg@8 and set MuseScore’s FFmpeg library folder to '
                     '/opt/homebrew/opt/ffmpeg@8/lib. See Read Me.md → Video setup.')


def export_native(executable, score, destination, work, log, stopped):
    """Select Muse Sounds on a disposable score, then export its moving-cursor video."""
    if not pathlib.Path(executable).is_file():
        raise ValueError('Install MuseScore Studio 4.7 or newer at /Applications/MuseScore 4.app.')
    libraries = compatible_ffmpeg_dir()
    playback = work / 'playback.mscz'
    with log.open('w') as output:
        output.write(f'Native MuseScore video · MuseSounds · 1080p · 30 fps\nFFmpeg libraries: {libraries}\n')

    def run(command):
        if stopped.is_set():
            raise ValueError('Stopped. Retry to prepare this video.')
        with log.open('a') as output:
            output.write('\n' + repr(command) + '\n')
            output.flush()
            try:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=7200)
            except subprocess.TimeoutExpired:
                raise ValueError('MuseScore export timed out. See ' + log.name) from None
        if result.returncode:
            raise ValueError(f'MuseScore export failed (exit {result.returncode}). See {log.name}')

    # --score-video ignores --sound-profile in Studio 4.7. Its score-only conversion
    # can also stall during audio-engine shutdown. Export audio first in the batch
    # so initialization completes, then save the prepared score for native video.
    job = work / 'playback-job.json'
    job.write_text(json.dumps([{'in': str(score), 'out': [str(work / 'playback-audio.wav'), str(playback)]}]))
    run([executable, '--sound-profile', 'MuseSounds', '-j', str(job)])
    if not playback.is_file():
        raise ValueError('MuseScore did not prepare the playback score. See ' + log.name)
    try:
        with zipfile.ZipFile(playback) as archive:
            profile = json.loads(archive.read('audiosettings.json')).get('activeSoundProfile')
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        raise ValueError('MuseScore saved an invalid playback score. See ' + log.name) from None
    if profile != 'MuseSounds':
        raise ValueError('MuseScore could not select Muse Sounds. See ' + log.name)
    run([executable, '--score-video', '--resolution', '1080p', '--fps', '30',
         '--ls', '0', '--ts', '0', '-o', str(destination), str(playback)])
    if not destination.is_file():
        raise ValueError('MuseScore did not create a video. See ' + log.name)
