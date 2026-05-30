# Product Requirements Document: AI Cinematic Generation System

## 1. Product Overview

**Product Name:** AI Cinematic Backend  
**Version:** 1.0 (Current State) → 2.0 (Target)  
**Date:** 2026-05-27  
**Owner:** Peter 

The AI Cinematic Generation System is a backend API that takes a reference photo of a person, a scene prompt, and a multi-character dialogue script, then produces a fully rendered cinematic video — with the person's face preserved in the video — synchronized to AI-generated character voices. It is currently built as a FastAPI Python service orchestrating three external AI APIs.

---

## 2. Problem Statement

Creating personalized cinematic video content — where a real person's face appears in an AI-generated scene with synchronized dialogue — currently requires professional studios, deep technical expertise, and significant production time. This system solves that by automating the entire pipeline: identity-preserving video generation + multi-speaker TTS synthesis + audio-video merging, all via a single API call.

**Current pain points in the prototype:**
- API keys are hardcoded in source code (critical security risk)
- No authentication or rate limiting (open endpoint)
- Synchronous execution causes long-hanging HTTP requests (30–120s)
- Missing dependencies in `requirements.txt` (`moviepy`, `pydub`)
- No persistence, logging, or observability
- Hard-coded character identities (Islam and Peter only)
- No input validation on prompt or dialogue fields
- `nano_banana.py` utility is built but unused (wasted capability)

---

## 3. Goals and Objectives

### Primary Goals
1. **Personalized Identity Preservation** — Users upload a single reference photo; the generated video faithfully preserves their face, skin tone, and likeness.
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

### FR-1: Video Generation Endpoint
- **Endpoint:** `POST /generate-video`
- **Input:** Multipart form with:
  - `image` (file): JPEG/PNG reference photo
  - `prompt` (string): Scene description
  - `dialogue` (string): Multi-line dialogue script with speaker prefixes
- **Output:** JSON with video URL/path, audio path, processing time, status

### FR-2: Identity Preservation
- The reference image must be used as the visual anchor for character identity in the generated video
- System must apply an enhanced identity-preservation prompt (facial identity, skin tone, hair, body shape)
- Generated video must use low CFG scale (≤0.5) to preserve likeness over prompt adherence

### FR-3: Multi-Speaker Dialogue
- Dialogue input format: `SpeakerName: line text` (one line per turn)
- Each speaker maps to a distinct ElevenLabs voice ID
- System must support Arabic (eleven_multilingual_v2 model)
- Lines separated by 500ms silence in the output audio
- Voices: stability=0.4, similarity_boost=0.8

### FR-4: Audio-Video Merge
- Final output must be a single `.mp4` with video (libx264) + audio (aac)
- Audio and video must start simultaneously
- If audio is longer than video, video is held on last frame (or looped — TBD)

### FR-5: Character Configuration (v2.0)
- Characters and their voice IDs should be configurable, not hardcoded
- Support adding new speaker–voice mappings via config or request payload

### FR-6: Job Status / Async Processing (v2.0)
- `POST /generate-video` returns a job ID immediately
- `GET /job/{job_id}` returns status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) + result when done
- Prevents HTTP timeouts on slow AI API responses

### FR-7: Image Scene Generation (Stretch)
- `nano_banana.py` exists and is unused; expose it as an optional step
- `POST /generate-scene` accepts two reference image URLs and returns a cinematic composite image

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

### Current Architecture (v1.0)

```
Client
  │
  ▼
POST /generate-video (FastAPI, synchronous)
  │
  ├─ Save image → temp/{uuid}.jpg
  ├─ ImgBB upload → image_url
  ├─ FAL/Kling API → video_url
  ├─ Download video → outputs/{uuid}.mp4
  ├─ ElevenLabs TTS (per line) → outputs/{uuid}.mp3
  └─ MoviePy merge → outputs/{uuid}_final.mp4
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
| **FAL / Kling v2.1** | Image-to-video generation | `fal.run/fal-ai/kling-video/v2.1/standard/image-to-video` | `FAL_API_KEY` env var |
| **ElevenLabs** | Multi-speaker TTS | `api.elevenlabs.io/v1/text-to-speech/{voice_id}` | `ELEVENLABS_API_KEY` env var |
| **ImgBB** | Image CDN hosting | `api.imgbb.com/1/upload` | `IMGBB_API_KEY` env var |
| **FAL / Nano Banana** | Scene image generation (stretch) | `fal.run/fal-ai/nano-banana` | Same `FAL_API_KEY` |

---

## 9. Key Files (Current Codebase)

| File | Role |
|------|------|
| `main.py` | FastAPI app, single `/generate-video` endpoint, full pipeline |
| `utils/fal_client.py` | Kling video generation client (`generate_video()`) |
| `utils/upload.py` | ImgBB image upload (`upload_to_imgbb()`) |
| `utils/dialogue_voice.py` | Multi-speaker ElevenLabs TTS (`generate_dialogue()`) |
| `utils/elevenlabs_voice.py` | Single-voice ElevenLabs TTS (legacy, unused) |
| `utils/nano_banana.py` | Two-character scene generation (unused, stretch feature) |
| `# requirements.txt` | Python dependencies (oddly named; needs rename + completion) |

---

## 10. Speaker / Voice Configuration

### Current (Hardcoded)
| Character | Arabic Name | Voice ID |
|-----------|------------|----------|
| Islam | اسلام | `pNInz6obpgDQGcFmaJgB` |
| Peter | بيتر | `ErXwobaYiN019PkySvjV` |

### Target (v2.0): Configurable via environment or request payload

---

## 11. Input/Output Specification

### Input: `POST /generate-video`
```
Content-Type: multipart/form-data

image      : <file>       JPEG or PNG, max 10MB
prompt     : <string>     Scene/environment description, max 500 chars
dialogue   : <string>     Multi-line, format: "SpeakerName: text\nSpeakerName: text"
```

### Output (Success)
```json
{
  "success": true,
  "status": "COMPLETED",
  "video_url": "https://cdn.kling.ai/...",
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
- Video longer than 5 seconds (Kling API constraint)

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
