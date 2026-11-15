# The Hatua video guide

Two videos play one after the other in the user guide:

- `docs/guide/hatua-teachers.mp4` - for teachers (11 steps)
- `docs/guide/hatua-parents.mp4` - for parents (10 steps)

Kwamboka, the guide, is a drawing. The screens are real recordings of the Hatua portal on the practice school (made-up people). The voice is the open Kokoro voice (Apache 2.0), made offline.

How an episode is made (`teachers` or `parents`):

1. `script.py <episode>` speaks every line, measures it, and writes `plan-<episode>.json` (what is said and when) and `voice-<episode>.wav`. It needs `pip install kokoro-onnx soundfile` and the two Kokoro model files. Kiswahili words and names are given their sounds in `SAY`.
2. `record.js <episode>` opens the portal with Playwright, moves a drawn mouse pointer, types and clicks in step with the plan, and films the screen.
3. `chrome.js <episode>` draws the frame around the recording (step, caption, title cards) from `chrome.html`.
4. `guide.js <episode>` films Kwamboka from `guide.html`. Her lips follow the loudness of the real voice, and her hands move while she talks and point when she shows a step.
5. `compose.sh <episode>` joins the four with ffmpeg.

To try another voice without filming again: `python scripts/tutorial_voice.py --episode teachers` (needs internet). The lips were drawn for the first voice, so they will fit a new voice only roughly.

Not done: nobody has listened to check how the voice says "Hatua", "Kwamboka", "Asante sana" and "karibu". Listen once before showing it.
