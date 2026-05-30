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

This is a single-file FastAPI backend (`main.py`) with a `utils/` module. There is one endpoint: `POST /generate-video`.

**Pipeline (all synchronous, runs in-request):**
1. Save uploaded image to `temp/{uuid}.jpg`
2. Upload to ImgBB CDN → get public `image_url`
3. Build an identity-preservation prompt (wraps the user's `prompt`) → POST to FAL/Kling v2.1 → get `video_url`
4. Download the generated video to `outputs/{uuid}.mp4`
5. Parse `dialogue` string line-by-line by Arabic speaker prefix → call ElevenLabs TTS per line → concatenate with 500ms silence → export `outputs/{uuid}.mp3`
6. Merge with MoviePy (`libx264` + `aac`) → `outputs/{uuid}_final.mp4`
7. Return JSON with paths and `video_url`

**`utils/` modules:**
- `fal_client.py` — `generate_video(prompt, image_url)` — calls Kling v2.1 via FAL, `cfg_scale=0.5`, 5s duration
- `upload.py` — `upload_to_imgbb(image_path)` — base64 encodes and POSTs to ImgBB
- `dialogue_voice.py` — `generate_dialogue(dialogue, output_path)` — multi-speaker TTS; routes lines starting with `"اسلام:"` to Islam's voice ID and `"بيتر:"` to Peter's voice ID; uses `pydub.AudioSegment` to combine
- `elevenlabs_voice.py` — single-voice legacy wrapper, not called anywhere
- `nano_banana.py` — `generate_identity_scene(image1_url, image2_url)` — calls FAL nano-banana model; defined but not wired into any endpoint

## Key Constraints

- **API keys are hardcoded** in every `utils/` file. Before adding any endpoint or shipping any change, these must be moved to environment variables (`FAL_API_KEY`, `ELEVENLABS_API_KEY`, `IMGBB_API_KEY`).
- The pipeline is **fully synchronous** — a single request blocks for 30–120 seconds while waiting on FAL and ElevenLabs. There is no background job queue.
- Dialogue parsing only recognises two hard-coded Arabic speaker prefixes (`اسلام:` and `بيتر:`). Lines with any other prefix are silently skipped.
- `temp/` files written during dialogue generation (`temp_islam_{i}.mp3`, `temp_peter_{i}.mp3`) are never cleaned up.
- The `outputs/` and `temp/` directories are created at startup by `main.py`.
