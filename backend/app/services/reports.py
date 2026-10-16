import logging
from html import escape
from threading import BoundedSemaphore

from app.core.errors import AppError, IntegrationUnavailable
from app.core.images import IMAGE_DECODER_LOCK
from app.models.signals import Signal

PDF_SLOTS = BoundedSemaphore(2)
logger = logging.getLogger(__name__)
STATUSES = {
    "draft": "Черновик",
    "pending_review": "На проверке",
    "confirmed": "Подтверждён аналитиком",
    "returned": "Возвращён",
}
FACTOR_LABELS = {
    "R1": "Отсутствие применимого правового основания",
    "R2": "Предложение внести платёж",
    "R3": "Реклама строящегося жилья",
    "R4": "Коллективная жалоба",
    "R5": "Разрыв готовности ≥20 п.п.",
    "R6": "Остановка или задержка работ",
}

VERIFICATION_LABELS = {
    "unknown": "Нет подтверждения",
    "proposed": "Требует проверки",
    "confirmed": "Подтверждено",
    "rejected": "Отклонено",
}
EVIDENCE_LABELS = {
    "advertisement": "Текст объявления",
    "screenshot": "Скриншот объявления",
    "legal_basis_review": "Проверка правового основания",
    "complaint": "Жалоба",
    "progress_report": "Отчёт о готовности",
    "work_status": "Сведения о ходе работ",
    "document": "Документ",
}
BASIS_LABELS = {
    "guarantee": "Гарантия КЖК",
    "regional_permit": "Разрешение МИО",
    "other_applicable": "Иное применимое основание",
    "unknown": "Основание не установлено",
}
ZONE_LABELS = {
    "GREEN": "Низкий приоритет",
    "YELLOW": "Требует проверки",
    "RED": "Высокий приоритет",
}


