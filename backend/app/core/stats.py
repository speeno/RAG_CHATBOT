"""운영 통계 집계 (PRD §34 대시보드, §35 미답변 분석).

`turn_logs`를 기간별로 읽어 Python에서 집계한다 — SQLite/Postgres 공통 SQL 유지가 목적이며,
수만 건 규모까지는 충분하다(필요 시 SQL GROUP BY로 교체). 날짜는 `tz_offset_minutes`(기본 +540 = KST) 기준 로컬 일자로 묶는다.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.db import BaseDatabase

_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_question(q: str) -> str:
    """유사 질문 묶기용 키: 소문자 + 공백/문장부호 제거 (예: '환불은 언제까지?' == '환불은  언제까지')."""
    return _PUNCT.sub("", (q or "").lower())


@dataclass
class Range:
    start: date          # inclusive (local date)
    end: date            # inclusive (local date)
    tz: timezone

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def prev(self) -> "Range":
        return Range(self.start - timedelta(days=self.days), self.start - timedelta(days=1), self.tz)

    def utc_bounds(self) -> tuple[str, str]:
        """로컬 [start 00:00, end+1 00:00) → UTC ISO 문자열(created_at 비교용)."""
        s = datetime.combine(self.start, datetime.min.time(), self.tz).astimezone(timezone.utc)
        e = datetime.combine(self.end + timedelta(days=1), datetime.min.time(), self.tz).astimezone(timezone.utc)
        return s.isoformat(timespec="seconds"), e.isoformat(timespec="seconds")


def make_range(date_from: str | None, date_to: str | None, tz_offset_minutes: int = 540, default_days: int = 7) -> Range:
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    today = datetime.now(tz).date()
    end = date.fromisoformat(date_to) if date_to else today
    start = date.fromisoformat(date_from) if date_from else end - timedelta(days=default_days - 1)
    if start > end:
        start, end = end, start
    return Range(start, end, tz)


def _local_date(created_at: str, tz: timezone) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return created_at[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).date().isoformat()


def _pct(n: int, d: int) -> float | None:
    return None if d == 0 else round(n * 100.0 / d, 1)


def _avg(xs: list[int]) -> int | None:
    return None if not xs else int(sum(xs) / len(xs))


def _delta(cur: float | int | None, prev: float | int | None) -> float | None:
    if cur is None or prev is None:
        return None
    return round(float(cur) - float(prev), 1)


def _kpi(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    answered = sum(1 for r in rows if r.get("answerable"))
    pos = sum(1 for r in rows if r.get("feedback") == "positive")
    neg = sum(1 for r in rows if r.get("feedback") == "negative")
    fb = pos + neg
    convs = {r["conversation_id"] for r in rows}
    return {
        "questions": n,
        "answered": answered,
        "unanswered": n - answered,
        "answer_rate": _pct(answered, n),
        "no_answer_rate": _pct(n - answered, n),
        "feedback_count": fb,
        "positive_rate": _pct(pos, fb),
        "negative_rate": _pct(neg, fb),
        "conversations": len(convs),
        "avg_turns": round(n / len(convs), 1) if convs else None,
        "avg_total_ms": _avg([r["total_ms"] for r in rows if r.get("total_ms") is not None]),
        "avg_retrieval_ms": _avg([r["retrieval_ms"] for r in rows if r.get("retrieval_ms") is not None]),
        "avg_llm_ms": _avg([r["llm_ms"] for r in rows if r.get("llm_ms") is not None and r.get("answerable")]),
    }


def _top_category(r: dict[str, Any]) -> str:
    ret = r.get("retrieved") or []
    return (ret[0].get("category") if ret else None) or "미분류"


def _group_questions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = normalize_question(r["user_query"])
        if not key:
            continue
        g = groups.setdefault(key, {"key": key, "question": r["user_query"], "count": 0, "unanswered": 0,
                                     "last_at": r["created_at"], "conversation_id": r["conversation_id"],
                                     "message_id": r["message_id"], "top_score": None, "category": None})
        g["count"] += 1
        if not r.get("answerable"):
            g["unanswered"] += 1
        if r["created_at"] >= g["last_at"]:
            g["last_at"] = r["created_at"]
            g["question"] = r["user_query"]
            g["conversation_id"] = r["conversation_id"]
            g["message_id"] = r["message_id"]
        ret = r.get("retrieved") or []
        if ret:
            sc = ret[0].get("score")
            if sc is not None and (g["top_score"] is None or sc > g["top_score"]):
                g["top_score"] = sc
                g["category"] = ret[0].get("category") or None
    return groups


def dashboard(db: BaseDatabase, rng: Range) -> dict[str, Any]:
    s, e = rng.utc_bounds()
    rows = db.turn_log_rows(s, e)
    ps, pe = rng.prev().utc_bounds()
    prev_rows = db.turn_log_rows(ps, pe)

    cur = _kpi(rows)
    prev = _kpi(prev_rows)
    delta = {k: _delta(cur.get(k), prev.get(k)) for k in ("questions", "answer_rate", "no_answer_rate", "positive_rate", "avg_total_ms", "conversations")}

    # 일별 추이 (빈 날짜도 0으로 채움)
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"questions": 0, "answered": 0, "unanswered": 0, "positive": 0, "negative": 0})
    for r in rows:
        d = by_day[_local_date(r["created_at"], rng.tz)]
        d["questions"] += 1
        d["answered" if r.get("answerable") else "unanswered"] += 1
        if r.get("feedback") in ("positive", "negative"):
            d[r["feedback"]] += 1
    daily = []
    for i in range(rng.days):
        day = (rng.start + timedelta(days=i)).isoformat()
        daily.append({"date": day, **by_day.get(day, {"questions": 0, "answered": 0, "unanswered": 0, "positive": 0, "negative": 0})})

    # 카테고리 TOP (답변된 턴의 1순위 문서 카테고리)
    cat = Counter(_top_category(r) for r in rows if r.get("answerable"))
    total_cat = sum(cat.values())
    categories = [{"category": c, "count": n, "share": _pct(n, total_cat)} for c, n in cat.most_common(5)]

    # 피드백 비율
    pos = sum(1 for r in rows if r.get("feedback") == "positive")
    neg = sum(1 for r in rows if r.get("feedback") == "negative")
    feedback = {"positive": pos, "negative": neg, "none": len(rows) - pos - neg, "total": len(rows)}

    # 주요 질문 TOP 5 (질문 수 기준) + 미답변률
    groups = _group_questions(rows)
    top_questions = sorted(groups.values(), key=lambda g: (-g["count"], g["last_at"]))[:5]
    top_questions = [{"question": g["question"], "category": g["category"] or "미분류", "count": g["count"],
                      "unanswered_rate": _pct(g["unanswered"], g["count"])} for g in top_questions]

    return {
        "range": {"from": rng.start.isoformat(), "to": rng.end.isoformat(), "days": rng.days,
                  "prev_from": rng.prev().start.isoformat(), "prev_to": rng.prev().end.isoformat()},
        "kpi": cur, "kpi_prev": prev, "delta": delta,
        "daily": daily, "categories": categories, "feedback": feedback, "top_questions": top_questions,
    }


def unanswered(db: BaseDatabase, rng: Range, top_n: int = 10) -> dict[str, Any]:
    s, e = rng.utc_bounds()
    rows = db.turn_log_rows(s, e)
    ps, pe = rng.prev().utc_bounds()
    prev_rows = db.turn_log_rows(ps, pe)
    un = [r for r in rows if not r.get("answerable")]
    un_prev = [r for r in prev_rows if not r.get("answerable")]

    reviews = {rv["question_key"]: rv for rv in db.list_unanswered_reviews()}
    groups = _group_questions(un)
    prev_groups = _group_questions(un_prev)
    resolved = sum(g["count"] for g in groups.values() if reviews.get(g["key"], {}).get("status") == "resolved")

    def growth(cur_n: int, prev_n: int) -> float | None:
        if prev_n == 0:
            return None if cur_n == 0 else 100.0
        return round((cur_n - prev_n) * 100.0 / prev_n, 1)

    top = []
    for g in sorted(groups.values(), key=lambda g: (-g["count"], g["last_at"]))[:top_n]:
        rv = reviews.get(g["key"])
        prev_n = prev_groups.get(g["key"], {}).get("count", 0)
        # 개선 추천: 관련 문서가 전혀 없거나 매우 낮음 → 새 문서 추가 / 임계값 근처 → 기존 문서 보완
        sc = g["top_score"]
        rec = "new_document" if (sc is None or sc < 0.15) else "improve_document"
        top.append({
            "key": g["key"], "question": g["question"], "count": g["count"], "share": _pct(g["count"], len(un)),
            "growth": growth(g["count"], prev_n), "last_at": g["last_at"], "top_score": sc,
            "category": g["category"] or "미분류", "recommendation": rec,
            "status": (rv or {}).get("status", "open"), "note": (rv or {}).get("note"),
            "conversation_id": g["conversation_id"], "message_id": g["message_id"],
        })

    by_day: Counter[str] = Counter(_local_date(r["created_at"], rng.tz) for r in un)
    daily = [{"date": (rng.start + timedelta(days=i)).isoformat(), "unanswered": by_day.get((rng.start + timedelta(days=i)).isoformat(), 0)}
             for i in range(rng.days)]

    cat = Counter(_top_category(r) for r in un)
    categories = [{"category": c, "count": n, "share": _pct(n, len(un))} for c, n in cat.most_common()]

    recs = Counter(t["recommendation"] for t in top)
    repeated = sum(1 for g in groups.values() if g["count"] >= 2)

    return {
        "range": {"from": rng.start.isoformat(), "to": rng.end.isoformat(), "days": rng.days},
        "kpi": {
            "unanswered": len(un), "unanswered_prev": len(un_prev), "growth": growth(len(un), len(un_prev)),
            "rate": _pct(len(un), len(rows)), "rate_prev": _pct(len(un_prev), len(prev_rows)),
            "questions": len(rows), "distinct": len(groups),
            "resolved": resolved, "resolved_rate": _pct(resolved, len(un)),
        },
        "top": top, "daily": daily, "categories": categories,
        "recommendations": {"new_document": recs.get("new_document", 0), "improve_document": recs.get("improve_document", 0), "faq_candidates": repeated},
    }
