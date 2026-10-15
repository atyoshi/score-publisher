# Score Publisher

A local Mac app for selecting MuseScore pieces, preparing score videos, previewing them, and uploading a batch to your YouTube channel.

## Open the app

Double-click **Start Score Publisher.command** in this folder. Keep its Terminal window open while preparing or uploading. The app opens in your browser at http://127.0.0.1:8765. If macOS asks which app opens the launcher, choose Terminal.

MuseScore Studio 4.7.5, FFmpeg, and Python are already installed on this Mac. No Python packages are needed.

## Use it

1. Start with the **Scores** folder (`~/Music/Scores`), or use **Choose folder**. You can also paste a folder path and click **Refresh**. Only scores directly inside the selected folder are listed; backups and nested folders are ignored.
2. Check the pieces you want. Nothing is selected by default. Search or filter by composer to help exclude copied scores. Composer metadata can be wrong, so composer filtering is only a clue. The filename is the default video title.
3. Click **Preview** to review the score, check **Include in upload batch**, edit its title, and set the month you wrote it. Use **Previous piece** and **Next piece** to browse scores without closing the preview. The initial month comes from the score's internal creation date, not its filesystem date. Click **Save changes**.
4. Arrange the numbered batch using **↑** and **↓** in the sidebar. New selections go to the end; the order is saved. You can reorder again during final review. Click **Prepare videos** to process the selected pieces one at a time. Preview again to play the completed video. You can prepare one piece from its preview as well.
5. Connect YouTube using the one-time setup below. Choose visibility and the appropriate audience for the batch, then click **Review upload batch**.
6. Check the complete list, upload order, titles, descriptions, and visibility. Videos are uploaded one at a time in the numbered order. This determines upload sequence; it does not schedule publication times or control how YouTube sorts your channel. **Upload batch** is the action that sends the videos to YouTube.

Descriptions contain exactly one line, for example:

> Written in December 2025

Selections and edits persist across app restarts and folder changes. Completed videos are reused. Exact score duplicates are flagged, and exact duplicates within an upload batch or previously uploaded through this app are rejected. Different revisions of the same composition need your review. Use **Check existing YouTube videos** to compare against uploads made through other tools. This matches titles, not musical content.

## Video appearance and sound

Automatic rendering creates native **1920 × 1080, 30 fps MP4s** with a moving blue playback cursor. Full score pages advance with the music. This is MuseScore's native page view, rather than the cloud player's continuous scrolling.

The app selects **Muse Sounds** on a temporary copy before exporting the video. Installed matching libraries provide the instrument sounds; missing or unsupported instruments fall back to MS Basic. This includes scores imported from MusicXML. It never changes your original scores.

### Video setup

MuseScore Studio **4.7 or newer** is required. Studio 4.7 supports FFmpeg shared libraries through version 8; having only FFmpeg 9 makes the native exporter crash. This Mac has already been configured with FFmpeg 8 alongside the default version 9. For another Apple Silicon Mac:

```sh
brew install ffmpeg@8
defaults write org.musescore.MuseScore4 application.ffmpegLibsDir -string /opt/homebrew/opt/ffmpeg@8/lib
```

Reopen MuseScore if it was already running. Keep FFprobe installed for video validation. Score Publisher checks for compatible libraries before invoking the native exporter and reports export errors in Preview, with the diagnostic log filename.

### Upgrading existing videos

Older automatically generated videos are labeled **Older video · prepare to upgrade**. They remain viewable, but need upgrading before a new upload. Use **Prepare videos** for your selected pieces, or **Upgrade this video** in Preview. The new native video is saved under a different filename, leaving the old file on disk. Videos already uploaded or associated with an interrupted upload retain their original media and upload records.

Videos attached through Preview are reused. Attachments saved by older versions lack a source label; clicking Prepare on those creates a native replacement while leaving the old file on disk. Sound and mixer changes are detected when you **Refresh** the score folder.

You can still export an MP4 yourself and use **Preview → Attach a video exported in MuseScore**. Paste that MP4's full local path. The app copies it into its Videos folder and validates that it has audio and video.

Preview the result before publication, especially for unusual layouts, multi-movement works, or scores with complex playback. Composition dates and copied scores always need your judgment.

## Connect YouTube once

