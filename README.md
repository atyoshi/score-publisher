# Score Publisher

A local Mac app for selecting MuseScore pieces, preparing score videos, previewing them, and uploading an ordered batch to YouTube.

## Requirements

- macOS
- Python 3 (standard library only; no pip packages)
- MuseScore Studio 4.7 or newer, available at `/Applications/MuseScore 4.app`
- FFprobe on your `PATH`, and compatible FFmpeg shared libraries configured in MuseScore (see below)
- A Google Cloud project with YouTube Data API v3 enabled, plus a Desktop OAuth client, if you want to upload or check your channel

The app defaults to `~/Music/Scores`. Use **Choose folder** in the app to select a different folder.

## Run

Double-click **Start Score Publisher.command** and keep its Terminal window open. The app opens at [http://127.0.0.1:8765](http://127.0.0.1:8765). Or run `python3 app.py` from this folder.

The app scans scores directly inside the chosen library folder and lets you select, preview, edit titles and composition dates, reorder a batch, prepare score videos, and review everything before upload. Video descriptions use the format `Written in {Month} {Year}`. Nothing uploads until you click **Upload batch**.

The **Suggestions** tab searches a folder tree for MuseScore, MusicXML, Sibelius, and MIDI files. MuseScore and MusicXML files can be imported for review. Sibelius files need to be exported from Sibelius as MusicXML first; MIDI files should be opened and saved as a MuseScore score. File discovery does not determine ownership or authorship.

## YouTube setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project and enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
2. Configure Google Auth Platform / OAuth consent. If the app is in Testing, add the channel owner's Google account as a test user.
3. Create an OAuth client of type **Desktop app** and download its JSON credentials.
4. In Score Publisher, click **Connect YouTube**, select the JSON file, and sign in to the intended channel.

The app requests permission to upload videos and read the channel's uploads list for title-based duplicate checks. Duplicate checks are suggestions based on titles, not audio matching. Review every match yourself. Google may require verification or restrict an unverified project's uploads to private visibility.

OAuth credentials, upload state, logs, and generated videos remain local in `.data/` and `Videos/`; both are excluded from Git. The local credentials are not encrypted. Do not share `.data/` or generated user content.

## Rendering notes

The app uses MuseScore's native exporter to create 1920 × 1080 videos at 30 fps with a moving blue playback cursor. It selects Muse Sounds on a temporary score copy, then exports that copy. Available instrument libraries are used automatically; unsupported or missing sounds fall back to MS Basic. Original scores are never changed. The native layout shows full pages and advances between them; it does not continuously scroll like the cloud player.

MuseScore 4.7 needs FFmpeg shared libraries from versions 4–8. FFmpeg 9 alone causes its native exporter to crash. On Apple Silicon Macs, install `ffmpeg@8` alongside your default FFmpeg and configure MuseScore:

```sh
brew install ffmpeg@8
defaults write org.musescore.MuseScore4 application.ffmpegLibsDir -string /opt/homebrew/opt/ffmpeg@8/lib
```

This Mac is already configured. Reopen MuseScore if it was running before configuration. The app checks for compatible libraries before starting an export.

Older generated videos stay available to preview but are marked for upgrade. Select them and click **Prepare videos**, or use **Upgrade this video** in Preview. New videos use a separate filename, and the old files remain on disk. Attached videos and videos with completed or resumable upload records are preserved. Sound or mixer changes in a score are detected when you refresh the folder. Preview the result before publication.

Alternatively, export an MP4 in MuseScore and attach it from the score preview.

## Limitations

- Sibelius files are detected but not parsed natively.
- YouTube duplicate checks match titles, so renamed works, alternate spellings, excerpts, compilations, and generic titles can produce missed or false matches.
- Composition dates and authorship need your review.
- Uploading follows YouTube's account limits and project quota. This app does not schedule release times.

See [Read Me.md](Read%20Me.md) for detailed usage and recovery guidance.
