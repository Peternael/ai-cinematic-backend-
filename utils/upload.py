import requests
import base64

IMGBB_API_KEY = "3e86926e7b57406c8833bb653c4af1a1"

def upload_to_imgbb(image_path):

    with open(image_path, "rb") as file:

        encoded = base64.b64encode(
            file.read()
        ).decode("utf-8")

    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": IMGBB_API_KEY,
            "image": encoded
        }
    )

    data = response.json()

    print(data)

    if "data" not in data:

        raise Exception(
            f"ImgBB Error: {data}"
        )

    return data["data"]["url"]