from html import escape
from threading import BoundedSemaphore

from app.core.errors import AppError, IntegrationUnavailable
from app.models.signals import Signal

PDF_SLOTS = BoundedSemaphore(2)
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


def report_html(signal: Signal) -> str:
    s = signal.snapshot

    def esc(value):
        return escape(str(value if value is not None else "—"))

    rows = "".join(
        f"<tr><td>{f.code}: {FACTOR_LABELS[f.code]}</td><td>{esc(f.status)}</td>"
        f"<td>{f.points}</td><td>{esc(', '.join(f.evidence_ids))}</td></tr>"
        for f in s.risk.factors
    )
    evidence = "".join(
        f"<section><h3>Источник {esc(e.id)}</h3><p>{esc(e.type)} · {esc(e.source_url)}"
        f"<br>{esc(e.source_reference)}</p><blockquote>{esc(e.excerpt)}"
        f"{' [выдержка сокращена]' if e.excerpt_truncated else ''}</blockquote>"
        f"<p>Фиксация: {esc(e.captured_at.isoformat())}<br>Проверил: {esc(e.reviewer)}, "
        f"{esc(e.reviewed_at.isoformat())}<br>SHA-256: {esc(e.sha256)}</p></section>"
        for e in s.evidence
    )
    decisions = "".join(
        f"<li>{esc(f.code)}: {esc(f.reviewer)}, {esc(f.reviewed_at)} — {esc(f.notes)}</li>"
        for f in s.complex.factors
        if f.status == "confirmed"
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
</style><body><p class="demo">DEMO — вымышленные данные.
Не является выводом о незаконности.</p>
<h1>{esc(signal.title)}</h1><p>Сигнал {esc(signal.id)} · версия {signal.version}
<br>Статус: {STATUSES[signal.status]}</p>
<h2>{esc(s.complex.name)}</h2><p>{esc(s.complex.city)}, {esc(s.complex.address)}
<br>Застройщик: {esc(s.developer.name)} · вымышленный БИН {esc(s.developer.bin)}</p>
<p>Причина: {esc(signal.reason)}</p>
<h2>Приоритет проверки: {s.risk.score} / 100 · {s.risk.zone}</h2>
<p>Снимок версии ЖК {s.complex.version}, зафиксирован {esc(s.captured_at.isoformat())}.
Последующие изменения карточки сюда не включены. Гипотезы AI не дают баллов.</p>
<table><thead><tr><th>Фактор</th><th>Статус</th><th>Баллы</th><th>Источники</th></tr>
</thead><tbody>{rows}</tbody></table>
<h2>Правовое основание</h2><p>{esc(s.complex.legal_basis.type)} ·
{esc(s.complex.legal_basis.status)}<br>{esc(s.complex.legal_basis.reference)}
<br>{esc(s.complex.legal_basis.source)}</p>
<h2>Решения по факторам</h2><ul>{decisions}</ul>
<h2>Проверенные источники</h2>{evidence or "<p>Нет подтверждённых источников.</p>"}
<h2>Решение по сигналу</h2><p>Создал: {esc(signal.created_by)},
{esc(signal.created_at.isoformat())}<br>Проверил: {esc(signal.reviewer)},
{esc(signal.reviewed_at)}<br>Обоснование: {esc(signal.review_notes)}</p>
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
            from weasyprint import HTML
        except (ImportError, OSError):
            raise IntegrationUnavailable("PDF system libraries") from None
        return HTML(string=report_html(signal), url_fetcher=deny_resource).write_pdf()
    finally:
        PDF_SLOTS.release()
