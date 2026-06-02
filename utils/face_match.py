import os

# =========================================
# SSL FIX FOR INSIGHTFACE MODEL DOWNLOAD
# =========================================
# insightface fetches the buffalo_l model from GitHub releases on first run.
# In some Windows/Python setups requests can't verify the cert ("unable to get
# local issuer certificate"). Point Python at certifi's CA bundle before the
# insightface import so the one-time download succeeds.
import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import numpy as np
import cv2
from insightface.app import FaceAnalysis

# =========================================
# FACE DETECTION + IDENTITY MATCHING
# =========================================
# Locates each reference person inside the generated (merged) video and returns
# a single padded crop rectangle per character. Each rectangle isolates ONE face
# so it can be lip-synced unambiguously (deterministically) on fal.
# First run downloads the buffalo_l model (~300MB).

_app = None


def _get_app():
    """Lazily initialise the InsightFace model (CPU)."""
    global _app
    if _app is None:
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _app = app
    return _app


def _read_reference_face(image_path):
    """Return the ArcFace embedding of the largest face in a reference photo."""
    img = cv2.imread(image_path)
    if img is None:
        raise Exception(f"Could not read reference image: {image_path}")

    faces = _get_app().get(img)
    if not faces:
        raise Exception(f"No face detected in reference image: {image_path}")

    faces.sort(
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        reverse=True,
    )
    return faces[0].normed_embedding


def _even(v):
    """Round to an even integer (codec-friendly dimensions)."""
    v = int(round(v))
    return v - (v % 2)


def get_face_crops(video_path, reference_image_paths, pad=0.35, sample_every=10):
    """
    Detect each reference person in the video and return one padded crop
    rectangle (x1, y1, x2, y2) per reference, aligned to reference_image_paths
    order. Each rectangle is the union of that person's detected face boxes
    across sampled frames, padded and clamped to the frame.
    """
    app = _get_app()

    ref_embeddings = [_read_reference_face(p) for p in reference_image_paths]
    n = len(ref_embeddings)

    # accumulated union box per reference: [min_x1, min_y1, max_x2, max_y2]
    unions = [None] * n
    hit_counts = [0] * n

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Could not open video: {video_path}")

    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frame_idx = 0
    sampled = 0

    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        if frame_idx % sample_every == 0:
            sampled += 1
            faces = app.get(frame_bgr)

            if faces:
                used = set()
                for ref_idx, ref_emb in enumerate(ref_embeddings):
                    best_f, best_score = -1, -1.0
                    for f_idx, face in enumerate(faces):
                        if f_idx in used:
                            continue
                        score = float(np.dot(ref_emb, face.normed_embedding))
                        if score > best_score:
                            best_score, best_f = score, f_idx

                    if best_f == -1:
                        continue

                    used.add(best_f)
                    hit_counts[ref_idx] += 1
                    x1, y1, x2, y2 = faces[best_f].bbox[:4]

                    if unions[ref_idx] is None:
                        unions[ref_idx] = [x1, y1, x2, y2]
                    else:
                        u = unions[ref_idx]
                        u[0] = min(u[0], x1)
                        u[1] = min(u[1], y1)
                        u[2] = max(u[2], x2)
                        u[3] = max(u[3], y2)

        frame_idx += 1

    cap.release()

    print(f"[FACE_MATCH] sampled {sampled} frame(s); frame size {W}x{H}")

    rects = []
    for ref_idx in range(n):
        if unions[ref_idx] is None:
            raise Exception(
                f"Reference #{ref_idx} ({reference_image_paths[ref_idx]}) was "
                f"never matched to a face in the video."
            )

        x1, y1, x2, y2 = unions[ref_idx]
        bw, bh = (x2 - x1), (y2 - y1)
        px, py = bw * pad, bh * pad

        cx1 = max(0, x1 - px)
        cy1 = max(0, y1 - py)
        cx2 = min(W, x2 + px)
        cy2 = min(H, y2 + py)

        rx1 = _even(cx1)
        ry1 = _even(cy1)
        rx2 = _even(cx2)
        ry2 = _even(cy2)

        rects.append((rx1, ry1, rx2, ry2))

        print(
            f"[FACE_MATCH] ref #{ref_idx} ({reference_image_paths[ref_idx]}) "
            f"hits={hit_counts[ref_idx]} crop=({rx1},{ry1},{rx2},{ry2})"
        )

    # warn on overlap (paste order will then matter)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rects[i], rects[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                print(f"[FACE_MATCH] WARNING: crop rects {i} and {j} overlap")

    return rects
