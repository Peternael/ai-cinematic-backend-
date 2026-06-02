import os
import fal_client

FAL_API_KEY = "fc820905-8029-4431-95ea-f40ee9583ad8:9f7fac6c7325c20a10b909034f77213a"

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
# APPLY LIP SYNC (FAL sync-lipsync v3 / sync-3)
# =========================================
# sync-3 has native multi-speaker active-speaker detection: it builds a global
# understanding of the shot and routes each distinct voice to its own face. So
# we feed the combined dialogue audio and let sync-3 split it across faces.

def apply_lipsync(video_url, audio_url, sync_mode="cut_off"):

    result = fal_client.subscribe(
        "fal-ai/sync-lipsync/v3",
        arguments={
            "video_url": video_url,
            "audio_url": audio_url,
            "sync_mode": sync_mode,
        },
        with_logs=True,
        on_queue_update=lambda u: print(f"FAL SYNC-LIPSYNC v3: {u}"),
    )

    print("FAL SYNC-LIPSYNC v3 RESULT:")
    print(result)

    return result["video"]["url"]
