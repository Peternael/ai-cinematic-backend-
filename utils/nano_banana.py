import requests

FAL_API_KEY = "fc820905-8029-4431-95ea-f40ee9583ad8:9f7fac6c7325c20a10b909034f77213a"

headers = {
    "Authorization": f"Key {FAL_API_KEY}",
    "Content-Type": "application/json"
}

# =========================================
# GENERATE IDENTITY SCENE
# =========================================

def generate_identity_scene(
    image1_url,
    image2_url
):

    prompt = """
Create a realistic cinematic image of these exact two Arab male friends sitting together on Cairo Nile Corniche at night.

Preserve exact facial identity,
hairstyle,
skin tone,
facial structure,
and appearance from the uploaded reference photos.

The two people should look exactly like the real persons in the reference images.

Ultra realistic cinematic lighting.
Natural sitting pose.
Emotional atmosphere.
Film look.
Highly detailed skin texture.
"""

    payload = {

        "prompt": prompt,

        "image_urls": [
            image1_url,
            image2_url
        ]
    }

    response = requests.post(

        "https://fal.run/fal-ai/nano-banana",

        json=payload,

        headers=headers,

        timeout=300
    )

    data = response.json()

    print("NANO BANANA RESPONSE:")
    print(data)

    if "images" not in data:

        raise Exception(
            f"Nano Banana Error: {data}"
        )

    return data["images"][0]["url"]

# =========================================
# MERGE CHARACTERS (NANO BANANA PRO)
# =========================================

def merge_characters_pro(image_urls, prompt, characters=None):

    n = len(image_urls)

    if characters:
        people_clause = "The people are: " + ", ".join(
            f"{c['name']} ({c.get('gender', 'person')})" for c in characters
        ) + "."
    else:
        people_clause = ""

    identity_prompt = f"""
Create a realistic cinematic image featuring the {n} people from the uploaded reference photos together in the scene below.

{people_clause}

PRESERVE exact facial identity, hairstyle, skin tone, facial structure, and overall appearance of EACH person from their reference photo.
Each person in the output MUST look exactly like the corresponding real person in the reference images — same face, same features, same identity.
Do not invent or generate new or different faces. Do not change ages, ethnicities, or distinctive features.

Scene: {prompt}

Ultra realistic cinematic lighting.
Natural poses.
Emotional atmosphere.
Film look.
Highly detailed skin texture.
"""

    payload = {

        "prompt": identity_prompt,

        "image_urls": image_urls
    }

    response = requests.post(

        "https://fal.run/fal-ai/nano-banana-pro/edit",

        json=payload,

        headers=headers,

        timeout=300
    )

    data = response.json()

    print("NANO BANANA PRO RESPONSE:")
    print(data)

    if "images" not in data:

        raise Exception(
            f"Nano Banana Pro Error: {data}"
        )

    return data["images"][0]["url"]