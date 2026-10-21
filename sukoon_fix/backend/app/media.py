"""Sukoon — tiny helper for the base64 data-URL photo uploads used by patient
contacts (the "family tree"). There is no separate file-storage service in
this prototype, and an uploaded file saved to local disk would be wiped on
every restart of an ephemeral hosting environment anyway — so photos are
stored inline as data: URLs in the same (persistent) database row instead.
Kept small on purpose: this is a profile-photo thumbnail, not a media library.
"""
from fastapi import HTTPException

MAX_PHOTO_DATA_URL_CHARS = 2_400_000  # ~1.8MB of actual image bytes once base64-decoded


def validate_photo_data_url(data_url):
    if not data_url:
        return data_url
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image (data URL)")
    if len(data_url) > MAX_PHOTO_DATA_URL_CHARS:
        raise HTTPException(status_code=400, detail="Photo is too large — please use a smaller image (under ~1.5MB)")
    return data_url
