import requests
from pydub import AudioSegment

ELEVEN_API_KEY = "573e73750e552b6f9bb6026eefbfb18e8e078f1a8fc4e449d29d9a9b46be5f13"

# =========================================
# GENERATE SINGLE VOICE
# =========================================

def generate_single_voice(
    text,
    voice_id,
    output_path
):

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {

        "xi-api-key": ELEVEN_API_KEY,

        "Accept": "audio/mpeg",

        "Content-Type": "application/json"
    }

    payload = {

        "text": text,

        "model_id": "eleven_multilingual_v2",

        "voice_settings": {

            "stability": 0.4,

            "similarity_boost": 0.8
        }
    }

    response = requests.post(

        url,

        json=payload,

        headers=headers
    )

    if response.status_code != 200:

        raise Exception(response.text)

    with open(output_path, "wb") as f:

        f.write(response.content)

# =========================================
# GENERATE DIALOGUE
# =========================================

def generate_dialogue(

    dialogue,

    output_path,

    voice_map,

    per_character_paths=None

):
    """
    voice_map: {"CharacterName": "elevenlabs_voice_id", ...}
    per_character_paths: {"CharacterName": "path/to/char.mp3", ...}
      Each character gets a time-aligned audio track (their lines at correct
      timestamps, silence where other characters speak).
    Returns: total audio duration in seconds.
    """

    lines = dialogue.split("\n")

    combined = AudioSegment.empty()

    # (start_ms, AudioSegment) per speaker
    speaker_clips = {name: [] for name in voice_map}

    # Chronological [(speaker, start_sec, end_sec), ...]
    timeline = []

    for i, line in enumerate(lines):

        line = line.strip()

        if not line or ":" not in line:
            continue

        speaker, text = line.split(":", 1)
        speaker = speaker.strip()
        text = text.strip()

        if speaker not in voice_map:
            continue

        voice_id = voice_map[speaker]

        temp_path = f"temp/{speaker}_{i}.mp3"

        generate_single_voice(text, voice_id, temp_path)

        audio = AudioSegment.from_mp3(temp_path)

        # Record position before appending
        start_ms = len(combined)

        speaker_clips[speaker].append((start_ms, audio))

        end_ms = start_ms + len(audio)

        timeline.append((speaker, start_ms / 1000.0, end_ms / 1000.0))

        combined += audio

        combined += AudioSegment.silent(duration=500)

    audio_duration = combined.duration_seconds

    print(f"AUDIO DURATION: {audio_duration} sec")

    combined.export(output_path, format="mp3")

    # =========================================
    # PER-CHARACTER TIME-ALIGNED TRACKS
    # =========================================

    if per_character_paths:

        full_duration_ms = len(combined)

        for speaker, clips in speaker_clips.items():

            if speaker not in per_character_paths:
                continue

            track = AudioSegment.silent(duration=full_duration_ms)

            for start_ms, clip in clips:
                track = track.overlay(clip, position=start_ms)

            track.export(per_character_paths[speaker], format="mp3")

            print(f"EXPORTED {speaker} TRACK: {per_character_paths[speaker]}")

    return audio_duration, timeline
