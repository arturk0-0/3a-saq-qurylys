import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.cli.evaluate import CASES, main
from app.core.config import Settings
from app.core.errors import AppError
from app.models.analysis import Extraction
from app.services.evaluation import evaluate_case


def extracted(*codes, quote="Внесите депозит"):
    return Extraction(
        hypotheses=[
            {"code": code, "quote": quote, "explanation": "Проверить источник"} for code in codes
        ],
        mentioned_complexes=[],
        payment_terms=[],
        uncertainty="Требуется проверка аналитиком",
    )


@pytest.mark.parametrize(
    "observed,quote,expected_status",
    [
        (["R2"], "Внесите депозит", "passed"),
        ([], "", "failed"),
        (["R2", "R3"], "Внесите депозит", "failed"),
        (["R2"], "Придуманная цитата", "failed"),
    ],
)
def test_evaluation_reports_false_negatives_positives_and_unanchored_quotes(
    tmp_path,
    observed,
    quote,
    expected_status,
):
    case = {
        "id": "check",
        "language": "ru",
        "medium": "text",
        "text": "Внесите депозит 100 тенге.",
        "expectedCodes": ["R2"],
    }
    client = SimpleNamespace(extract=Mock(return_value=extracted(*observed, quote=quote)))
    result = evaluate_case(case, client, image_directory=tmp_path)
    assert result["status"] == expected_status
    client.extract.assert_called_once_with(case["text"], None)
    assert len(result["inputSha256"]) == 64


def test_screenshot_is_sent_as_image_without_hidden_text_and_blur_is_not_auto_passed(tmp_path):
    case = json.loads(CASES.read_text())[6]
    client = SimpleNamespace(extract=Mock(return_value=extracted()))
    result = evaluate_case(case, client, image_directory=tmp_path)
    assert result["status"] == "manual_review"
    text, image = client.extract.call_args.args
    assert text == "" and image[1] == "image/png"
    assert image[0].startswith(b"\x89PNG")
    assert (tmp_path / f"{case['id']}.png").read_bytes() == image[0]


def test_cli_lists_without_calling_provider(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["evaluate", "--limit", "2"])
    client = Mock(side_effect=AssertionError("Must not initialize Gemini"))
    monkeypatch.setattr("app.cli.evaluate.GeminiClient", client)
    assert main() == 0
    assert "Запросы не выполнялись" in capsys.readouterr().out
    client.assert_not_called()


def test_missing_key_prevents_run_and_does_not_write_fake_measurements(monkeypatch, tmp_path):
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["evaluate", "--run", "--output", str(output)])
    monkeypatch.setattr("app.cli.evaluate.Settings", lambda: Settings(_env_file=None))
    assert main() == 2
    assert not output.exists()


def test_provider_failure_stops_remaining_calls_and_report_never_contains_exception(
    monkeypatch,
    tmp_path,
    capsys,
):
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["evaluate", "--run", "--output", str(output)])
    monkeypatch.setattr(
        "app.cli.evaluate.Settings",
        lambda: Settings(_env_file=None, gemini_api_key="TEST SECRET", gemini_model="test-model"),
    )
    client = SimpleNamespace(
        check_config=Mock(),
        extract=Mock(
            side_effect=AppError(429, "AI_PROVIDER_QUOTA", "TEST SECRET IN PROVIDER ERROR")
        ),
    )
    monkeypatch.setattr("app.cli.evaluate.GeminiClient", lambda _: client)
    assert main() == 1
    report = json.loads(output.read_text())
    assert report["executedCases"] == 1 and report["requestedCases"] == 7
    assert report["counts"]["error"] == 1
    client.extract.assert_called_once()
    assert "TEST SECRET" not in output.read_text() + capsys.readouterr().out


def test_bad_output_directory_is_rejected_before_paid_request(monkeypatch, tmp_path):
    parent = tmp_path / "not-a-directory"
    parent.write_text("existing file")
    monkeypatch.setattr("sys.argv", ["evaluate", "--run", "--output", str(parent / "report.json")])
    monkeypatch.setattr(
        "app.cli.evaluate.Settings",
        lambda: Settings(_env_file=None, gemini_api_key="test-key", gemini_model="test-model"),
    )
    client = SimpleNamespace(check_config=Mock(), extract=Mock())
    monkeypatch.setattr("app.cli.evaluate.GeminiClient", lambda _: client)
    assert main() == 2
    client.extract.assert_not_called()
