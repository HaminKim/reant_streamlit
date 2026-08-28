"""
processed/all_data_clean.csv 에 아직 없는 '영업일'을 찾아서
YYYYMMDD 형식으로 오래된 날짜부터 한 줄씩 출력한다.

사용:
    python find_missing_days.py [LOOKBACK_DAYS] [MAX_OUTPUT]

    LOOKBACK_DAYS : 오늘로부터 며칠 전까지 볼지 (기본 12)
    MAX_OUTPUT    : 최대 몇 개까지 출력할지 (기본 8) — 스케줄 실행이 과도하게 길어지지 않게 상한

이 스크립트는 stdout 에 날짜만 출력한다. 진단 메시지는 stderr 로.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
CSV = BASE / "processed" / "all_data_clean.csv"

# 한국 거래소 휴장일 (고정 + 주요 변동 공휴일). 없는 날짜가 섞여도
# 다운로더가 '데이터 없음(exit 2)'으로 넘어가므로 치명적이지 않다.
HOLIDAYS = {
    # 2025
    "2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
    "2025-03-03", "2025-05-01", "2025-05-05", "2025-05-06", "2025-06-03",
    "2025-06-06", "2025-08-15", "2025-10-03", "2025-10-06", "2025-10-07",
    "2025-10-08", "2025-10-09", "2025-12-25", "2025-12-31",
    # 2026
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-25", "2026-06-08", "2026-08-17",
    "2026-09-24", "2026-09-25", "2026-10-05", "2026-10-09", "2026-12-25",
    "2026-12-31",
    # 2027
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-02-10", "2027-03-01",
    "2027-05-05", "2027-05-13", "2027-06-07", "2027-08-16", "2027-09-14",
    "2027-09-15", "2027-09-16", "2027-10-04", "2027-10-11", "2027-12-27",
    "2027-12-31",
}


def log(*a):
    print(*a, file=sys.stderr)


def main():
    lookback = int(sys.argv[1]) if len(sys.argv) >= 2 and sys.argv[1] else 12
    max_out = int(sys.argv[2]) if len(sys.argv) >= 3 and sys.argv[2] else 8

    # Seibro 해외주식 보고서는 상위 ~50종목. 이보다 훨씬 적으면
    # 렌더링이 덜 된 상태에서 긁힌 '부분 스크랩'으로 보고 다시 받는다.
    MIN_ROWS = 10

    if not CSV.exists():
        log(f"⚠️ {CSV} 없음 — 최근 {lookback}일 전부 후보로 출력")
        counts = {}
    else:
        df = pd.read_csv(CSV, dtype=str, encoding="utf-8-sig")
        col = "날짜" if "날짜" in df.columns else df.columns[0]
        dates = pd.to_datetime(df[col], errors="coerce").dt.date.dropna()
        counts = dates.value_counts().to_dict()

    today = date.today()
    holidays = {pd.Timestamp(h).date() for h in HOLIDAYS}

    missing = []
    for i in range(lookback, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:            # 토/일
            continue
        if d in holidays:
            continue
        n = counts.get(d, 0)
        if n >= MIN_ROWS:
            continue
        if 0 < n < MIN_ROWS:
            log(f"  ⚠️ {d}: {n}행뿐 — 부분 스크랩으로 보고 재수집")
        missing.append(d)

    missing = missing[:max_out]

    if not missing:
        log("✅ 누락 영업일 없음")
        return

    log(f"🔎 누락 영업일 {len(missing)}개: {[str(d) for d in missing]}")
    for d in missing:
        print(d.strftime("%Y%m%d"))


if __name__ == "__main__":
    main()
