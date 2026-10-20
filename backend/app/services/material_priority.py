"""Preliminary review workload, NOT legal risk or model confidence.

25 for an unresolved R2 + 10 for an unresolved R3, each once, irrespective
of number of publications or hypotheses. Thresholds: low <10, medium <25,
high >=25. Unanalyzed-only materials are unknown, not a zero-risk finding.
"""


def review_priority(proposals, states, review_state="needs_review"):
    if review_state != "needs_review":
        return {
            "score": 0,
            "level": "low",
            "reasons": ["Материал уже рассмотрен; новых условий не обнаружено."],
        }
    codes = {p["code"] for p in proposals if p["decision"] in {"pending", "insufficient"}}
    if not codes and not any(s == "ready" for s in states):
        return {"score": None, "level": "unknown", "reasons": ["Анализ ещё не завершён."]}
    score = (25 if "R2" in codes else 0) + (10 if "R3" in codes else 0)
    reasons = []
    if "R2" in codes:
        reasons.append("Найдено предложение платежа; требуется проверка аналитиком (R2).")
    if "R3" in codes:
        reasons.append("В рекламе описано строящееся жильё; требуется проверка (R3).")
    if any(s in {"queued", "running", "failed"} for s in states):
        reasons.append("Часть материалов ещё не проанализирована; оценка предварительная.")
    return {
        "score": score,
        "level": "high" if score >= 25 else "medium" if score >= 10 else "low",
        "reasons": reasons or ["В проанализированном тексте признаки R2/R3 не выделены."],
    }
