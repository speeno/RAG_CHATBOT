"""실시간 날씨 프로바이더 — 공공데이터포털(data.go.kr) 기상청 단기예보 조회서비스(VilageFcstInfoService_2.0).

- `KMA_SERVICE_KEY` 설정 시에만 활성화된다(미설정 → 기능 자동 비활성, 기존 동작 불변).
- 실황(getUltraSrtNcst: 기온·강수형태·1시간 강수량·습도·풍속) + 단기예보(getVilageFcst: 하늘상태·강수확률·최저/최고기온).
- 좌표는 기상청 격자(nx, ny) — 주요 지역 매핑 테이블 사용, 지역 미언급 시 서울.
- 10분 TTL 인메모리 캐시(무료 티어 호출 한도 보호). 실패는 조용히 None(채팅 흐름은 Fail-Closed 원칙 유지).
"""
from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

#: 기상청 단기예보 격자 좌표 (nx, ny) — 주요 지역
REGIONS: dict[str, tuple[int, int]] = {
    "서울": (60, 127), "인천": (55, 124), "수원": (60, 121), "성남": (63, 124), "고양": (57, 128),
    "부산": (98, 76), "대구": (89, 90), "울산": (102, 84), "창원": (90, 77), "포항": (102, 94),
    "광주": (58, 74), "전주": (63, 89), "목포": (50, 67), "여수": (73, 66),
    "대전": (67, 100), "세종": (66, 103), "청주": (69, 106), "천안": (63, 110),
    "강릉": (92, 131), "춘천": (73, 134), "원주": (76, 122), "속초": (87, 141),
    "제주": (52, 38), "서귀포": (52, 33), "안동": (91, 106), "김해": (95, 77), "평택": (62, 114),
}
DEFAULT_REGION = "서울"

_WEATHER_WORDS = ("날씨", "기온", "온도", "비 ", "비가", "비와", "비 와", "눈 ", "눈이", "눈와", "폭우", "폭설", "호우",
                  "태풍", "특보", "우산", "강수", "강우", "더위", "추위", "덥나", "춥나", "더워", "추워", "바람", "풍속",
                  "습도", "맑아", "맑나", "흐리", "우천", "기상")

PTY = {0: None, 1: "비", 2: "비/눈", 3: "눈", 4: "소나기", 5: "빗방울", 6: "빗방울·눈날림", 7: "눈날림"}
SKY = {1: "맑음", 3: "구름많음", 4: "흐림"}


def is_weather_query(text: str) -> bool:
    t = f"{text} "
    return any(w in t for w in _WEATHER_WORDS)


def detect_region(text: str) -> str:
    for name in REGIONS:
        if name in text:
            return name
    return DEFAULT_REGION


@dataclass
class WeatherReport:
    region: str
    observed_at: str            # 실황 기준 시각 (예: 2026-08-20 14:00 KST)
    now: dict[str, Any]         # {temp, pty, rain_1h, humidity, wind}
    today: dict[str, Any]       # {sky, pop_max, tmin, tmax, pty_set}
    tomorrow: dict[str, Any]

    def as_context_text(self) -> str:
        n = self.now
        parts = [f"[실시간 기상 정보 — {self.region}, 기상청 단기예보 서비스, 기준 {self.observed_at}]"]
        now_bits = []
        if n.get("temp") is not None:
            now_bits.append(f"현재 기온 {n['temp']}℃")
        now_bits.append(f"현재 강수: {n['pty'] or '없음'}")
        if n.get("rain_1h"):
            now_bits.append(f"1시간 강수량 {n['rain_1h']}mm")
        if n.get("humidity") is not None:
            now_bits.append(f"습도 {n['humidity']}%")
        if n.get("wind") is not None:
            now_bits.append(f"풍속 {n['wind']}m/s")
        parts.append("현재 날씨: " + ", ".join(now_bits) + ".")
        for label, d in (("오늘", self.today), ("내일", self.tomorrow)):
            if not d:
                continue
            bits = []
            if d.get("sky"):
                bits.append(f"하늘 {d['sky']}")
            if d.get("pty_set"):
                bits.append("강수형태 " + "/".join(d["pty_set"]))
            if d.get("pop_max") is not None:
                bits.append(f"최대 강수확률 {d['pop_max']}%")
            if d.get("tmin") is not None:
                bits.append(f"최저 {d['tmin']}℃")
            if d.get("tmax") is not None:
                bits.append(f"최고 {d['tmax']}℃")
            if bits:
                parts.append(f"{label} 예보: " + ", ".join(bits) + ".")
        parts.append("(안내: 기상 상황에 따라 배송·수거 일정이 지연될 수 있습니다.)")
        return "\n".join(parts)


