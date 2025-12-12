# clean_and_enrich.py
# 입력: processed/all_data.csv (컬럼: 종목명, 매수, 매도, 순매수, 날짜)
# 출력:
#  - processed/all_data_clean.csv (정제 + MA10/MA20 (+MA5 선택) 추가, utf-8-sig 저장)
#  - processed/by_stock_summary.csv (종목별 데이터 개수/최초/최종일)
#  - processed/stocks.txt (종목 리스트)

import pandas as pd
from pathlib import Path

# ✅ 경로 수정: 00리앤트 프로그램 / 리앤트
BASE = Path.home() / "Desktop" / "00리앤트 프로그램" / "리앤트"
PROC = BASE / "processed"
SRC  = PROC / "all_data.csv"
OUT_CLEAN = PROC / "all_data_clean.csv"
OUT_SUM   = PROC / "by_stock_summary.csv"
OUT_LIST  = PROC / "stocks.txt"

def to_num(s):
    """쉼표, 공백 제거 후 숫자 변환"""
    return pd.to_numeric(str(s).replace(",", "").replace(" ", ""), errors="coerce")

def main():
    if not SRC.exists():
        print(f"❌ 입력 파일이 없습니다: {SRC}")
        return

    print("📥 읽는 중:", SRC.name)
    df = pd.read_csv(SRC, dtype=str)

    # 필요한 컬럼만 확인
    need = ["종목명", "매수", "매도", "순매수", "날짜"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print("❌ 누락 컬럼:", missing)
        return
    df = df[need].copy()

    # 날짜/숫자 정리
    df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
    df = df.dropna(subset=["날짜"])
    df["종목명"] = df["종목명"].astype(str).str.strip()

    for c in ["매수", "매도", "순매수"]:
        df[c] = df[c].apply(to_num)

    # 날짜-종목별 중복 합산
    df = (
        df.groupby(["날짜", "종목명"], as_index=False)
          .agg({"매수": "sum", "매도": "sum", "순매수": "sum"})
          .sort_values(["종목명", "날짜"])
          .reset_index(drop=True)
    )

    # 이동평균 (rolling mean)
    df["MA5"]  = df.groupby("종목명")["순매수"].rolling(5,  min_periods=5).mean().reset_index(level=0, drop=True)
    df["MA10"] = df.groupby("종목명")["순매수"].rolling(10, min_periods=10).mean().reset_index(level=0, drop=True)
    df["MA20"] = df.groupby("종목명")["순매수"].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)

    # 저장
    df.to_csv(OUT_CLEAN, index=False, encoding="utf-8-sig")
    print(f"✅ 저장 완료: {OUT_CLEAN.name} (rows={len(df):,})")

    # 요약 통계
    sumdf = (
        df.groupby("종목명")
          .agg(행수=("날짜","size"), 최초일=("날짜","min"), 최종일=("날짜","max"))
          .reset_index()
          .sort_values(["행수","종목명"], ascending=[False, True])
    )
    sumdf.to_csv(OUT_SUM, index=False, encoding="utf-8-sig")
    print(f"🧾 요약 저장: {OUT_SUM.name}")

    # 종목 리스트
    stocks = df["종목명"].dropna().drop_duplicates().sort_values().tolist()
    OUT_LIST.write_text("\n".join(stocks), encoding="utf-8")
    print(f"📝 종목 리스트 저장: {OUT_LIST.name} (총 {len(stocks)}종목)")

    print("🎉 정제 + 지표 추가 완료!")

if __name__ == "__main__":
    main()
