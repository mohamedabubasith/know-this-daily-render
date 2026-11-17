# Know This Daily: render

The video-making part of the Know This Daily YouTube Shorts studio, run on GitHub Actions.
The studio (private) writes a shot list and starts the `render` workflow; this repo turns it into a video:
AI pictures (free sources), the Tamil narrator voice, music composed in code (FluidSynth, FluidR3_GM),
and an animated HyperFrames render. The result is kept as the run's artifact for 7 days.

Run by hand: Actions > render > Run workflow, with a job id and the film.json gzipped and base64-encoded.

Secrets: `HF_TOKEN` (voice and pictures), `SHORTS_VOICE_SPACE` (the narrator voice Space), `CLAUDE_CODE_OAUTH_TOKEN` (only drawn explainer films).

Voice G: IndicF5 by AI4Bharat (MIT), copying a storytelling clip from AI4Bharat's Rasa dataset (CC-BY-4.0), run on the runner's CPU.
