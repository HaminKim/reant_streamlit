# combine_data.py
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("📊 데이터 병합 시작...\n")

all_data = []

if not DATA_DIR.exists():
    print(f"❌ data 폴더가 없습니다: {DATA_DIR}")
    raise SystemExit(1)

for file in sorted(DATA_DIR.iterdir()):
    if file.suffix.lower() not in (".xls", ".xlsx"):
        continue

    date = file.stem.replace("re", "")  # reYYYYMMDD
    try:
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
        df["날짜"] = pd.to_datetime(date, format="%Y%m%d", errors="coerce")

        # 날짜 파싱 실패한 파일은 스킵
        if df["날짜"].isna().all():
            raise ValueError(f"날짜 파싱 실패: {date}")

        all_data.append(df)
        print(f"✅ 처리 완료: {file.name} ({len(df)}행)")

    except Exception as e:
        print(f"⚠️ 실패: {file.name} → {e}")

if all_data:
    merged = pd.concat(all_data, ignore_index=True)

    out_path = OUT_DIR / "all_data.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"\n🎉 병합 완료! 총 {len(merged)}행 → {out_path} 로 저장됨.")
else:
    print("\n❌ 병합할 유효 데이터가 없습니다.")
    raise SystemExit(1)
