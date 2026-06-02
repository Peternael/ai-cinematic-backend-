# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product Requirements

See [@PRD.md](PRD.md) for the full product requirements document, including goals, functional requirements, architecture diagrams, security requirements, and the v2.0 roadmap.

## Running the Server

```bash
uvicorn main:app --reload
```

The API runs on `http://localhost:8000` by default. There is no test suite.

## Dependencies

The requirements file is named `# requirements.txt` (with a `#` prefix — this is intentional in the current state but should be renamed). Install with:

```bash
pip install -r "# requirements.txt"
pip install moviepy pydub  # these are used but missing from requirements
```

## Architecture

This is a single-file FastAPI backend (`main.py`) with a `utils/` module. There are **two** endpoints, both synchronous (the full pipeline runs in-request):

- `POST /generate-video` — V1, green-screen avatar composite
- `POST /generate-video-v2` — V2, nano-banana-pro → Kling → ElevenLabs → fal sync-3 lip-sync

**Both endpoints take the same multipart input:**
- `images` (multiple files): one reference photo per character
- `characters` (string): JSON array `[{"name", "voice_id"?, "gender"?}, ...]` — `voice_id` is optional (a character without one is rendered but silent)
- `prompt` (string): scene description
- `dialogue` (string): multi-line `Name: text`, one turn per line

**V1 pipeline — `POST /generate-video`** (driven by `characters` length; uses `zip(images, char_list)`):
1. Parse `characters`; save + ImgBB-upload each image
2. Remove each portrait's background (FAL birefnet) → composite onto a green screen
3. Generate one shared background from `prompt` (FAL fast-sdxl)
4. Generate per-character ElevenLabs audio tracks (time-aligned)
5. Per character: upload audio to fal storage → Kling **AI-Avatar v2** (audio-driven talking video)
6. Chroma-key each avatar and composite them side-by-side onto the background with MoviePy → `outputs/{uuid}_final.mp4`

**V2 pipeline — `POST /generate-video-v2`** (decouples *visible characters* from *speakers*):
1. Parse `characters`; validate **one character entry per uploaded image**; build `voice_map` from only the characters that have a `voice_id`
2. Save + ImgBB-upload all images
3. `merge_characters_pro` composites everyone into **one** cinematic scene (FAL nano-banana-pro/edit), passing a speaker staging hint
4. Animate the composite (FAL Kling v2.1 image-to-video, 10s)
5. Generate the combined dialogue audio (ElevenLabs, only characters with a line)
6. Lip-sync the combined track onto the video (FAL **sync-lipsync v3**, native multi-speaker) → `outputs/{uuid}_final.mp4`; response also includes `video_url`

**`utils/` modules:**
- `fal_client.py` — `generate_video(prompt, image_url, duration="5")` (Kling v2.1 image-to-video, `cfg_scale=0.5`), `generate_avatar_video(image_url, audio_url)` (Kling AI-Avatar v2), `generate_background(prompt)` (fast-sdxl), `remove_background(image_url)` (birefnet)
- `upload.py` — `upload_to_imgbb(image_path)` — base64 encodes and POSTs to ImgBB
- `dialogue_voice.py` — `generate_dialogue(dialogue, output_path, voice_map, per_character_paths=None)` — multi-speaker TTS; parses `Name: text` lines and matches the speaker **case-insensitively against any name in `voice_map`** (no longer hardcoded prefixes); `eleven_multilingual_v2`, 500ms silence between lines; returns `(duration, timeline)` and optionally writes per-character time-aligned tracks. Also `generate_single_voice(text, voice_id, output_path)`
- `lipsync.py` — `upload_to_fal_storage(file_path)` and `apply_lipsync(video_url, audio_url)` (FAL `fal-ai/sync-lipsync/v3`)
- `nano_banana.py` — `merge_characters_pro(image_urls, prompt, characters, speakers)` — FAL nano-banana-pro/edit, wired into V2. Also `generate_identity_scene(image1_url, image2_url)` — legacy, hardcoded prompt, unused
- `face_match.py` — `get_face_crops(video_path, reference_image_paths, ...)` — InsightFace `buffalo_l` face detection + identity matching, returns one padded crop rect per reference (intended for deterministic per-speaker lip-sync). **Built but not wired into any endpoint yet**; downloads ~300MB on first run
- `elevenlabs_voice.py` — `generate_voice` single hardcoded-voice wrapper, legacy, not called anywhere

## Key Constraints

- **API keys are hardcoded** in every `utils/` file. Before adding any endpoint or shipping any change, these must be moved to environment variables (`FAL_API_KEY`, `ELEVENLABS_API_KEY`, `IMGBB_API_KEY`).
- The pipeline is **fully synchronous** — a single request blocks for 30–120 seconds (longer for V2) while waiting on FAL and ElevenLabs. There is no background job queue.
- Dialogue parsing is generic: each `Name: text` line is matched **case-insensitively** against the speaker names supplied in the request's `characters` payload (both `:` and the full-width `：` are accepted). Lines whose speaker isn't in the `voice_map` are silently skipped.
- **V2 decouples visible characters from speakers**: `characters` must contain exactly one entry per uploaded image (the people in the scene), but `voice_id` is optional — only characters with a `voice_id` *and* a dialogue line actually speak; the rest are rendered silent. V1, by contrast, is driven entirely by `characters` length and needs per-character audio.
- `temp/` files written during dialogue generation (`temp/{speaker}_{i}.mp3`) and the intermediate image/background/portrait files are never cleaned up.
- `face_match.py` exists for deterministic per-speaker lip-sync but is **not wired into either endpoint**; V2 relies on sync-3's native multi-speaker detection to choose which face to animate.
- The `outputs/` and `temp/` directories are created at startup by `main.py`.