class KmaWeather:
    """data.go.kr 단기예보 클라이언트. 실패 시 None 반환(호출부는 기능을 건너뜀)."""

    def __init__(self, service_key: str, timeout: float = 7.0, cache_ttl: int = 600):
        # 포털이 주는 '일반 인증키(Encoding)'가 들어와도 동작하도록 디코딩해 보관(httpx 가 한 번만 인코딩)
        self.service_key = urllib.parse.unquote(service_key) if "%" in service_key else service_key
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
    name = "kma:vilage-fcst-2.0"

    # ── 시각 계산 ────────────────────────────────────────────────
    @staticmethod
    def _ncst_base(now: datetime) -> tuple[str, str]:
        """초단기실황: 매시 40분경 생성 → 40분 이전이면 직전 정시."""
        t = now if now.minute >= 45 else now - timedelta(hours=1)
        return t.strftime("%Y%m%d"), t.strftime("%H00")

    @staticmethod
    def _fcst_base(now: datetime) -> tuple[str, str]:
        """단기예보: 02/05/08/11/14/17/20/23시 발표(+10분 여유)."""
        t = now - timedelta(minutes=15)
        for h in (23, 20, 17, 14, 11, 8, 5, 2):
            if t.hour >= h:
                return t.strftime("%Y%m%d"), f"{h:02d}00"
        y = t - timedelta(days=1)
        return y.strftime("%Y%m%d"), "2300"

    # ── HTTP ─────────────────────────────────────────────────────
    def _get(self, path: str, **params: Any) -> list[dict[str, Any]] | None:
        key = f"{path}|{sorted(params.items())}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.cache_ttl:
                return hit[1]
        try:
            r = httpx.get(f"{BASE_URL}/{path}", params={
                "serviceKey": self.service_key, "dataType": "JSON", "pageNo": 1, "numOfRows": 1000, **params,
            }, timeout=self.timeout)
            r.raise_for_status()
            body = r.json()["response"]
            if body["header"]["resultCode"] != "00":
                logger.warning("KMA API 오류: %s %s", body["header"]["resultCode"], body["header"].get("resultMsg"))
                return None
            items = body["body"]["items"]["item"]
        except Exception:  # noqa: BLE001 — 네트워크/파싱 실패는 기능 스킵
            logger.exception("KMA API 호출 실패: %s", path)
            return None
        with self._lock:
            self._cache[key] = (time.time(), items)
        return items

    # ── public ───────────────────────────────────────────────────
    def get_report(self, region: str | None = None, *, now: datetime | None = None) -> WeatherReport | None:
        region = region if region in REGIONS else DEFAULT_REGION
        nx, ny = REGIONS[region]
        now = now or datetime.now(KST)

        bd, bt = self._ncst_base(now)
        ncst = self._get("getUltraSrtNcst", base_date=bd, base_time=bt, nx=nx, ny=ny)
        obs: dict[str, Any] = {}
        if ncst:
            vals = {i["category"]: i["obsrValue"] for i in ncst}
            def fnum(v: Any) -> float | None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            obs = {"temp": fnum(vals.get("T1H")), "pty": PTY.get(int(float(vals.get("PTY", 0))) if vals.get("PTY") else 0),
                   "rain_1h": fnum(vals.get("RN1")) or None, "humidity": fnum(vals.get("REH")), "wind": fnum(vals.get("WSD"))}

        fd, ft = self._fcst_base(now)
        fcst = self._get("getVilageFcst", base_date=fd, base_time=ft, nx=nx, ny=ny)
        days: dict[str, dict[str, Any]] = {}
        if fcst:
            today = now.strftime("%Y%m%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y%m%d")
            for it in fcst:
                d = it["fcstDate"]
                if d not in (today, tomorrow):
                    continue
                slot = days.setdefault(d, {"pop": [], "sky": [], "pty": set(), "tmin": None, "tmax": None})
                c, v = it["category"], it["fcstValue"]
                if c == "POP":
                    slot["pop"].append(int(v))
                elif c == "SKY":
                    slot["sky"].append(int(v))
                elif c == "PTY" and v not in ("0", 0):
                    name = PTY.get(int(v))
                    if name:
                        slot["pty"].add(name)
                elif c == "TMN":
                    slot["tmin"] = round(float(v))
                elif c == "TMX":
                    slot["tmax"] = round(float(v))

            def summarize(d: str) -> dict[str, Any]:
                s = days.get(d)
                if not s:
                    return {}
                sky = SKY.get(max(set(s["sky"]), key=s["sky"].count)) if s["sky"] else None
                return {"sky": sky, "pop_max": max(s["pop"]) if s["pop"] else None,
                        "pty_set": sorted(s["pty"]), "tmin": s["tmin"], "tmax": s["tmax"]}
            today_sum, tomorrow_sum = summarize(today), summarize(tomorrow)
        else:
            today_sum, tomorrow_sum = {}, {}

        if not obs and not today_sum and not tomorrow_sum:
            return None
        return WeatherReport(
            region=region,
            observed_at=f"{bd[:4]}-{bd[4:6]}-{bd[6:]} {bt[:2]}:{bt[2:]} KST",
            now=obs or {"temp": None, "pty": None, "rain_1h": None, "humidity": None, "wind": None},
            today=today_sum, tomorrow=tomorrow_sum,
        )
