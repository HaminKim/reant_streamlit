# downloader.py
# 세이브로 "외국인/기관 종목별 거래내역 TOP50" 자동 다운로드 (단순화 버전)
# start~end 날짜를 다운로드하고 파일명을 reYYYYMMDD.xls로 변경 후 data 폴더에 저장
#
# 사용 예)
#   python downloader.py 20241009 20241031
#   python downloader.py 20251212 20251212
#
# GitHub Actions(ubuntu)에서도 동작하도록 경로/헤드리스/옵션 강화

from __future__ import annotations

from pathlib import Path
import time, shutil, sys, os
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException, TimeoutException
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


# ✅ repo 기준 경로 (Actions에서도 동일)
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
TMP_DIR  = BASE / "downloads_tmp"
for d in (DATA_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)


def iter_days(start: str = "20241009", end: str | None = None):
    """start~end 날짜를 1일씩(YYYYMMDD)"""
    if end is None:
        end = date.today().strftime("%Y%m%d")
    s = date.fromisoformat(f"{start[:4]}-{start[4:6]}-{start[6:]}")
    e = date.fromisoformat(f"{end[:4]}-{end[4:6]}-{end[6:]}")
    while s <= e:
        yield s.strftime("%Y%m%d")
        s += timedelta(days=1)


def clear_tmp():
    for p in TMP_DIR.glob("*"):
        try:
            p.unlink()
        except Exception:
            pass


def wait_download(timeout: int = 40):
    """
    TMP_DIR에 다운로드가 완료될 때까지 기다렸다가,
    최종 파일(Path)을 반환. 실패 시 None.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        files = list(TMP_DIR.glob("*"))
        if not files:
            time.sleep(0.3)
            continue

        # 크롬 다운로드 중 파일(.crdownload)이 남아있으면 대기
        if any(str(f).endswith(".crdownload") for f in files):
            time.sleep(0.3)
            continue

        # 가장 최근 파일 1개
        latest = sorted(files, key=lambda x: x.stat().st_mtime)[-1]
        return latest

    return None


def dismiss_alert(driver):
    try:
        alert = driver.switch_to.alert
        txt = alert.text
        alert.accept()
        print(f"⚠️ Alert 닫음: {txt}")
    except NoAlertPresentException:
        pass


def build_driver(headless: bool = True):
    opts = webdriver.ChromeOptions()

    prefs = {
        "download.default_directory": str(TMP_DIR.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    opts.add_experimental_option("prefs", prefs)

    # 공통 안정화 옵션
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")

    # ✅ Actions(리눅스)에서 자주 필요한 옵션
    # (로컬 윈도우/맥에서도 무해)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")

    if headless:
        opts.add_argument("--headless=new")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(40)
    return driver


def main():
    # ✅ 기본은 헤드리스 ON (Actions에서 안정적)
    # 로컬에서 화면 보면서 디버깅하고 싶으면:
    #   HEADLESS=0 python downloader.py ...
    headless_env = os.getenv("HEADLESS", "1").strip()
    headless = (headless_env != "0")

    start = "20241009"
    end = None
    if len(sys.argv) >= 2:
        start = sys.argv[1]
    if len(sys.argv) >= 3:
        end = sys.argv[2]

    print(f"💾 저장 폴더: {DATA_DIR}")
    print(f"🗂️ 임시 폴더: {TMP_DIR}")
    print(f"🧠 HEADLESS = {headless} (env HEADLESS={headless_env})")
    print(f"📅 기간: {start} ~ {end or date.today().strftime('%Y%m%d')}")

    driver = build_driver(headless=headless)

    try:
        driver.get(SEIBRO_URL)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        dismiss_alert(driver)
        time.sleep(1)

        # 기본 설정
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, XPATH_SETTLE))).click()
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, XPATH_BUYSELL))).click()
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, XPATH_US))).click()

        for ymd in iter_days(start, end):
            clear_tmp()
            dst = DATA_DIR / f"re{ymd}.xls"

            print(f"\n📅 {ymd} 다운로드 중…")

            # 조회
            try:
                s = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, XPATH_START))
                )
                e = driver.find_element(By.XPATH, XPATH_END)

                s.clear(); s.send_keys(ymd)
                e.clear(); e.send_keys(ymd)

                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, XPATH_QUERY))
                ).click()

                time.sleep(2.0)
                dismiss_alert(driver)

            except (TimeoutException, Exception) as ex:
                print(f"❌ {ymd} 조회 실패: {ex}")
                continue

            # 엑셀 다운로드
            try:
                WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, XPATH_XLS))
                ).click()

                f = wait_download(timeout=50)
                if f:
                    # 이미 dst가 있으면 덮어쓰기
                    if dst.exists():
                        dst.unlink()
                    shutil.move(str(f), str(dst))
                    print(f"✅ 저장 완료: {dst.name}")
                else:
                    print(f"⚠️ {ymd} 다운로드 감지 실패 (timeout)")

            except (TimeoutException, Exception) as ex:
                print(f"❌ {ymd} 엑셀 다운로드 실패: {ex}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("\n🎉 자동 다운로드 종료!")


if __name__ == "__main__":
    main()