1. Open [Google Cloud](https://console.cloud.google.com/). Create or select a project.
2. Enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
3. Configure Google Auth Platform / OAuth consent. If the app is in Testing, add the Google account that owns your channel as a test user.
4. Create an OAuth client of type **Desktop app**. Download its JSON credentials.
5. In Score Publisher, click **Connect YouTube**, select that JSON file, then click **Sign in with Google**. Choose the account and channel you intend to upload to and grant upload access.
6. You return to Score Publisher after sign-in. The header should read **YouTube connected**.

The app requests YouTube upload access and read-only access to your channel’s existing uploads. Google may require verification or restrict uploads from an unverified project to private visibility. Your channel's upload limits and the project's quota also apply. Uploading does not bypass those limits. Testing-mode authorizations may expire and require reconnecting.

If you connected before channel checking was added, reconnect to grant read access. Signing in also starts a channel check.

Your credentials and saved authorization are stored locally in **.data** with restricted file permissions. Keep that hidden folder private and exclude it when sharing the app. It is not encrypted. You can revoke access from your [Google account connections](https://myaccount.google.com/connections).

## Interruptions and storage

- Videos are saved in **Videos**. Leave them there if you want the app to reuse them. Names use an internal identifier to avoid collisions between similarly titled pieces.
- Upload session links and completed YouTube video IDs are saved in **.data/state.json**. After a network interruption, retry the selected batch with the same title, date, audience, and visibility. The app queries the existing session before resuming, including checking whether a lost final response actually completed the upload.
- An upload error stops the remaining batch. Resolve it, then retry. Completed uploads are skipped. An expired session may require troubleshooting; the app deliberately does not silently create another upload.
- The stop button lets a running export finish and stops queued work. During upload, it stops at a chunk boundary. Closing the launcher while rendering can leave an unfinished export process; use Stop first and let the active piece finish.
- If you edit a source score, **Refresh** to invalidate its old preview. Previously uploaded pieces keep their YouTube record, preventing automatic reposts.
- The hidden **.data** folder also contains diagnostic logs and temporary rendering files. If a piece fails, its Preview shows the log filename.
- Keep the launcher window open. To stop the local app, press **Control-C** in that window.

## Verification performed

Core score discovery, preview, rendering, description validation, and upload recovery flows were exercised locally. The native switch passed 10 regression checks and two real video upgrades through the app queue, including audio/video validation, playback range requests, cache reuse, and preservation of original files and upload records. No real YouTube upload was performed; Google credentials and authorization must be supplied by you.

Official references: [MuseScore command-line export](https://handbook.musescore.org/appendix/command-line-usage), [Google desktop authorization](https://developers.google.com/identity/protocols/oauth2/native-app), [YouTube resumable uploads](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol).

## Suggestions and other notation programs

The **Suggestions** tab searches a folder and its subfolders for score files. The initial search covers your Music folder; change the search folder whenever you like. Hidden directories, Backup Scores, backup directories, and symlinks are skipped. Search is capped at 50,000 visited files or 3,000 score results; choose a smaller folder if the app reports that limit.

The search results are suggestions to review, not claims about ownership or musical quality. Several files may be revisions or copies of the same piece.

- **MSCZ / MSCX**: use directly.
- **MUSICXML / MXL / score XML**: use directly through MuseScore. General-purpose XML files are ignored. Check the imported notation and playback; layout, sounds, and some notational details may differ from the original program. MusicXML's encoding date is not used as the composition date.
- **SIB**: open in Sibelius, export as MusicXML, then search again or open the export folder in the Library. Native Sibelius parsing is not implemented.
- **MID / MIDI**: open in MuseScore, review the notation, and save as MSCZ first.
- **.musescore**: this is not the usual MuseScore score extension. If encountered, the app asks you to export a recognized format rather than guessing how to read it.

**Open folder to review** loads that folder's directly supported scores and opens the chosen piece's preview. It does not select the piece, copy the source score, or start an upload. It switches the active library folder; selections in your other folders remain saved.

## Check against your existing YouTube videos

Click **Check existing YouTube videos** after connecting. The app reads the signed-in channel's uploads playlist, including all returned pages, and saves a local title index. The channel name, title count, and check time are shown so you can assess how current it is. A failed refresh retains the previous complete index and displays an error.

Exact normalized titles, close spelling matches, and sufficiently distinctive titles contained in a longer title are flagged as **possible** matches. This cannot prove musical identity or guarantee that a piece is absent: generic titles can produce false matches, and renamed videos, alternate spellings, excerpts, or pieces contained in longer compilations can be missed. No audio fingerprinting is performed.

In **Preview**, open the matching YouTube links. A flagged piece is blocked from uploading unless you explicitly check **I checked these videos; upload this piece anyway**. If a later channel check finds additional matching videos, that review must be repeated. Save title edits before reviewing matches. The upload batch review also tells you if your channel has not been checked.

Channel listing, pagination, failure handling, title matching, MusicXML parsing, compressed MusicXML manifests, backup exclusion, and review invalidation were tested locally with simulated Google responses. The live channel check still requires your Google authorization.
