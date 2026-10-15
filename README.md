# Score Publisher

A local Mac app for selecting MuseScore pieces, preparing score videos, previewing them, and uploading an ordered batch to YouTube.

## Requirements

- macOS
- Python 3 (standard library only; no pip packages)
- MuseScore Studio 4, available at `/Applications/MuseScore 4.app`
- FFmpeg on your `PATH`
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

The app renders 1920 × 1080 score videos with FFmpeg using MuseScore score-page, timing, and audio exports. The active measure is outlined in blue. Audio uses MuseScore Basic. This does not reproduce MuseScore.com's scrolling presentation or Muse Sounds playback. Preview videos before publication, especially for unusual layouts or complex playback. The app does not modify original score files.

Alternatively, export an MP4 in MuseScore and attach it from the score preview.

## Limitations

- Sibelius files are detected but not parsed natively.
- YouTube duplicate checks match titles, so renamed works, alternate spellings, excerpts, compilations, and generic titles can produce missed or false matches.
- Composition dates and authorship need your review.
- Uploading follows YouTube's account limits and project quota. This app does not schedule release times.

See [Read Me.md](Read%20Me.md) for detailed usage and recovery guidance.
