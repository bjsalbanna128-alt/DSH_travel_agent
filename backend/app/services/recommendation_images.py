"""Bounded, content-based validation of static recommendation covers."""

from dataclasses import dataclass
from io import BytesIO

from fastapi import HTTPException, Request
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.schemas.recommendations import ImageMime

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
IMAGE_MIMES: dict[str, ImageMime] = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@dataclass(frozen=True)
class DecodedCover:
    content: bytes
    mime: ImageMime
    width: int
    height: int


def _image_format(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    raise HTTPException(415, "封面仅支持静态 JPEG、PNG 或 WebP 图片。")


def _decode_cover(data: bytes) -> DecodedCover:
    image_format = _image_format(data)
    if image_format == "WEBP" and data[12:16] == b"VP8X" and len(data) > 20 and data[20] & 0x02:
        raise HTTPException(422, "封面须为静态图片。")
    try:
        with Image.open(BytesIO(data), formats=[image_format]) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(422, "封面尺寸须在 1,600 万像素以内。")
            if image.get_format_mimetype() == "image/apng" or getattr(image, "n_frames", 1) != 1:
                raise HTTPException(422, "封面须为静态图片。")
            image.verify()
        # verify() checks container integrity. Reopen and decode the pixels as well.
        with Image.open(BytesIO(data), formats=[image_format]) as image:
            image.load()
    except Image.DecompressionBombError as exc:
        raise HTTPException(422, "封面尺寸须在 1,600 万像素以内。") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError) as exc:
        raise HTTPException(422, "封面图片损坏或无法解码。") from exc
    return DecodedCover(data, IMAGE_MIMES[image_format], width, height)


async def read_cover_upload(request: Request) -> DecodedCover:
    length = request.headers.get("content-length")
    if length and length.isdecimal():
        digits = length.lstrip("0") or "0"
        if len(digits) > len(str(MAX_IMAGE_BYTES)) or int(digits) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "封面大小不能超过 5 MiB。")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "封面大小不能超过 5 MiB。")
        body.extend(chunk)
    if not body:
        raise HTTPException(422, "请选择封面图片。")
    return await run_in_threadpool(_decode_cover, bytes(body))
