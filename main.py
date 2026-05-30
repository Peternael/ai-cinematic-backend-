from fastapi import FastAPI
from fastapi import UploadFile, File, Form
from fastapi.responses import JSONResponse

import json
import uuid
import os
import requests
import time
import numpy as np
from typing import List

from PIL import Image
from moviepy import VideoFileClip, AudioFileClip, VideoClip, ImageClip, concatenate_videoclips

from utils.upload import upload_to_imgbb
from utils.fal_client import generate_avatar_video, generate_background, remove_background, generate_video
from utils.nano_banana import merge_characters_pro
from utils.dialogue_voice import generate_dialogue
from utils.lipsync import upload_to_fal_storage, apply_lipsync

app = FastAPI()

# =========================================
# CREATE FOLDERS
# =========================================

os.makedirs("temp", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# =========================================
# HELPERS
# =========================================

def make_green_portrait(transparent_path, output_path):
    char = Image.open(transparent_path).convert("RGBA")
    green_bg = Image.new("RGB", char.size, (0, 255, 0))
    green_bg.paste(char, mask=char.split()[3])
    green_bg.save(output_path, "JPEG", quality=95)


def apply_chroma_key(frame_rgb, tolerance=60):
    r = frame_rgb[:, :, 0].astype(int)
    g = frame_rgb[:, :, 1].astype(int)
    b = frame_rgb[:, :, 2].astype(int)
    is_green = (g - r > tolerance) & (g - b > tolerance) & (g > 100)
    alpha = np.where(is_green, 0, 255).astype(np.uint8)
    return np.dstack([frame_rgb, alpha])


def composite_scene(bg_path, clip_paths, audio_path, output_path):

    scene_size = (1024, 1024)

    bg_image = Image.open(bg_path).convert("RGB").resize(scene_size)

    clips = [VideoFileClip(p) for p in clip_paths]

    duration = min(c.duration for c in clips)

    char_h = int(scene_size[1] * 0.78)

    n = len(clips)

    positions_x = [int(scene_size[0] * (i + 1) / (n + 1)) for i in range(n)]

    def make_frame(t):

        scene = bg_image.copy().convert("RGBA")

        for clip, cx in zip(clips, positions_x):

            t_clamped = min(t, clip.duration - 0.001)

            frame = clip.get_frame(t_clamped)

            rgba = apply_chroma_key(frame)

            img = Image.fromarray(rgba, "RGBA")

            ratio = char_h / img.height

            img = img.resize((int(img.width * ratio), char_h), Image.LANCZOS)

            x = cx - img.width // 2
            y = scene_size[1] - char_h

            scene.paste(img, (x, y), img)

        return np.array(scene.convert("RGB"))

    fps = clips[0].fps or 25

    final = VideoClip(make_frame, duration=duration)

    audio = AudioFileClip(audio_path)

    final = final.with_audio(audio)

    final.write_videofile(output_path, fps=fps, codec="libx264", audio_codec="aac")

    for c in clips:
        c.close()

# =========================================
# PING-PONG LOOP VIDEO TO TARGET DURATION
# =========================================

def loop_video_pingpong(input_path, target_duration, output_path):

    probe = VideoFileClip(input_path)
    base_duration = probe.duration
    probe.close()

    print(f"BASE CLIP DURATION: {base_duration} sec")
    print(f"TARGET DURATION: {target_duration} sec")

    if target_duration <= base_duration:

        clip = VideoFileClip(input_path).subclipped(0, target_duration)
        clip.write_videofile(output_path, codec="libx264", audio=False)
        clip.close()
        return

    parts = []
    accumulated = 0.0
    forward = True

    while accumulated < target_duration:

        clip = VideoFileClip(input_path)

        if not forward:
            # Reverse playback via time remap
            clip = clip.time_transform(
                lambda t, d=base_duration: d - t,
                keep_duration=True
            )

        parts.append(clip)
        accumulated += base_duration
        forward = not forward

    looped = concatenate_videoclips(parts).subclipped(0, target_duration)

    looped.write_videofile(output_path, codec="libx264", audio=False)

    looped.close()

    for p in parts:
        p.close()

# =========================================
# BUILD STATIC VIDEO FROM IMAGE
# =========================================

def build_static_video(image_path, duration, output_path, fps=25):

    clip = ImageClip(image_path).with_duration(duration)
    clip.write_videofile(output_path, fps=fps, codec="libx264", audio=False)
    clip.close()

# =========================================
# GENERATE VIDEO
# =========================================

@app.post("/generate-video")
async def generate_video_api(

    images: List[UploadFile] = File(...),

    characters: str = Form(...),

    prompt: str = Form(...),

    dialogue: str = Form(...)

):

    start_time = time.time()

    try:

        print("\n====================")
        print("START AVATAR VIDEO GENERATION")
        print("====================")

        request_id = str(uuid.uuid4())

        # =========================================
        # PARSE CHARACTERS
        # =========================================

        char_list = json.loads(characters)

        print(f"CHARACTERS: {[c['name'] for c in char_list]}")

        voice_map = {c["name"]: c["voice_id"] for c in char_list}

        # =========================================
        # STEP 1 — SAVE + UPLOAD IMAGES
        # =========================================

        print("STEP 1 -> SAVE + UPLOAD IMAGES")

        image_urls = []

        for i, (img_file, char) in enumerate(zip(images, char_list)):

            image_path = f"temp/{request_id}_{i}.jpg"

            with open(image_path, "wb") as f:
                f.write(await img_file.read())

            image_url = upload_to_imgbb(image_path)

            print(f"IMAGE URL [{char['name']}]: {image_url}")

            image_urls.append(image_url)

        # =========================================
        # STEP 1B — REMOVE BACKGROUNDS
        # =========================================

        print("STEP 1B -> REMOVE BACKGROUNDS")

        transparent_paths = []

        for i in range(len(char_list)):

            t_url = remove_background(image_urls[i])

            t_path = f"temp/{request_id}_{i}_nobg.png"

            with open(t_path, "wb") as f:
                f.write(requests.get(t_url, timeout=120).content)

            transparent_paths.append(t_path)

            print(f"TRANSPARENT SAVED [{char_list[i]['name']}]: {t_path}")

        # =========================================
        # STEP 1C — GREEN SCREEN PORTRAITS
        # =========================================

        print("STEP 1C -> GREEN PORTRAITS")

        green_image_urls = []

        for i, char in enumerate(char_list):

            g_path = f"temp/{request_id}_{i}_green.jpg"

            make_green_portrait(transparent_paths[i], g_path)

            g_url = upload_to_imgbb(g_path)

            green_image_urls.append(g_url)

            print(f"GREEN PORTRAIT [{char['name']}]: {g_url}")

        # =========================================
        # STEP 1D — GENERATE SHARED BACKGROUND
        # =========================================

        print("STEP 1D -> GENERATE SHARED BACKGROUND")

        bg_url = generate_background(prompt)

        bg_path = f"temp/{request_id}_bg.jpg"

        with open(bg_path, "wb") as f:
            f.write(requests.get(bg_url, timeout=120).content)

        print(f"BACKGROUND SAVED: {bg_path}")

        # =========================================
        # STEP 2 — GENERATE DIALOGUE AUDIO
        # =========================================

        print("STEP 2 -> GENERATE DIALOGUE AUDIO")

        audio_path = f"outputs/{request_id}.mp3"

        per_char_paths = {
            c["name"]: f"outputs/{request_id}_{i}.mp3"
            for i, c in enumerate(char_list)
        }

        audio_duration, _ = generate_dialogue(
            dialogue,
            audio_path,
            voice_map,
            per_char_paths
        )

        print("DIALOGUE GENERATED")

        # =========================================
        # CHECK AUDIO EXISTS
        # =========================================

        if not os.path.exists(audio_path):

            return JSONResponse({
                "success": False,
                "error": "Audio file not found"
            })

        audio_size = os.path.getsize(audio_path)

        print(f"AUDIO SIZE: {audio_size}")

        if audio_size < 1000:

            return JSONResponse({
                "success": False,
                "error": "Generated audio is invalid"
            })

        # =========================================
        # STEP 3 — AVATAR V2 PER CHARACTER
        # =========================================

        print("STEP 3 -> AVATAR V2 PER CHARACTER")

        avatar_video_paths = []

        for i, char in enumerate(char_list):

            char_name = char["name"]

            print(f"PROCESSING CHARACTER: {char_name}")

            fal_url = upload_to_fal_storage(per_char_paths[char_name])

            print(f"FAL AUDIO URL [{char_name}]: {fal_url}")

            avatar_resp = generate_avatar_video(green_image_urls[i], fal_url)

            if "video" not in avatar_resp:

                return JSONResponse({
                    "success": False,
                    "error": f"Kling Avatar error for {char_name}: {avatar_resp}"
                })

            video_url = avatar_resp["video"]["url"]

            print(f"AVATAR VIDEO URL [{char_name}]: {video_url}")

            video_path = f"outputs/{request_id}_{i}.mp4"

            with open(video_path, "wb") as f:
                f.write(requests.get(video_url, timeout=300).content)

            print(f"VIDEO SAVED [{char_name}]: {video_path}")

            avatar_video_paths.append(video_path)

        # =========================================
        # STEP 4 — COMPOSITE INTO NATURAL SCENE
        # =========================================

        print("STEP 4 -> COMPOSITE SCENE")

        final_video_path = f"outputs/{request_id}_final.mp4"

        composite_scene(bg_path, avatar_video_paths, audio_path, final_video_path)

        print("COMPOSITE DONE")

        # =========================================
        # TOTAL TIME
        # =========================================

        total_time = round(time.time() - start_time, 2)

        print(f"TOTAL TIME: {total_time} sec")

        # =========================================
        # FINAL RESPONSE
        # =========================================

        return JSONResponse({

            "success": True,

            "status": "COMPLETED",

            "video_path": final_video_path,

            "audio_path": audio_path,

            "time_taken": total_time

        })

    except Exception as e:

        print("ERROR:")
        print(str(e))

        return JSONResponse({

            "success": False,

            "error": str(e)

        })

# =========================================
# GENERATE VIDEO V2
# nano-banana-pro -> kling -> sync.so lipsync (sync-3)
# =========================================

@app.post("/generate-video-v2")
async def generate_video_v2_api(

    images: List[UploadFile] = File(...),

    characters: str = Form(...),

    prompt: str = Form(...),

    dialogue: str = Form(...)

):

    start_time = time.time()

    try:

        print("\n====================")
        print("START V2 PIPELINE")
        print("====================")

        request_id = str(uuid.uuid4())

        # =========================================
        # PARSE CHARACTERS
        # =========================================

        char_list = json.loads(characters)

        print(f"CHARACTERS: {[c['name'] for c in char_list]}")

        voice_map = {c["name"]: c["voice_id"] for c in char_list}

        # =========================================
        # STEP 1 - SAVE + UPLOAD IMAGES
        # =========================================

        print("STEP 1 -> SAVE + UPLOAD IMAGES")

        image_urls = []

        for i, img_file in enumerate(images):

            image_path = f"temp/{request_id}_{i}.jpg"

            with open(image_path, "wb") as f:
                f.write(await img_file.read())

            url = upload_to_imgbb(image_path)

            print(f"IMAGE URL [{i}]: {url}")

            image_urls.append(url)

        # =========================================
        # STEP 2 - MERGE WITH NANO BANANA PRO
        # =========================================

        print("STEP 2 -> MERGE COMPOSITE (NANO BANANA PRO)")

        composite_url = merge_characters_pro(image_urls, prompt, char_list)

        print(f"COMPOSITE URL: {composite_url}")

        # =========================================
        # STEP 3 - ANIMATE WITH KLING
        # =========================================

        print("STEP 3 -> ANIMATE WITH KLING")

        kling_resp = generate_video(prompt, composite_url, duration="10")

        if "video" not in kling_resp:

            return JSONResponse({
                "success": False,
                "error": f"Kling error: {kling_resp}"
            })

        base_video_url = kling_resp["video"]["url"]

        base_video_path = f"outputs/{request_id}_base.mp4"

        with open(base_video_path, "wb") as f:
            f.write(requests.get(base_video_url, timeout=300).content)

        print(f"BASE VIDEO SAVED: {base_video_path}")

        # =========================================
        # STEP 4 - GENERATE DIALOGUE AUDIO
        # =========================================

        print("STEP 4 -> GENERATE DIALOGUE AUDIO")

        audio_path = f"outputs/{request_id}.mp3"

        print("CHAR_LIST:")
        print(char_list)

        print("VOICE_MAP:")
        print(voice_map)

        print("DIALOGUE:")
        print(dialogue)

        audio_duration, timeline = generate_dialogue(
            dialogue,
            audio_path,
            voice_map
        )

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:

            return JSONResponse({
                "success": False,
                "error": "Generated audio is invalid"
            })

        print(f"AUDIO DURATION: {audio_duration} sec")

        # =========================================
        # STEP 5 - LIP-SYNC VIA SYNC.SO
        # =========================================

        print("STEP 5 -> LIP-SYNC (sync.so)")

        video_fal_url = upload_to_fal_storage(base_video_path)
        audio_fal_url = upload_to_fal_storage(audio_path)

        final_url = apply_lipsync(
        video_fal_url,
        audio_fal_url,
        timeline=timeline,
        char_list=char_list
)

        final_video_path = f"outputs/{request_id}_final.mp4"

        with open(final_video_path, "wb") as f:
            f.write(requests.get(final_url, timeout=300).content)

        print(f"FINAL VIDEO SAVED: {final_video_path}")

        # =========================================
        # TOTAL TIME
        # =========================================

        total_time = round(time.time() - start_time, 2)

        print(f"TOTAL TIME: {total_time} sec")

        # =========================================
        # FINAL RESPONSE
        # =========================================

        return JSONResponse({

        "success": True,

        "status": "COMPLETED",

        "video_url": final_url,

        "video_path": final_video_path,

        "audio_path": audio_path,

        "time_taken": total_time

        })

    except Exception as e:

        print("ERROR:")
        print(str(e))

        return JSONResponse({

            "success": False,

            "error": str(e)

        })
