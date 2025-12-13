# downloader.py
# Seibro "외국인/기관 종목별 거래내역 TOP50" 자동 다운로드
# GitHub Actions(ubuntu/headless) 안정화 버전: 오버레이(processbar) 대기 + 안전 클릭 + headless 옵션

from pathlib import Path
import time, shutil, sys
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException, TimeoutException, ElementClickInterceptedException
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

# ✅ 오버레이(프로세스바) — 클릭을 가로채는 w2modal
CSS_OVERLAY = "div.w2modal"

# ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
TMP_DIR  = BASE / "downloads_tmp"
for d in (DATA_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

def iter_days(start="20241009", end=None):
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

def wait_download(timeout=35):
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

def wait_overlay_gone(driver, timeout=25):
    """Seibro(WebSquare) 로딩/처리 오버레이(w2modal)가 사라질 때까지 대기"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: all(not el.is_displayed() for el in d.find_elements(By.CSS_SELECTOR, CSS_OVERLAY))
        )
    except TimeoutException:
        # 계속 떠있어도 다음 시도를 해보긴 하되, 로그는 남김
        print("⚠️ 오버레이가 오래 남아있음(Timeout). 그래도 계속 진행 시도.")

def safe_click(driver, by, selector, timeout=25):
    """
    1) 오버레이가 사라질 때까지 기다림
    2) 일반 클릭 시도
    3) 막히면(JS overlay 등) 스크롤 + JS 클릭으로 fallback
    """
    wait_overlay_gone(driver, timeout=timeout)
    el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
    try:
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector))).click()
        return
    except ElementClickInterceptedException:
        pass
    except Exception:
        pass

    # fallback: scroll + JS click
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        wait_overlay_gone(driver, timeout=timeout)
        driver.execute_script("arguments[0].click();", el)
    except Exception as e:
        raise RuntimeError(f"safe_click 실패: {selector} -> {e}") from e

# ──────────────────────────────────────────────────────────────
def main():
    # ✅ Actions에서는 env HEADLESS=1로 실행 중이었지?
    headless_env = (str(sys.environ.get("HEADLESS", "1")) if hasattr(sys, "environ") else "1")
    # 위 줄이 깨질 수 있어서 안전하게 다시:
    try:
        import os
        headless = os.getenv("HEADLESS", "1") == "1"
    except Exception:
        headless = True

    opts = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": str(TMP_DIR.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    opts.add_experimental_option("prefs", prefs)

    # ✅ GitHub Actions(ubuntu) 안정화 옵션
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")

    print(f"💾 저장 폴더: {DATA_DIR}")
    print(f"🗂️ 임시 폴더: {TMP_DIR}")
    print(f"🧠 HEADLESS = {headless} (env HEADLESS=1)")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(60)

    try:
        driver.get(SEIBRO_URL)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        dismiss_alert(driver)
        wait_overlay_gone(driver, timeout=30)
        time.sleep(1)

        # 기본 설정(오버레이/클릭 가로채기 대응)
        safe_click(driver, By.XPATH, XPATH_SETTLE,  timeout=30)
        safe_click(driver, By.XPATH, XPATH_BUYSELL, timeout=30)
        safe_click(driver, By.XPATH, XPATH_US,      timeout=30)

        start = "20241009"
        end = None
        if len(sys.argv) >= 2:
            start = sys.argv[1]
        if len(sys.argv) >= 3:
            end = sys.argv[2]

        print(f"📅 기간: {start} ~ {end or start}")

        for ymd in iter_days(start, end):
            clear_tmp()
            dst = DATA_DIR / f"re{ymd}.xls"

            print(f"\n📥 {ymd} 다운로드 중…")

            try:
                wait_overlay_gone(driver, timeout=25)
                s = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, XPATH_START)))
                e = driver.find_element(By.XPATH, XPATH_END)
                s.clear(); s.send_keys(ymd)
                e.clear(); e.send_keys(ymd)

                safe_click(driver, By.XPATH, XPATH_QUERY, timeout=30)
                time.sleep(2.0)
                dismiss_alert(driver)
                wait_overlay_gone(driver, timeout=30)
            except Exception as ex:
                print(f"❌ {ymd} 조회 실패: {ex}")
                continue

            try:
                safe_click(driver, By.XPATH, XPATH_XLS, timeout=30)
                f = wait_download(35)
                if f:
                    shutil.move(str(f), str(dst))
                    print(f"✅ 저장 완료: {dst.name}")
                else:
                    print(f"⚠️ {ymd} 다운로드 감지 실패")
            except Exception as ex:
                print(f"❌ {ymd} 엑셀 다운로드 실패: {ex}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("\n🎉 자동 다운로드 종료!")

if __name__ == "__main__":
    main()
