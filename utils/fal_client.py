import requests

FAL_API_KEY = "fc820905-8029-4431-95ea-f40ee9583ad8:9f7fac6c7325c20a10b909034f77213a"

headers = {
    "Authorization": f"Key {FAL_API_KEY}",
    "Content-Type": "application/json"
}

# =========================================
# GENERATE VIDEO WITH KLING
# =========================================

def generate_video(prompt, image_url, duration="5"):

    payload = {

        "image_url": image_url,

        "prompt": prompt,

        "duration": duration,

        "mode": "std",

        # حركة خفيفة للحفاظ على الهوية
        "cfg_scale": 0.5
    }

    response = requests.post(

        "https://fal.run/fal-ai/kling-video/v2.1/standard/image-to-video",

        json=payload,

        headers=headers,

        timeout=300
    )

    data = response.json()

    print("KLING RESPONSE:")
    print(data)

    return data

# =========================================
# GENERATE AVATAR VIDEO WITH KLING
# =========================================

def generate_avatar_video(image_url, audio_url):

    payload = {

        "image_url": image_url,

        "audio_url": audio_url
    }

    response = requests.post(

        "https://fal.run/fal-ai/kling-video/ai-avatar/v2/standard",

        json=payload,

        headers=headers,

        timeout=300
    )

    data = response.json()

    print("KLING AVATAR RESPONSE:")
    print(data)

    return data

# =========================================
# GENERATE BACKGROUND WITH SDXL
# =========================================

def generate_background(prompt):

    payload = {

        "prompt": f"cinematic background scene, no people, empty environment, {prompt}",

        "negative_prompt": "people, faces, person, character, human, crowd",

        "image_size": "square_hd",

        "num_images": 1,

        "num_inference_steps": 25
    }

    response = requests.post(

        "https://fal.run/fal-ai/fast-sdxl",

        json=payload,

        headers=headers,

        timeout=120
    )

    data = response.json()

    print("BACKGROUND RESPONSE:")
    print(data)

    return data["images"][0]["url"]

# =========================================
# REMOVE BACKGROUND WITH BIREFNET
# =========================================

def remove_background(image_url):

    payload = {

        "image_url": image_url,

        "model": "Portrait",

        "output_format": "png"
    }

    response = requests.post(

        "https://fal.run/fal-ai/birefnet",

        json=payload,

        headers=headers,

        timeout=120
    )

    data = response.json()

    print("BIREFNET RESPONSE:")
    print(data)

    return data["image"]["url"]