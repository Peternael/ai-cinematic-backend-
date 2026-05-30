import os
import requests
import time
import fal_client

FAL_API_KEY = "fc820905-8029-4431-95ea-f40ee9583ad8:9f7fac6c7325c20a10b909034f77213a"
SYNCSO_API_KEY = "sk-099_9IuRTWaFyex4Kw2Q_Q.d3J55Ad8fE5yD3VoYn-v1w4DuNjsoOYg"

os.environ["FAL_KEY"] = FAL_API_KEY

# =========================================
# UPLOAD AUDIO TO FAL STORAGE
# =========================================
def upload_to_fal_storage(file_path):
    url = fal_client.upload_file(file_path)
    print("FAL UPLOAD URL:")
    print(url)
    return url

# =========================================
# APPLY LIP SYNC (SYNC.SO) - النسخة المصلحة للـ Segments
# =========================================
def apply_lipsync(video_url, audio_url, bounding_boxes=None, timeline=None, char_list=None):

    options = {
        "sync_mode": "cut_off"
    }
    
    segments_payload = []

    if timeline and char_list:
        try:
            char_names = [c["name"].strip().lower() for c in char_list]
            
            for speaker, start, end in timeline:
                speaker_clean = speaker.strip().lower()
                if speaker_clean in char_names:
                    speaker_id = char_names.index(speaker_clean)
                    
                    # التعديل الجوهري هنا: ضفنا الـ audioInput اللي الـ API عاوزه
                    segments_payload.append({
                        "start": float(start),
                        "end": float(end),
                        "speaker_id": speaker_id,
                        "audioInput": {
                            "refId": "main_audio"  # بنربطه بـ id ملف الصوت تحت
                        }
                    })
            print(f"[LIPSYNC] SUCCESSFULLY BUILT SEGMENTS WITH AUDIO REF: {segments_payload}")
        except Exception as seg_err:
            print(f"[LIPSYNC] Error building segments, falling back to ASD: {seg_err}")
            segments_payload = []

    if not segments_payload:
        if bounding_boxes is not None:
            asd_config = {
                "auto_detect": False,
                "bounding_boxes": bounding_boxes
            }
        else:
            asd_config = {"auto_detect": True}
            
        options["active_speaker_detection"] = asd_config
        print("[LIPSYNC] USING OLD ACTIVE SPEAKER DETECTION MODE")

    # =========================================
    # CREATE JOB PAYLOAD (تعديل الـ Input IDs)
    # =========================================
    job_payload = {
        "model": "sync-3",
        "input": [
            {
                "id": "main_video",  # تعريف معرف الفيديو
                "type": "video",
                "url": video_url
            },
            {
                "id": "main_audio",  # تعريف معرف الصوت (هو ده الـ refId اللي السيرفر طالبه!)
                "type": "audio",
                "url": audio_url
            }
        ],
        "options": options
    }

    if segments_payload:
        job_payload["segments"] = segments_payload

    # =========================================
    # CREATE JOB REQUEST
    # =========================================
    create_response = requests.post(
        "https://api.sync.so/v2/generate",
        headers={
            "x-api-key": SYNCSO_API_KEY,
            "Content-Type": "application/json"
        },
        json=job_payload,
        timeout=60
    )

    create_data = create_response.json()

    print("SYNCSO CREATE RESPONSE:")
    print(create_data)

    if "id" not in create_data:
        raise Exception(
            f"Sync.so Create Error: {create_data}"
        )

    job_id = create_data["id"]

    # =========================================
    # POLL UNTIL DONE
    # =========================================
    for attempt in range(60):
        time.sleep(5)

        poll_response = requests.get(
            f"https://api.sync.so/v2/generate/{job_id}",
            headers={
                "x-api-key": SYNCSO_API_KEY
            },
            timeout=30
        )

        poll_data = poll_response.json()

        print(f"SYNCSO POLL [{attempt + 1}]:")
        print(poll_data)

        status = poll_data.get("status")

        if status == "COMPLETED":
            output_url = poll_data.get("outputUrl")
            if not output_url:
                raise Exception(
                    f"Sync.so completed but no outputUrl: {poll_data}"
                )
            return output_url

        if status == "FAILED":
            raise Exception(
                f"Sync.so job failed: {poll_data}"
            )

    raise Exception("Sync.so timed out after 5 minutes")