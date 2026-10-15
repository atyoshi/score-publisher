# Muse Sounds for Score Publisher videos

Investigated on 15 October 2026 with the installed MuseScore Studio 4.7.5.

Update later on 15 October: the user downloaded Muse Brass. All nine brass
instrument directories now contain sample payloads. The missing-brass findings
below describe the initial tests, before that download. The user also confirmed
that the desired pipe-organ collection is paid and has not requested its purchase.

The native video export crash was subsequently diagnosed and repaired by
installing compatible FFmpeg 8 libraries alongside the existing FFmpeg 9.
See [the native export findings](Native%20video%20export%20investigation.md) and
its sample with a moving playback cursor. Score Publisher has now been switched
to native 1080p/30 fps export, with a separate MuseSounds preparation step on a
temporary score. The findings below record the earlier investigation.

Muse Sounds works with this app's existing FFmpeg video approach. The current
renderer explicitly selected `MuseScore Basic` before the switch, replacing the
Muse Sounds assignments already saved in many scores. Changing the audio source
does not require changing the score images or measure highlights.

## What is available on this Mac

The folders were checked for actual instrument files, not just directory names.

| Library | Instruments with files | Findings |
| --- | ---: | --- |
| Muse Woodwinds | 17/17 | Flutes, piccolo, oboe, English horn, clarinets, bassoons, saxophones |
| Muse Percussion | 45/45 | Timpani, snare, bass drum, cymbals, mallets, kits, auxiliary percussion |
| Muse Strings | 9/9 | Solo and section strings |
| Muse Keys | 9/9 | Pianos, harpsichord, celesta, electric keyboards, Hammond organ |
| Muse Choir | 7/7 | Voice sections and combined choirs |
| Muse Harp | 1/1 | Harp |
| Muse Guitars Vol 1 | 10/10 | Acoustic/electric guitars and electric bass |
| Muse Drumline | 5/5 | Snares, tenors, bass drum, cymbals |
| Muse Brass | **0/9** | Empty instrument directories; sample payloads are missing |

Muse Brass needs to be installed or repaired through Muse Hub, followed by a
fresh MuseScore process and a repeat export check. The missing files explain
the brass fallback in the test below. There is a Hammond organ sample, but the
library's generic pipe-organ score did not map to it; these are different sounds.

## Export checks

Tests ran sequentially on copies of scores. Source checksums were unchanged.
Every test below returned exit code 0 and produced decodable, non-silent stereo
audio at 44.1 kHz. Instrument assignments were checked using `--tracks-diff`;
an MP3 containing audio alone does not establish that Muse Sounds was used.

| Score / test | Result after selecting MuseSounds |
| --- | --- |
| D. 113, piano | Muse Keys Grand Piano |
| String quartet | Muse Strings on all four musical tracks |
| Dream of a Witches' Sabbath, orchestra | Muse Sounds on 18 of 25 musical tracks: eight woodwinds, four percussion, harp, five string sections. Seven brass tracks fell back to MS Basic. |
| Blackhawk, marimba | Muse Percussion Marimba |
| Chorale in C | Muse Choir on all four voice tracks |
| Adagio for Violin and Harp | Muse Strings and Muse Harp |
| Saxophone and piano | Muse Woodwinds Alto Saxophone and Muse Keys Grand Piano |
| Milk's Favorite Cookie, clarinet and harpsichord | Muse Woodwinds and Muse Keys |
| Fantasia in F-sharp minor, organ | MS Basic fallback; no matching Muse Sounds pipe organ was selected |

The metronome remains MS Basic in the reports and is excluded from musical-track
counts. Guitar and dedicated drumline samples are present, but were not tested
with musical exports. The orchestra contains notes for timpani and bass drum;
its snare and cymbal parts are empty, so their assignment was verified but their
sound was not auditioned. Marimba provides a separate populated percussion test.

An initial Nocturne in E test produced silence under both profiles because that
file contains no notes; it is excluded from the populated-score results.

Piano and quartet also exported successfully to lossless 32-bit floating-point
WAV. MP3 and WAV differ slightly in container duration due to encoding padding.
The Basic and MuseSounds MP3 durations matched for each comparison score.

