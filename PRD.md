# Product Requirements Document: AI Cinematic Generation System

## 1. Product Overview

**Product Name:** AI Cinematic Backend  
**Version:** 1.0 (Current State) → 2.0 (Target)  
**Date:** 2026-05-27  
**Owner:** Peter 

The AI Cinematic Generation System is a backend API that takes one or more reference photos (one per character), a scene prompt, and a multi-character dialogue script, then produces a fully rendered cinematic video — with each person's face preserved in the video — synchronized to AI-generated character voices. It is built as a FastAPI Python service orchestrating ImgBB, ElevenLabs, and several FAL models. It currently exposes **two** generation endpoints: `POST /generate-video` (V1, green-screen avatar composite) and `POST /generate-video-v2` (V2, nano-banana-pro → Kling → ElevenLabs → fal sync-3 lip-sync).

---

## 2. Problem Statement

Creating personalized cinematic video content — where a real person's face appears in an AI-generated scene with synchronized dialogue — currently requires professional studios, deep technical expertise, and significant production time. This system solves that by automating the entire pipeline: identity-preserving video generation + multi-speaker TTS synthesis + audio-video merging, all via a single API call.

**Current pain points in the prototype:**
- API keys are hardcoded in source code (critical security risk)
- No authentication or rate limiting (open endpoint)
- Synchronous execution causes long-hanging HTTP requests (30–120s)
- Missing dependencies in `requirements.txt` (`moviepy`, `pydub`)
- No persistence, logging, or observability
- No input validation on prompt or dialogue fields (beyond V2's "one character per image" check)
- `face_match.py` (InsightFace per-speaker face matching) is built but not yet wired into either endpoint

> **Note:** Two prototype pain points from the original draft are now resolved — characters/voices are configurable via the `characters` payload (no longer hard-coded to Islam/Peter), and `nano_banana.py` is wired into V2 via `merge_characters_pro`.

---

## 3. Goals and Objectives

### Primary Goals
1. **Personalized Identity Preservation** — Users upload one reference photo per character; the generated video faithfully preserves each person's face, skin tone, and likeness.
2. **Multi-Speaker Dialogue Synthesis** — Support multiple named characters with distinct AI voices, including full Arabic/multilingual dialogue.
3. **One-Call API** — Accept image + prompt + dialogue in a single request and return a final merged video.

### Product Goals (v2.0)
- Make the system production-safe (secrets management, auth, rate limiting)
- Support configurable characters (not just Islam/Peter)
- Move to async/background job processing to avoid HTTP timeouts
- Add persistence and job status polling
- Make the system deployable via Docker

---

## 4. Target Users

| User | Description |
|------|-------------|
| **Content Creators** | Arab-market creators who want AI-generated cinematic reels featuring themselves |
| **Developers / Integrators** | Teams embedding personalized video generation into a product |
| **Internal Users (Current)** | Peter and Islam — the primary named characters in the current prototype |

---

## 5. Functional Requirements

### FR-1: Video Generation Endpoints
- **Endpoints:** `POST /generate-video` (V1, avatar composite) and `POST /generate-video-v2` (V2, nano-banana-pro → Kling → sync-3). Both share the same input.
- **Input:** Multipart form with:
  - `images` (files): one JPEG/PNG reference photo **per character**
  - `characters` (string): JSON array `[{"name", "voice_id"?, "gender"?}, ...]` — `voice_id` optional
  - `prompt` (string): Scene description
  - `dialogue` (string): Multi-line `Name: text`, one turn per line
- **Output:** JSON with video path (+ `video_url` on V2), audio path, processing time, status

### FR-2: Identity Preservation
- The reference image must be used as the visual anchor for character identity in the generated video
- System must apply an enhanced identity-preservation prompt (facial identity, skin tone, hair, body shape)
- Generated video must use low CFG scale (≤0.5) to preserve likeness over prompt adherence

### FR-3: Multi-Speaker Dialogue
- Dialogue input format: `SpeakerName: line text` (one line per turn)
- Speaker names are matched **case-insensitively** against the `characters` payload (configurable; not hardcoded). Both `:` and full-width `：` are accepted
- Each speaking character maps to a distinct ElevenLabs voice ID via `characters[].voice_id`
- System must support Arabic (eleven_multilingual_v2 model)
- Lines separated by 500ms silence in the output audio
- Voices: stability=0.4, similarity_boost=0.8
- A character listed without a `voice_id` (or with no dialogue line) is rendered in the scene but stays silent (V2)

### FR-4: Audio-Video Merge
- Final output must be a single `.mp4` with video (libx264) + audio (aac)
- Audio and video must start simultaneously
- If audio is longer than video, video is held on last frame (or looped — TBD)

### FR-5: Character Configuration — ✅ DONE (v1.0)
- Characters and their voice IDs are configurable via the `characters` request payload (no longer hardcoded)
- New speaker–voice mappings are added per request; `gender` is also passed through to the scene-composite prompt

### FR-6: Job Status / Async Processing (v2.0)
- `POST /generate-video` returns a job ID immediately
- `GET /job/{job_id}` returns status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) + result when done
- Prevents HTTP timeouts on slow AI API responses

