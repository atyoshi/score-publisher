# Native MuseScore video export: diagnosis and repair

Checked on 15 October 2026 with MuseScore Studio 4.7.5 (260831071), arm64, on
macOS 27.0.1. The native exporter now works on this Mac.

## Cause

The installed default FFmpeg is 9.0.2. MuseScore 4.7.5's video encoder resolver
only implements FFmpeg versions 4–8. Its library search requires matching
versioned shared libraries; an executable named `ffmpeg` on PATH is insufficient.

No compatible libraries were available in its configured or default folders,
so `currentVideoEncoder()` returned null. `VideoWriter::write()` then attempted
`encoder->open(...)` without checking for null. The crash occurred before video
generation and also reproduced with `--no-audio`.

The crash dump was inspected with LLDB without attaching to a live process:

```text
EXC_BAD_ACCESS (code=1, address=0x0)
VideoWriter::write(...) + 848
ConverterController::convertFullNotation(...) + 196
ConverterController::exportScoreVideo(...) + 648
ConsoleApp::processConverter(...) + 3636

x0 = 0x0
VideoWriter::write + 848: ldr x8, [x0]
```

The surrounding instructions set up MP4 encoder options and call the encoder's
virtual `open` method. This establishes the null encoder as the immediate crash
cause. The relevant source and concise debugger output were saved in
`.data/video-investigation/`.

The warnings about undefined `view-mode`, `piano`, and `piano-position` options
are separate CLI parser bugs: this version checks options whose declarations
are commented out. Those warnings also appear during the successful export.

## Repair applied

Installed Homebrew's separately versioned `ffmpeg@8` package, version 8.1.3,
and configured MuseScore's FFmpeg library folder:

```sh
brew install ffmpeg@8
defaults write org.musescore.MuseScore4 application.ffmpegLibsDir \
  -string /opt/homebrew/opt/ffmpeg@8/lib
```

FFmpeg 9.0.2 remains the default command-line FFmpeg. No global relinking or PATH
change was made. Only MuseScore's library-folder preference was changed; its
previous empty value is recorded in
`.data/video-investigation/previous-ffmpeg-setting.json`.

A fresh MuseScore process logged successful loading of FFmpeg 8's avutil 60,
avcodec 62, avformat 62, swscale 9, and swresample 6 libraries from that folder.
If MuseScore's main window was already open before the change, reopen the app
before trying export from that window.

## Verified output

Exported a copy of the same string-quartet score that had crashed:

```sh
"/Applications/MuseScore 4.app/Contents/MacOS/mscore" \
  --score-video --resolution 1080p --fps 30 --ls 0 --ts 0 \
  -o native-fixed.mp4 quartet.mscz
```

- Exit code 0; completed in 28.16 seconds.
- H.264 video, 1920 × 1080, 30 fps, with AAC stereo audio.
- Output duration 31.718458 seconds; 8,154,209 bytes.
- Audio is non-silent; the log records four MuseSampler instrument tracks.
- The test score copy's checksum was unchanged.
- Frames at 1 and 2 seconds show the blue cursor moving across the first
  system; later frames show it following playback onto the next page.

[Watch the native sample](.data/video-investigation/native-fixed.mp4).
Probe output, logs, selected frames, and verification JSON are in
`.data/video-investigation/` and are ignored by Git.

## What this means for Score Publisher

The native export failure that motivated the screenshot-based fallback has
been resolved on this Mac. Score Publisher's `Prepare videos` implementation
has now been switched to this native exporter. It first selects MuseSounds on a
temporary score copy, then renders the native video. Old unuploaded videos can
be upgraded through the same button, and the old media stays on disk. Uploaded
videos, resumable upload media, and newly attached videos are preserved.

The integration also exposed a score-only conversion shutdown stall. Preparation
now uses a MuseSounds batch that exports temporary WAV audio before saving the
playback copy, allowing audio-engine initialization to complete. This batch and
the following native video export both completed successfully. Ten regression
checks passed, and the two existing unuploaded videos were upgraded through the
live app queue; original media, scores, selection, and upload records remained
unchanged. Playback range requests and reuse of completed native files were also
verified. Results are in `.data/video-investigation/switch-live-results.json`.

The tested native CLI output displays full pages with a moving playback cursor.
It advances between pages rather than smoothly scrolling through one continuous
score. The upstream continuous-view export request remains open. Native export
therefore solves the moving-cursor requirement, while the exact cloud-style
continuous scrolling would need further layout/rendering work.

The upstream code also offers a flexible layout, but the CLI's `view-mode`
switch is not implemented in 4.7.5. Do not assume that adding that flag selects
the desktop export dialog's reflow behavior.

## References

- [MuseScore 4.7.5 encoder resolver](https://github.com/musescore/MuseScore/blob/v4.7.5/src/framework/media/internal/videoencoderresolver.cpp)
- [FFmpeg library search](https://github.com/musescore/MuseScore/blob/v4.7.5/src/framework/media/internal/ffmpegutils.cpp)
- [Native video writer](https://github.com/musescore/MuseScore/blob/v4.7.5/src/importexport/videoexport/internal/videowriter.cpp)
- [CLI option parser](https://github.com/musescore/MuseScore/blob/v4.7.5/src/app/internal/commandlineparser.cpp)
- [Homebrew FFmpeg 8](https://formulae.brew.sh/formula/ffmpeg@8)
- [Continuous-view export request](https://github.com/musescore/MuseScore/issues/34349)