A demonstration MP4 was made by copying the existing quartet video stream and
replacing its audio with Muse Sounds rendered to WAV, then encoded to AAC at
256 kbit/s. Both videos are 31.738685 seconds, and their compressed video-stream
SHA-256 hashes match. This verifies that the existing visuals can be retained;
it does not replace a listening review for articulation or synchronization.

## Listen and compare

- [Quartet video with Muse Sounds](.data/muse-sounds-investigation/quartet-muse.mp4)
- [Quartet Basic audio](.data/muse-sounds-investigation/quartet-basic.mp3) / [Muse Sounds audio](.data/muse-sounds-investigation/quartet-muse.mp3)
- [Piano Basic audio](.data/muse-sounds-investigation/piano-notes-basic.mp3) / [Muse Sounds audio](.data/muse-sounds-investigation/piano-notes-muse.mp3)
- [Orchestra Basic audio](.data/muse-sounds-investigation/orchestra-basic.mp3) / [Muse Sounds audio, with brass fallback](.data/muse-sounds-investigation/orchestra-muse.mp3)
- [Marimba](.data/muse-sounds-investigation/marimba-muse.mp3), [choir](.data/muse-sounds-investigation/choir-muse.mp3), [harp](.data/muse-sounds-investigation/harp-muse.mp3), [saxophone](.data/muse-sounds-investigation/saxophone-muse.mp3), [harpsichord](.data/muse-sounds-investigation/harpsichord-muse.mp3)

These are raw exports with their original dynamics; the comparisons are not
loudness matched. Level measurements confirm signal, not perceived quality.
Machine-readable results, track reports, logs, and library inventories are in
`.data/muse-sounds-investigation/`. These files are ignored by Git.

## How to integrate it

The installed CLI uses **`MuseSounds` without a space**, as confirmed by its
`--help`. The handbook currently shows `Muse Sounds`; use the installed spelling
for this version. The following form was verified for both `.mp3` and `.wav`:

```sh
"/Applications/MuseScore 4.app/Contents/MacOS/mscore" \
  --sound-profile MuseSounds \
  --tracks-diff tracks.json \
  -o audio.wav score.mscz
```

Recommended implementation:

1. Replace the forced Basic profile with MuseSounds, export to WAV, and let
   FFmpeg encode the final AAC audio once. Keep the current score-page/timing
   exports and video renderer.
2. Retain the track report and surface musical tracks that fall back to Basic.
   Muse Sounds only covers available, matching instruments; profile selection
   alone is insufficient. Distinguish a missing library from an unmatched
   instrument, such as the pipe organ.
3. Include the audio profile and a renderer version in generated-video and
   intermediate-audio cache identities. Currently `render()` returns any
   existing target immediately, and interrupted exports reuse `audio.mp3`.
   Simply changing the profile would leave old Basic videos in use.
4. Provide an explicit regeneration path for existing automatic videos while
   preserving attached videos and upload records. Update the UI and guides
   that currently promise Basic audio.
5. Preview the resulting audio before publishing. Preserve useful exporter
   logs; the current renderer overwrites its export diagnostics before encoding.

For scores with deliberately customized mixer instruments, an additional
“Use saved score sounds” option would be useful: omitting `--sound-profile`
retains saved track inputs rather than clearing and reassigning them. That mode
was inspected in the upstream converter source but not separately export-tested
here. It should receive the same fallback checks.

The initial investigation created samples and this report without changing the
application. The subsequent implementation switched the renderer and upgraded
the two existing unuploaded videos while retaining old media, original scores,
selection, and upload records.

## References

- [MuseScore command-line usage](https://handbook.musescore.org/appendix/command-line-usage): audio export, profiles, and batch conversion.
- [Muse Sounds handbook](https://handbook.musescore.org/sound-and-playback/musesounds): installing libraries, instrument assignment, and fallback behavior.
- [MuseScore 4.7.5 converter source](https://github.com/musescore/MuseScore/blob/v4.7.5/src/converter/internal/convertercontroller.cpp): an explicit profile clears saved track input parameters before reassignment.
