import hashlib
import io
import logging
import warnings
from typing import Protocol
from uuid import uuid4

from google.api_core.exceptions import GoogleAPICallError
from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError, Conflict, IntegrationUnavailable
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.entities import Advertisement, Evidence
from app.services.workspace import WorkspaceService, audit_event, serialize

MAX_UPLOAD = 6 * 1024 * 1024
MEDIA = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
logger = logging.getLogger(__name__)


def validate_image(data: bytes, media_type: str) -> None:
    if not data or len(data) > MAX_UPLOAD:
        raise AppError(413, "FILE_SIZE", "Image must be between 1 byte and 6 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if MEDIA.get(image.format) != media_type or image.width * image.height > 20_000_000:
                    raise ValueError("Invalid format or dimensions")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not accepted")
                image.verify()
            # JPEG/WebP verify() does not decode pixels. Reject truncated/corrupt data
            # before storing it or paying for an AI request; keep the original bytes.
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AppError(
            422, "INVALID_IMAGE", "Use a valid static JPEG, PNG or WebP up to 20 megapixels"
        ) from None


class FileStorage(Protocol):
    def put(self, path: str, data: bytes, media_type: str) -> None: ...
    def get(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class FirebaseFileStorage:
    def __init__(self, runtime):
        self.runtime = runtime

    def put(self, path: str, data: bytes, media_type: str) -> None:
        try:
            self.runtime.bucket().blob(path).upload_from_string(
                data, content_type=media_type, if_generation_match=0, timeout=30
            )
        except GoogleAPICallError:
            raise IntegrationUnavailable("Storage upload") from None

    def get(self, path: str) -> bytes:
        try:
            # Range bounds allocation even if an object was replaced outside the app.
            return (
                self.runtime.bucket()
                .blob(path)
                .download_as_bytes(start=0, end=MAX_UPLOAD, timeout=30)
            )
        except GoogleAPICallError:
            raise IntegrationUnavailable("Storage download") from None

    def delete(self, path: str) -> None:
        try:
            self.runtime.bucket().blob(path).delete(timeout=10)
        except Exception:
            logger.error("Orphan upload cleanup failed; inspect private evidence objects")


class FileService:
    def __init__(self, workspace: WorkspaceService, storage: FileStorage):
        self.workspace = workspace
        self.storage = storage

    def upload(
        self, ad_id: str, version: int, data: bytes, media_type: str, user: Principal
    ) -> Evidence:
        validate_image(data, media_type)
        ad = Advertisement.model_validate(self.workspace.require_record("advertisements", ad_id))
        if ad.version != version or len(ad.attachment_ids) >= 10:
            raise Conflict("Advertisement changed or attachment limit reached")
        evidence_id = uuid4().hex
        path = f"evidence/{ad.complex_id}/{evidence_id}"
        item = Evidence(
            id=evidence_id,
            complex_id=ad.complex_id,
            advertisement_id=ad.id,
            type="screenshot",
            source_url=ad.source_url,
            excerpt="Скриншот: содержание требует проверки аналитиком.",
            captured_at=utc_now(),
            storage_path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            media_type=media_type,
            size_bytes=len(data),
            demo=ad.demo,
        )
        self.storage.put(path, data, media_type)

        def operation(tx):
            current = Advertisement.model_validate(
                self.workspace.require_record("advertisements", ad_id, tx)
            )
            complex_ = self.workspace.complex(ad.complex_id, tx)
            if current.version != version:
                raise Conflict()
            current.attachment_ids.append(item.id)
            current.version += 1
            event = audit_event(
                user, "evidence", item.id, "screenshot.upload", complex_, {"sha256": item.sha256}
            )
            tx.create("evidence", item.id, serialize(item))
            tx.set("advertisements", ad_id, serialize(current))
            tx.create("auditLogs", event.id, serialize(event))
            return item

        try:
            return self.workspace.store.atomic(operation)
        except Exception:
            # Do not delete after an uncertain Firestore commit: an object could already be
            # referenced. Unreferenced private objects may be cleaned by an administrator.
            logger.warning("Upload transaction failed; inspect unreferenced private objects")
            raise

    def download(self, evidence_id: str) -> tuple[bytes, str]:
        item = Evidence.model_validate(self.workspace.require_record("evidence", evidence_id))
        if not item.storage_path or not item.media_type:
            raise AppError(404, "NO_FILE", "Evidence has no uploaded image")
        data = self.storage.get(item.storage_path)
        if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
            raise AppError(502, "FILE_INTEGRITY", "Stored file failed integrity verification")
        return data, item.media_type
