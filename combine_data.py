# combine_data.py
# data/reYYYYMMDD.xls(x) 들을 읽어서 processed/all_data.csv에 "누적"
# - processed/all_data.csv가 있으면: 새 날짜만 추가
# - 같은 날짜 파일이 다시 들어오면: 그 날짜 데이터는 덮어쓰기(기존 날짜 행 삭제 후 추가)
# - 표가 아닌 파일(안내/에러로 저장된 xls)은 스킵
# - 새로 병합할 유효 데이터가 없으면 실패하지 않고 종료(성공)

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
    old = pd.read_csv(
        OUT_PATH,
        parse_dates=["날짜"],
        encoding="utf-8-sig",
        dtype={"종목명": "string"},
    )
    print(f"📌 기존 누적 로드: {OUT_PATH.name} (rows={len(old):,})")
else:
    old = pd.DataFrame(columns=["종목명", "매수", "매도", "순매수", "날짜"])
    print("📌 기존 누적 없음: 새로 생성합니다.")

# 2) data 폴더에서 파일 읽기 → 날짜별 DF 만들기
new_dfs = []
new_dates = set()

files = sorted([p for p in DATA_DIR.iterdir() if p.suffix.lower() in (".xls", ".xlsx")])
if not files:
    # ✅ 액션에서 다운로더가 저장 안 했을 수도 있으니, 실패 말고 성공 종료
    print("ℹ️ data 폴더에 xls/xlsx 파일이 없습니다. (다운로드 실패/휴일 가능) → 종료(성공)")
    raise SystemExit(0)

for file in files:
    date_str = file.stem.replace("re", "")  # reYYYYMMDD
    try:
        dt = pd.to_datetime(date_str, format="%Y%m%d", errors="coerce")
        if pd.isna(dt):
            print(f"⚠️ 스킵: {file.name} → 날짜 파싱 실패({date_str})")
            continue

        # ✅ 표 읽기
        tables = pd.read_html(str(file), header=0, flavor="lxml")
        if not tables:
            print(f"⚠️ 스킵: {file.name} → 표를 찾지 못함(안내/에러 페이지 가능)")
            continue
        df = tables[0]

        # ✅ 표 형식 아니면 스킵 (열 부족)
        if df.shape[1] < 6:
            print(f"⚠️ 스킵: {file.name} → 열 수 부족({df.shape[1]}). (안내/에러 페이지일 가능성)")
            continue

        df = df.iloc[:, [3, 4, 5]].copy()
        df.columns = ["종목명", "매수", "매도"]

        # 숫자 변환
        for c in ["매수", "매도"]:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

        # ✅ 종목명 비어있는 행 제거 (가끔 헤더/빈줄 섞임 방지)
        df["종목명"] = df["종목명"].astype("string").str.strip()
        df = df.dropna(subset=["종목명"])
        df = df[df["종목명"] != ""]

        df["순매수"] = df["매수"] - df["매도"]
        df["날짜"] = dt.normalize()

        # ✅ 모두 NaN이면(실제 데이터 없음) 스킵
        if df[["매수", "매도", "순매수"]].isna().all().all():
            print(f"⚠️ 스킵: {file.name} → 수치 데이터가 전부 비어있음(안내/빈 데이터 가능)")
            continue

        new_dfs.append(df)
        new_dates.add(dt.normalize())

        print(f"✅ 처리 완료: {file.name} ({len(df)}행)")

    except Exception as e:
        print(f"⚠️ 스킵: {file.name} → {e}")

# ✅ 유효 새 데이터가 없으면 실패하지 말고 성공 종료
if not new_dfs:
    print("\nℹ️ 새로 병합할 유효 데이터가 없습니다. (주말/휴일/사이트 응답 문제 가능) → 종료(성공)")
    raise SystemExit(0)

new_data = pd.concat(new_dfs, ignore_index=True)

# 3) 같은 날짜는 “덮어쓰기” (기존에서 해당 날짜 제거 후 append)
if len(old) > 0:
    old["날짜"] = pd.to_datetime(old["날짜"], errors="coerce").dt.normalize()
    mask_keep = ~old["날짜"].isin(new_dates)
    removed = len(old) - int(mask_keep.sum())
    old = old.loc[mask_keep].copy()
    if removed:
        print(f"🧹 덮어쓰기: 기존 데이터에서 동일 날짜 행 {removed:,}개 제거")

# 4) 합치고 저장
merged = pd.concat([old, new_data], ignore_index=True)

merged["종목명"] = merged["종목명"].astype("string").str.strip()
merged["날짜"] = pd.to_datetime(merged["날짜"], errors="coerce").dt.normalize()

merged = merged.dropna(subset=["날짜", "종목명"])
merged = merged.sort_values(["날짜", "종목명"]).reset_index(drop=True)

merged.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

print(f"\n🎉 누적 병합 완료! 총 {len(merged):,}행 → {OUT_PATH} 저장")
print(f"🆕 이번에 반영한 날짜 수: {len(new_dates)}개")