### FR-7: Image Scene Generation — ✅ DONE (v1.0, integrated)
- `nano_banana.py`'s `merge_characters_pro` is wired into the V2 pipeline: it composites all reference photos into one cinematic scene (FAL nano-banana-pro/edit) that Kling then animates
- It is not exposed as a standalone `POST /generate-scene` endpoint — it runs as an internal step of `/generate-video-v2`

---

## 6. Non-Functional Requirements

### NFR-1: Security (Critical)
- All API keys must be loaded from environment variables, not hardcoded
- The `/generate-video` endpoint must require an API key or auth token
- Input validation on `prompt` and `dialogue` (max length, sanitization)
- No secrets in source control

### NFR-2: Reliability
- Graceful error handling for all external API failures (FAL, ElevenLabs, ImgBB)
- Temporary files cleaned up after job completes or fails
- Retries with backoff for transient network errors

### NFR-3: Observability
- Replace `print()` statements with structured logging (Python `logging` module)
- Log request ID, each pipeline step, duration, and API response codes
- Error logs include full stack traces

### NFR-4: Performance
- Individual generation jobs expected to take 30–120 seconds (API-bound)
- System should handle concurrent requests without blocking (async or worker queue)
- File I/O should not block the event loop

### NFR-5: Dependency Hygiene
- `requirements.txt` must list all runtime dependencies with pinned versions:
  - fastapi, uvicorn, requests, python-multipart, pillow
  - moviepy, pydub (currently missing)
  - Remove unused: edge-tts

### NFR-6: Portability
- System must be runnable via Docker (`Dockerfile` + `docker-compose.yml`)
- Environment configured entirely via `.env` file

---

## 7. Technical Architecture

### Current Architecture (v1.0) — two synchronous endpoints

```
Client ──(images[], characters JSON, prompt, dialogue)──► FastAPI (synchronous)

POST /generate-video  (V1 — green-screen avatar composite)
  ├─ per character: ImgBB upload → birefnet remove-bg → green-screen portrait
  ├─ fast-sdxl shared background
  ├─ ElevenLabs per-character audio tracks
  ├─ per character: Kling AI-Avatar v2 (audio-driven)
  └─ MoviePy chroma-key composite → outputs/{uuid}_final.mp4

POST /generate-video-v2  (V2 — nano-banana-pro → Kling → sync-3)
  ├─ validate one character per image; build voice_map (voice_id holders only)
  ├─ ImgBB upload all images
  ├─ nano-banana-pro/edit → single composite scene (+ speaker staging hint)
  ├─ Kling v2.1 image-to-video (10s) → base video
  ├─ ElevenLabs → combined dialogue audio
  └─ fal sync-lipsync v3 (combined track) → outputs/{uuid}_final.mp4 (+ video_url)
         │
         ▼
      JSON Response
```

### Target Architecture (v2.0)

```
Client
  │
  ▼
POST /generate-video → returns { job_id }
  │
  ▼
Background Worker (Celery / asyncio task)
  ├─ ImgBB → image_url
  ├─ FAL/Kling → video_url
  ├─ ElevenLabs → audio file
  └─ MoviePy → final.mp4 → stored output

Client polls:
GET /job/{job_id} → { status, video_url, ... }
```

---

## 8. External API Integrations

| Service | Role | Endpoint | Key Config |
|---------|------|----------|-----------|
| **FAL / Kling v2.1** | Image-to-video generation (V1 & V2) | `fal.run/fal-ai/kling-video/v2.1/standard/image-to-video` | `FAL_API_KEY` |
| **FAL / Kling AI-Avatar v2** | Audio-driven talking avatar (V1) | `fal.run/fal-ai/kling-video/ai-avatar/v2/standard` | `FAL_API_KEY` |
| **FAL / Nano Banana Pro** | Multi-character scene composite (V2) | `fal.run/fal-ai/nano-banana-pro/edit` | `FAL_API_KEY` |
| **FAL / fast-sdxl** | Background image generation (V1) | `fal.run/fal-ai/fast-sdxl` | `FAL_API_KEY` |
| **FAL / birefnet** | Portrait background removal (V1) | `fal.run/fal-ai/birefnet` | `FAL_API_KEY` |
| **FAL / sync-lipsync v3** | Multi-speaker lip-sync (V2) | `fal-ai/sync-lipsync/v3` (fal_client) | `FAL_KEY` env var |
| **ElevenLabs** | Multi-speaker TTS | `api.elevenlabs.io/v1/text-to-speech/{voice_id}` | `ELEVENLABS_API_KEY` |
| **ImgBB** | Image CDN hosting | `api.imgbb.com/1/upload` | `IMGBB_API_KEY` |

---

## 9. Key Files (Current Codebase)

