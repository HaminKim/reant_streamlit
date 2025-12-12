# downloader.py
# 세이브로 "외국인/기관 종목별 거래내역 TOP50" 자동 다운로드 (단순화 버전)
# 모든 날짜를 다운로드하고 파일명을 reYYYYMMDD.xls로 변경 후 data 폴더에 저장

from pathlib import Path
import time, shutil, sys, random
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager

# ──────────────────────────────────────────────────────────────
SEIBRO_URL = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921"

XPATH_SETTLE   = '//*[@id="a1_radio1_input_0"]'
XPATH_BUYSELL  = '//*[@id="area_radio_2_input_2"]'
XPATH_START    = '//*[@id="sd1_inputCalendar1_input"]'
XPATH_END      = '//*[@id="sd1_inputCalendar2_input"]'
XPATH_US       = '//*[@id="area_radio_input_1"]'
XPATH_QUERY    = '//*[@id="image2"]'
XPATH_XLS      = '//*[@id="ExcelDownload_img"]'
# ──────────────────────────────────────────────────────────────

# ✅ 변경: 저장 베이스 경로를 "바탕화면/00리앤트 프로그램/리앤트"로
BASE = Path.home() / "Desktop" / "00리앤트 프로그램" / "리앤트"   # ✅
DATA_DIR = BASE / "data"
TMP_DIR = BASE / "downloads_tmp"
for d in (DATA_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

def iter_days(start="20241009", end=None):
    """start~end 날짜 1일씩"""
    if end is None:
        end = date.today().strftime("%Y%m%d")
    s, e = date.fromisoformat(f"{start[:4]}-{start[4:6]}-{start[6:]}"), date.fromisoformat(f"{end[:4]}-{end[4:6]}-{end[6:]}")
    while s <= e:
        yield s.strftime("%Y%m%d")
        s += timedelta(days=1)

def clear_tmp():
    for p in TMP_DIR.glob("*"):
        try: p.unlink()
        except: pass

def wait_download(timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        files = list(TMP_DIR.glob("*"))
        if not files:
            time.sleep(0.3)
            continue
        if not any(str(f).endswith(".crdownload") for f in files):
            return sorted(files, key=lambda x: x.stat().st_mtime)[-1]
        time.sleep(0.3)
    return None

def dismiss_alert(driver):
    try:
        alert = driver.switch_to.alert
        txt = alert.text
        alert.accept()
        print(f"⚠️ Alert 닫음: {txt}")
    except NoAlertPresentException:
        pass

# ──────────────────────────────────────────────────────────────
def main():
    opts = webdriver.ChromeOptions()
    prefs = {
        # ✅ 변경: 크롬 다운로드 폴더에 절대경로 사용(일부 환경에서 필요)
        "download.default_directory": str(TMP_DIR.resolve()),  # ✅
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    # 필요하면 헤드리스로
    # opts.add_argument("--headless=new")

    print(f"💾 저장 폴더: {DATA_DIR}")
    print(f"🗂️ 임시 폴더: {TMP_DIR}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(30)

    try:
        driver.get(SEIBRO_URL)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        dismiss_alert(driver)
        time.sleep(1)

        # 기본 설정
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, XPATH_SETTLE))).click()
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, XPATH_BUYSELL))).click()
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, XPATH_US))).click()

        start = "20241009"
        end = None
        if len(sys.argv) >= 2: start = sys.argv[1]
        if len(sys.argv) >= 3: end = sys.argv[2]

        for ymd in iter_days(start, end):
            clear_tmp()
            dst = DATA_DIR / f"re{ymd}.xls"

            print(f"\n📅 {ymd} 다운로드 중…")

            try:
                s = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, XPATH_START)))
                e = driver.find_element(By.XPATH, XPATH_END)
                s.clear(); s.send_keys(ymd)
                e.clear(); e.send_keys(ymd)
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, XPATH_QUERY))).click()
                time.sleep(2.0)
                dismiss_alert(driver)
            except Exception as ex:
                print(f"❌ {ymd} 조회 실패: {ex}")
                continue

            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, XPATH_XLS))).click()
                f = wait_download(25)
                if f:
                    shutil.move(str(f), str(dst))
                    print(f"✅ 저장 완료: {dst.name}")
                else:
                    print(f"⚠️ {ymd} 다운로드 감지 실패")
            except Exception as ex:
                print(f"❌ {ymd} 엑셀 다운로드 실패: {ex}")

    finally:
        driver.quit()
        print("\n🎉 자동 다운로드 종료!")

# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