def report_html(signal: Signal) -> str:
    s = signal.snapshot

    def esc(value):
        return escape(str(value if value is not None else "—"))

    rows = "".join(
        f"<tr><td>{f.code}: {FACTOR_LABELS[f.code]}</td>"
        f"<td>{esc(VERIFICATION_LABELS.get(f.status, f.status))}</td>"
        f"<td>{f.points}</td><td>{esc(', '.join(f.evidence_ids))}</td></tr>"
        for f in s.risk.factors
    )

    def evidence_html(e):
        if e.source_reference.startswith("AI hypothesis; "):
            reference = (
                "<p class='provenance'><strong>Историческая запись AI до проверки:</strong> "
                f"{esc(e.source_reference)}<br>Пометка unverified относится к моменту создания "
                "AI-гипотезы. Последующая проверка аналитика указана ниже и сохранена "
                "в этом снимке.</p>"
            )
        else:
            reference = f"<p>Реквизиты источника: {esc(e.source_reference)}</p>"
        return (
            f"<section><h3>Источник {esc(e.id)}</h3>"
            f"<p>{esc(EVIDENCE_LABELS.get(e.type, e.type))} · {esc(e.source_url)}</p>"
            f"{reference}<blockquote>{esc(e.excerpt)}"
            f"{' [выдержка сокращена]' if e.excerpt_truncated else ''}</blockquote>"
            f"<p><strong>Источник проверен аналитиком · версия {e.version}</strong>"
            f"<br>Фиксация: {esc(e.captured_at.isoformat())}"
            f"<br>Проверил источник: {esc(e.reviewer)}, {esc(e.reviewed_at.isoformat())}"
            f"<br>SHA-256: {esc(e.sha256)}</p></section>"
        )

    evidence = "".join(evidence_html(item) for item in s.evidence)
    decisions = "".join(
        f"<li>{esc(f.code)}: {esc(f.reviewer)}, {esc(f.reviewed_at)} — {esc(f.notes)}</li>"
        for f in s.complex.factors
        if f.status == "confirmed"
    )
    review = (
        f"Проверил сигнал: {esc(signal.reviewer)}, {esc(signal.reviewed_at.isoformat())}"
        if signal.reviewer and signal.reviewed_at
        else "Решение по сигналу ещё не принято."
    )
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>SAQ QURYLYS — сигнал</title>
<style>@page {{ size: A4; margin: 18mm;
@bottom-center {{ content: 'SAQ QURYLYS · DEMO · ' counter(page); }} }}
body {{ font: 10pt 'DejaVu Sans', sans-serif; color: #163539;
line-height: 1.5; overflow-wrap: anywhere; }}
h1 {{ font-size: 20pt; }} h2 {{ font-size: 14pt; }}
table {{ border-collapse: collapse; width:100%; table-layout: fixed; }}
td, th {{ border: 1px solid #b4c9c8; padding: 6px; }} th {{ background: #e8f1ef; }}
blockquote {{ border-left: 3px solid #b4c9c8; padding-left:12px; white-space: pre-wrap; }}
.demo {{ border: 2px solid #9e670c; padding: 10px; font-weight:bold; }}
section {{ margin-top: 18px; }}
h1, h2, h3 {{ break-after: avoid; }} tr {{ break-inside: avoid; }}
p, blockquote {{ orphans: 3; widows: 3; }}
.provenance {{ padding: 8px; border: 1px solid #b4c9c8; background: #f1f6f3; }}
th:nth-child(1) {{ width: 38%; }} th:nth-child(2) {{ width: 18%; }}
th:nth-child(3) {{ width: 10%; }} th:nth-child(4) {{ width: 34%; }}
</style><body><p class="demo">DEMO — вымышленные данные.
Не является выводом о незаконности.</p>
<h1>{esc(signal.title)}</h1><p>Сигнал {esc(signal.id)} · версия {signal.version}
<br>Статус: {STATUSES[signal.status]}</p>
<h2>{esc(s.complex.name)}</h2><p>{esc(s.complex.city)}, {esc(s.complex.address)}
<br>Застройщик: {esc(s.developer.name)} · вымышленный БИН {esc(s.developer.bin)}</p>
<p>Причина: {esc(signal.reason)}</p>
<h2>Приоритет проверки: {s.risk.score} / 100 · {s.risk.zone} — {ZONE_LABELS[s.risk.zone]}</h2>
<p>Снимок версии ЖК {s.complex.version}, зафиксирован {esc(s.captured_at.isoformat())}.
Последующие изменения карточки сюда не включены. Гипотезы AI не дают баллов.</p>
<table><thead><tr><th>Фактор</th><th>Статус</th><th>Баллы</th><th>Источники</th></tr>
</thead><tbody>{rows}</tbody></table>
<h2>Правовое основание</h2><p>{esc(BASIS_LABELS[s.complex.legal_basis.type])} ·
{esc(VERIFICATION_LABELS[s.complex.legal_basis.status])}<br>{esc(s.complex.legal_basis.reference)}
<br>{esc(s.complex.legal_basis.source)}</p>
<h2>Решения по факторам</h2><ul>{decisions}</ul>
<h2>Проверенные источники</h2>{evidence or "<p>Нет подтверждённых источников.</p>"}
<h2>Решение по сигналу</h2><p>Создал: {esc(signal.created_by)},
{esc(signal.created_at.isoformat())}<br>{review}<br>Обоснование: {esc(signal.review_notes)}</p>
<p>Инструмент поддержки аналитика. Сигнал не отправляется в органы автоматически.
Неизвестное правовое основание не означает его отсутствие.
Все даты содержат часовой пояс.</p></body></html>"""


def deny_resource(url, *args, **kwargs):
    raise ValueError("External and local resources are forbidden in reports")


def render_pdf(signal: Signal) -> bytes:
    if not PDF_SLOTS.acquire(blocking=False):
        raise AppError(429, "PDF_BUSY", "PDF renderer is busy; try later")
    try:
        try:
            # Its first import changes a global Pillow option. Do not race the
            # strict decoder used to validate uploaded evidence in another thread.
            with IMAGE_DECODER_LOCK:
                from weasyprint import HTML
        except (ImportError, OSError):
            raise IntegrationUnavailable("PDF system libraries") from None
        try:
            return HTML(string=report_html(signal), url_fetcher=deny_resource).write_pdf()
        except (OSError, RuntimeError) as exc:
            logger.error("PDF render failed: exception_type=%s", type(exc).__name__)
            raise AppError(
                503, "PDF_RENDER_FAILED", "PDF renderer is unavailable; try later"
            ) from None
    finally:
        PDF_SLOTS.release()
