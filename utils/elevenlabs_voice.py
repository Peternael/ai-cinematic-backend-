import requests

ELEVEN_API_KEY = "573e73750e552b6f9bb6026eefbfb18e8e078f1a8fc4e449d29d9a9b46be5f13"

# =========================================
# GENERATE VOICE
# =========================================

def generate_voice(
    text,
    output_path
):

    url = "https://api.elevenlabs.io/v1/text-to-speech/pNInz6obpgDQGcFmaJgB"

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

    print("ELEVEN STATUS:")
    print(response.status_code)

    print("CONTENT TYPE:")
    print(response.headers.get("content-type"))

    # =========================================
    # ERROR HANDLING
    # =========================================

    if response.status_code != 200:

        raise Exception(
            f"ElevenLabs Error: {response.text}"
        )

    # مهم جدًا
    if "audio" not in response.headers.get("content-type", ""):

        raise Exception(
            f"Invalid audio response: {response.text}"
        )

    # =========================================
    # SAVE AUDIO
    # =========================================

    with open(output_path, "wb") as f:

        f.write(response.content)

    print("AUDIO SAVED")