from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "processed"

OUT_DIR.mkdir(exist_ok=True)

OUT_PATH = OUT_DIR / "all_data.csv"

print("📊 데이터 병합 시작\n")

files = sorted(DATA_DIR.glob("re*.xls"))

if not files:
    print("ℹ️ data 폴더에 파일 없음 → 종료")
    exit()

# 기존 데이터 로드
if OUT_PATH.exists():
    old = pd.read_csv(
        OUT_PATH,
        parse_dates=["날짜"],
        encoding="utf-8-sig",
        dtype={"종목명": "string"}
    )
    print(f"📌 기존 데이터 {len(old):,}행 로드")
else:
    old = pd.DataFrame(columns=["종목명","매수","매도","순매수","날짜"])
    print("📌 기존 데이터 없음")

new_dfs = []
new_dates = set()

for file in files:

    ymd = file.stem.replace("re","")

    try:

        dt = pd.to_datetime(ymd,format="%Y%m%d")

        df = pd.read_html(file)[0]

        df.columns = ["종목명","매수","매도"]

        for c in ["매수","매도"]:
            df[c] = (
                df[c]
                .astype(str)
                .str.replace(",","")
            )
            df[c] = pd.to_numeric(df[c],errors="coerce")

        df["순매수"] = df["매수"] - df["매도"]

        df["날짜"] = dt.strftime("%Y-%m-%d")

        new_dfs.append(df)
        new_dates.add(dt.strftime("%Y-%m-%d"))

        print(f"✅ 처리 완료 {file.name} ({len(df)}행)")

    except Exception as e:

        print(f"⚠️ 실패 {file.name}")
        print(e)

if not new_dfs:
    print("❌ 처리된 데이터 없음")
    exit()

new_data = pd.concat(new_dfs,ignore_index=True)

# 같은 날짜 덮어쓰기
old["날짜"] = old["날짜"].astype(str)

mask = ~old["날짜"].isin(new_dates)

old = old.loc[mask]

merged = pd.concat([old,new_data],ignore_index=True)

merged = merged.sort_values(["날짜","종목명"]).reset_index(drop=True)

merged.to_csv(OUT_PATH,index=False,encoding="utf-8-sig")

print("\n🎉 병합 완료")
print(f"총 행수: {len(merged):,}")
print(f"저장 위치: {OUT_PATH}")
