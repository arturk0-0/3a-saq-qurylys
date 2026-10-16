"""Storage SDK failures are simulated explicitly; never connect to a bucket."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import RetryError, ServiceUnavailable

from app.core.errors import AppError
from app.services.files import FirebaseFileStorage


@pytest.mark.parametrize(
    "operation,method", [("put", "upload_from_string"), ("get", "download_as_bytes")]
)
def test_storage_retry_deadline_is_safe_unavailable(operation, method, caplog):
    blob = Mock()
    failure = RetryError("PRIVATE_STORAGE_DETAIL", ServiceUnavailable("PRIVATE_CAUSE"))
    getattr(blob, method).side_effect = failure
    bucket = Mock()
    bucket.blob.return_value = blob
    storage = FirebaseFileStorage(SimpleNamespace(bucket=lambda: bucket))
    with pytest.raises(AppError) as error:
        if operation == "put":
            storage.put("evidence/test/image", b"test bytes", "image/png")
        else:
            storage.get("evidence/test/image")
    assert (error.value.status_code, error.value.code) == (503, "INTEGRATION_UNAVAILABLE")
    assert "PRIVATE" not in caplog.text + error.value.message
    assert getattr(blob, method).call_count == 1
    blob.delete.assert_not_called()
