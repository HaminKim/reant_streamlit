# combine_data.py
# data/reYYYYMMDD.xls(x) 들을 읽어서 processed/all_data.csv에 "누적"
# - processed/all_data.csv가 있으면: 새 날짜만 추가
# - 같은 날짜 파일이 다시 들어오면: 그 날짜 데이터는 덮어쓰기(기존 날짜 행 삭제 후 추가)
# - 마지막에 전체를 날짜 기준 정렬해서 저장

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "all_data.csv"

print("📊 데이터 병합(증분 누적) 시작...\n")

if not DATA_DIR.exists():
    print(f"❌ data 폴더가 없습니다: {DATA_DIR}")
    raise SystemExit(1)

# 1) 기존 누적 데이터 로드 (있으면)
if OUT_PATH.exists():
    old = pd.read_csv(OUT_PATH, parse_dates=["날짜"], encoding="utf-8-sig", dtype={"종목명": "string"})
    print(f"📌 기존 누적 로드: {OUT_PATH.name} (rows={len(old):,})")
else:
    old = pd.DataFrame(columns=["종목명", "매수", "매도", "순매수", "날짜"])
    print("📌 기존 누적 없음: 새로 생성합니다.")

# 2) data 폴더에서 파일 읽기 → 날짜별 DF 만들기
new_dfs = []
new_dates = set()

files = sorted([p for p in DATA_DIR.iterdir() if p.suffix.lower() in (".xls", ".xlsx")])
if not files:
    print("❌ data 폴더에 xls/xlsx 파일이 없습니다.")
    raise SystemExit(1)

for file in files:
    date_str = file.stem.replace("re", "")  # reYYYYMMDD
    try:
        dt = pd.to_datetime(date_str, format="%Y%m%d", errors="coerce")
        if pd.isna(dt):
            raise ValueError(f"날짜 파싱 실패: {date_str}")

        df = pd.read_html(str(file), header=0, flavor="lxml")[0]
        if df.shape[1] < 6:
            raise ValueError(f"열 수 부족 ({df.shape[1]})")

        df = df.iloc[:, [3, 4, 5]].copy()
        df.columns = ["종목명", "매수", "매도"]

        for c in ["매수", "매도"]:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df["순매수"] = df["매수"] - df["매도"]
        df["날짜"] = dt

        new_dfs.append(df)
        new_dates.add(dt.normalize())

        print(f"✅ 처리 완료: {file.name} ({len(df)}행)")

    except Exception as e:
        print(f"⚠️ 실패: {file.name} → {e}")

if not new_dfs:
    print("\n❌ 새로 병합할 유효 데이터가 없습니다.")
    raise SystemExit(1)

new_data = pd.concat(new_dfs, ignore_index=True)

# 3) 같은 날짜는 “덮어쓰기” (기존에서 해당 날짜 제거 후 append)
if len(old) > 0:
    # old["날짜"]가 Timestamp면 normalize로 날짜만 비교
    old_dates = pd.to_datetime(old["날짜"], errors="coerce").dt.normalize()
    mask_keep = ~old_dates.isin(new_dates)
    removed = len(old) - int(mask_keep.sum())
    old = old.loc[mask_keep].copy()
    if removed:
        print(f"🧹 덮어쓰기: 기존 데이터에서 동일 날짜 행 {removed:,}개 제거")

# 4) 합치고 저장
merged = pd.concat([old, new_data], ignore_index=True)

# 기본 정리(형 안정화)
merged["종목명"] = merged["종목명"].astype("string").str.strip()
merged["날짜"] = pd.to_datetime(merged["날짜"], errors="coerce")

merged = merged.sort_values(["날짜", "종목명"]).reset_index(drop=True)

merged.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

print(f"\n🎉 누적 병합 완료! 총 {len(merged):,}행 → {OUT_PATH} 저장")
print(f"🆕 이번에 반영한 날짜 수: {len(new_dates)}개")
