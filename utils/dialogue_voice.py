import os
import requests
from pydub import AudioSegment

ELEVEN_API_KEY = "573e73750e552b6f9bb6026eefbfb18e8e078f1a8fc4e449d29d9a9b46be5f13"

# =========================================
# GENERATE SINGLE VOICE
# =========================================
def generate_single_voice(text, voice_id, output_path):
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

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        raise Exception(response.text)

    with open(output_path, "wb") as f:
        f.write(response.content)

# =========================================
# GENERATE DIALOGUE - النسخة المؤمنة للعربي والإنجليزي
# =========================================
def generate_dialogue(dialogue, output_path, voice_map, per_character_paths=None):
    """
    voice_map: {"CharacterName": "elevenlabs_voice_id", ...}
    per_character_paths: {"CharacterName": "path/to/char.mp3", ...}
    """
    lines = dialogue.split("\n")
    combined = AudioSegment.empty()

    # تحويل مفاتيح الـ voice_map كلها لـ lowercase لتفادي مشاكل الـ Case Sensitivity
    clean_voice_map = {str(k).strip().lower(): v for k, v in voice_map.items()}
    
    # (start_ms, AudioSegment) لكل متحدث باستخدام الاسم الـ cleaned
    speaker_clips = {str(name).strip().lower(): [] for name in voice_map}

    # التايم لاين الزمني بالثواني
    timeline = []

    for i, line in enumerate(lines):
        line = line.strip()

        # دعم النقطتين فوق بعض سواء إنجليزي أو عربي لتفادي لخبطة كيبورد فلاتر
        if ":" in line:
            speaker, text = line.split(":", 1)
        elif "：" in line:
            speaker, text = line.split("：", 1)
        else:
            print(f"[AUDIO] Skipping line (No valid colon found): {line}")
            continue

        # تنظيف تام للاسم المقصوص من أي مسافات مخفية وتحويله لسمول
        speaker_cleaned = speaker.strip().lower()
        text = text.strip()

        # لو السطر فاضي بعد الفصل مش هنقراه
        if not text:
            continue

        # التشيك أصبح آمن تماماً ومستحيل يقع بسبب الكابيتال أو المسافات
        if speaker_cleaned not in clean_voice_map:
            print(f"[AUDIO] Speaker '{speaker_cleaned}' not found in voice_map. Skipping.")
            continue

        voice_id = clean_voice_map[speaker_cleaned]
        temp_path = f"temp/{speaker_cleaned}_{i}.mp3"

        # توليد الصوت من ElevenLabs والكلام العربي هيتقري طبيعي جداً
        generate_single_voice(text, voice_id, temp_path)
        audio = AudioSegment.from_mp3(temp_path)

        # حساب التوقيت بالملي ثانية
        start_ms = len(combined)
        speaker_clips[speaker_cleaned].append((start_ms, audio))
        end_ms = start_ms + len(audio)

        # حفظ التايم لاين بالثواني (بنرجع الاسم الأصلي المبعوت من الـ voice_map عشان يطابق الـ char_list بره)
        # بنجيب الاسم بالشكل اللي بره عشان الـ Lip-sync ميتلخبطش
        original_speaker_name = [k for k in voice_map if k.strip().lower() == speaker_cleaned][0]
        timeline.append((original_speaker_name, start_ms / 1000.0, end_ms / 1000.0))

        combined += audio
        combined += AudioSegment.silent(duration=500)

    audio_duration = combined.duration_seconds
    print(f"AUDIO DURATION: {audio_duration} sec")
    print(f"GENERATED TIMELINE: {timeline}")

    combined.export(output_path, format="mp3")

    # =========================================
    # PER-CHARACTER TIME-ALIGNED TRACKS
    # =========================================
    if per_character_paths:
        full_duration_ms = len(combined)
        
        # تحويل مسارات الحفظ لـ lowercase لمطابقتها مع الأسامي النظيفة
        clean_per_char_paths = {str(k).strip().lower(): v for k, v in per_character_paths.items()}

        for speaker_cleaned, clips in speaker_clips.items():
            if speaker_cleaned not in clean_per_char_paths:
                continue

            track = AudioSegment.silent(duration=full_duration_ms)

            for start_ms, clip in clips:
                track = track.overlay(clip, position=start_ms)

            track.export(clean_per_char_paths[speaker_cleaned], format="mp3")
            print(f"EXPORTED {speaker_cleaned} TRACK: {clean_per_char_paths[speaker_cleaned]}")

    return audio_duration, timeline