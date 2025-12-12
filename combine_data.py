import os
import pandas as pd

data_dir = "data"
output_dir = "processed"
os.makedirs(output_dir, exist_ok=True)

print("📊 데이터 병합 시작...\n")
all_data = []

for file in sorted(os.listdir(data_dir)):
    if not (file.endswith(".xls") or file.endswith(".xlsx")):
        continue

    path = os.path.join(data_dir, file)
    date = file.replace("re", "").replace(".xls", "").replace(".xlsx", "")

    try:
        # 📍 종목명(D), 매수(E), 매도(F)
        df = pd.read_html(path, header=0, flavor="lxml")[0]

        # 열 수 확인 후, 최소 6개 이상일 때 D/E/F만 추출
        if df.shape[1] < 6:
            raise ValueError(f"열 수 부족 ({df.shape[1]})")

        df = df.iloc[:, [3, 4, 5]].copy()
        df.columns = ["종목명", "매수", "매도"]

        # 숫자 처리
        df["매수"] = (
            df["매수"].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(" ", "", regex=False)
        )
        df["매도"] = (
            df["매도"].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(" ", "", regex=False)
        )

        df["매수"] = pd.to_numeric(df["매수"], errors="coerce")
        df["매도"] = pd.to_numeric(df["매도"], errors="coerce")
        df["순매수"] = df["매수"] - df["매도"]

        # ✅ 날짜를 datetime으로 변환
        df["날짜"] = pd.to_datetime(date, format="%Y%m%d")

        all_data.append(df)

        print(f"✅ 처리 완료: {file} ({len(df)}행)")

    except Exception as e:
        print(f"⚠️ 실패: {file} → {e}")

if all_data:
    merged = pd.concat(all_data, ignore_index=True)
    merged.to_csv(
        os.path.join(output_dir, "all_data.csv"), index=False, encoding="utf-8-sig"
    )
    print(f"\n🎉 병합 완료! 총 {len(merged)}행 → processed/all_data.csv 로 저장됨.")
else:
    print("\n❌ 병합할 유효 데이터가 없습니다.")
