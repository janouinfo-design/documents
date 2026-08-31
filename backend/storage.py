"""Adaptateur de stockage des fichiers.

Backend par défaut : Emergent object storage (remote).
Backend « local » : volume persistant monté (production VPS : volume Docker
nommé sur /data/storage) — jamais le disque éphémère du pod en déploiement Emergent.
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).parent / '.env')

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
STORAGE_BACKEND = (os.environ.get("STORAGE_BACKEND") or "emergent").lower()
LOCAL_STORAGE_DIR = os.environ.get("ADMIN_DOCS_STORAGE_PATH") or os.environ.get("LOCAL_STORAGE_DIR") or "/data/storage"
storage_key = None

EXT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip", "csv": "text/csv", "txt": "text/plain",
    "mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm",
}


def guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXT_MIME.get(ext, fallback)


def _local_path(path: str) -> str:
    base = os.path.abspath(LOCAL_STORAGE_DIR)
    full = os.path.abspath(os.path.join(base, path))
    if full != base and not full.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Chemin invalide")
    return full


# --- Backend « local » : volume persistant monté (prod VPS) -----------------
def _init_local():
    os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
    return "local"


def _put_local(path: str, data: bytes, content_type: str) -> dict:
    full = _local_path(path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)
    with open(full + ".meta", "w") as f:
        f.write(content_type or "application/octet-stream")
    return {"path": path, "size": len(data)}


def _get_local(path: str):
    full = _local_path(path)
    if not os.path.exists(full):
        raise FileNotFoundError(path)
    with open(full, "rb") as f:
        data = f.read()
    ctype = guess_mime(path)
    if os.path.exists(full + ".meta"):
        with open(full + ".meta") as f:
            ctype = f.read().strip() or ctype
    return data, ctype


# --- Backend « remote » : Emergent object storage (défaut) ------------------
def _init_remote():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def _put_remote(path: str, data: bytes, content_type: str) -> dict:
    key = _init_remote()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _get_remote(path: str):
    key = _init_remote()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# --- API publique : résolution du backend au moment de l'appel --------------
def _impl(op: str):
    mode = "local" if STORAGE_BACKEND == "local" else "remote"
    return globals()[f"_{op}_{mode}"]


def init_storage():
    return _impl("init")()


def put_object(path: str, data: bytes, content_type: str) -> dict:
    return _impl("put")(path, data, content_type)


def get_object(path: str):
    return _impl("get")(path)