| File | Role |
|------|------|
| `main.py` | FastAPI app; `/generate-video` (V1) and `/generate-video-v2` (V2) endpoints + both pipelines |
| `utils/fal_client.py` | FAL clients: `generate_video` (Kling v2.1), `generate_avatar_video` (Kling AI-Avatar v2), `generate_background` (fast-sdxl), `remove_background` (birefnet) |
| `utils/upload.py` | ImgBB image upload (`upload_to_imgbb()`) |
| `utils/dialogue_voice.py` | Multi-speaker ElevenLabs TTS (`generate_dialogue(dialogue, output_path, voice_map, per_character_paths=None)`) |
| `utils/lipsync.py` | FAL storage upload + sync-lipsync v3 (`upload_to_fal_storage`, `apply_lipsync`) |
| `utils/nano_banana.py` | Multi-character scene composite (`merge_characters_pro`, wired into V2); `generate_identity_scene` (legacy, unused) |
| `utils/face_match.py` | InsightFace per-speaker face matching (`get_face_crops`) — built, not yet wired in |
| `utils/elevenlabs_voice.py` | Single-voice ElevenLabs TTS (legacy, unused) |
| `# requirements.txt` | Python dependencies (oddly named; needs rename + completion) |

---

## 10. Speaker / Voice Configuration

### Current — request-driven via the `characters` payload
Voices are supplied per request as `characters[].voice_id`; speaker names are matched case-insensitively. Common voice IDs used in testing:

| Character | Arabic Name | Voice ID |
|-----------|------------|----------|
| Islam | اسلام | `pNInz6obpgDQGcFmaJgB` |
| Peter | بيتر | `ErXwobaYiN019PkySvjV` |

These are no longer hardcoded in the dialogue logic — any names/voice IDs in the request work.

---

## 11. Input/Output Specification

### Input: `POST /generate-video` and `POST /generate-video-v2`
```
Content-Type: multipart/form-data

images     : <file>...    one JPEG/PNG per character (repeat the field)
characters : <string>     JSON: [{"name","voice_id"?,"gender"?}, ...]
                          (V2: exactly one entry per uploaded image; voice_id optional)
prompt     : <string>     Scene/environment description
dialogue   : <string>     Multi-line, format: "Name: text\nName: text"
```

### Output (Success)
```json
{
  "success": true,
  "status": "COMPLETED",
  "video_url": "https://...",          // V2 only
  "video_path": "outputs/{uuid}_final.mp4",
  "audio_path": "outputs/{uuid}.mp3",
  "time_taken": 87.3
}
```

### Output (Error)
```json
{
  "success": false,
  "error": "<human-readable error message>"
}
```

---

## 12. Security Requirements

| Requirement | Priority |
|------------|----------|
| Move all API keys to `.env` / environment variables | Critical |
| Add API key auth to all endpoints (`X-API-Key` header) | High |
| Validate and sanitize `prompt` and `dialogue` inputs | High |
| Implement request size limits (image max 10MB) | High |
| Add CORS policy configuration | Medium |
| Periodic cleanup of `temp/` and `outputs/` directories | Medium |
| Rate limiting (e.g., 10 req/min per client) | Medium |

---

## 13. Out of Scope (v1.0 → v2.0)

- Frontend / client application
- User accounts or persistent user profiles
- Video editing or post-processing beyond audio merge
- Real-time streaming of video generation progress
- Support for non-Arabic languages (already supported by ElevenLabs multilingual, but not a stated requirement)
- Video longer than ~10 seconds (Kling API constraint; V1 uses 5s, V2 requests 10s)

---

## 14. Success Metrics

| Metric | Target |
|--------|--------|
| End-to-end generation time | < 120 seconds |
| Identity preservation quality | Subjective — faces recognizable in output |
| API error rate | < 5% |
| Audio-video sync accuracy | ≤ 200ms drift |
| System uptime (v2.0) | 99% |

---

## 15. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Kling API rate limits or outages | Implement retries + expose error clearly |
| ElevenLabs quota exhaustion | Track usage; surface quota error in response |
| Long generation blocking HTTP | Move to async background jobs (v2.0) |
| API keys leaked in repo | Immediate: rotate keys; migrate to env vars |
| `moviepy` version incompatibility | Pin version in requirements |

---

## 16. Immediate Action Items (Pre-v2.0)

1. **Rotate all exposed API keys** (FAL, ElevenLabs, ImgBB) — they are currently committed to source
2. Rename `# requirements.txt` → `requirements.txt` and add `moviepy`, `pydub`
3. Move all API keys to `.env` file and load via `python-dotenv`
4. Add basic API key authentication to `/generate-video`
5. Fix the `requirements.txt` naming issue and complete missing dependencies
6. Add structured logging to replace `print()` statements
7. Add cleanup of temp files after job completes

---

## 17. Future Enhancements (Post-v2.0)

- Support uploading two reference images (one per character) using `nano_banana.py`
- Support custom voice cloning (ElevenLabs voice clone API)
- Web UI for non-technical users
- Webhook support for job completion notifications
- Support longer videos (10s, 30s) as Kling upgrades
- Multi-scene chaining (sequence of clips merged into one video)
