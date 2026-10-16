"""Small, explicitly synthetic evaluation corpus; never used as application responses."""

import hashlib
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.errors import AppError
from app.services.gemini import GeminiClient


def screenshot(text: str, *, blurred: bool = False) -> bytes:
    font = None
    for name in ("DejaVuSans.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            font = ImageFont.truetype(name, size=30)
            break
        except OSError:
            continue
    if font is None:
        raise ValueError("Install DejaVu Sans or Arial; do not evaluate unreadable fallback glyphs")
    image = Image.new("RGB", (1000, 280), "white")
    ImageDraw.Draw(image).multiline_text((30, 30), text, font=font, fill="black", spacing=12)
    if blurred:
        image = image.resize((180, 50)).resize((1000, 280)).filter(ImageFilter.GaussianBlur(4))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def evaluate_case(case: dict, client: GeminiClient, *, image_directory: Path) -> dict:
    started = time.monotonic()
    result = {
        "id": case["id"],
        "language": case["language"],
        "medium": case["medium"],
        "expectedCodes": case["expectedCodes"],
        "providerAttempted": False,
    }
    try:
        image = None
        if case["medium"] != "text":
            data = screenshot(case["text"], blurred=case["medium"] == "blurred_image")
            image_directory.mkdir(parents=True, exist_ok=True)
            (image_directory / f"{case['id']}.png").write_bytes(data)
            image = (data, "image/png")
        text = case["text"] if image is None else ""
        result["inputSha256"] = hashlib.sha256(
            text.encode() + (image[0] if image else b"")
        ).hexdigest()
        result["providerAttempted"] = True
        extraction = client.extract(text, image)
        observed = sorted({item.code for item in extraction.hypotheses})
        # For these generated screenshots the original text is known. Whitespace-only OCR
        # differences are accepted here, but production screenshots still need human review.
        normalized = " ".join(case["text"].split())
        quote_checks = [
            " ".join(item.quote.split()) in normalized for item in extraction.hypotheses
        ]
        expected = case["expectedCodes"]
        result.update(
            {
                "observedCodes": observed,
                "quotesInKnownSource": all(quote_checks),
                "extraction": extraction.model_dump(mode="json", by_alias=True),
                "status": "manual_review"
                if expected is None
                else "passed"
                if observed == sorted(expected) and all(quote_checks)
                else "failed",
            }
        )
    except AppError as error:
        result.update(status="error", errorCode=error.code)
    except Exception:
        # Never serialize provider exceptions, credentials, arbitrary files or request URLs.
        result.update(status="error", errorCode="EVALUATION_FAILED")
    result["durationMs"] = round((time.monotonic() - started) * 1000)
    return result
