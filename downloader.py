from pathlib import Path
import sys
import io
import time
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    WebDriverException,
    TimeoutException,
)
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921"

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 종료 코드 규약
#   0 = 정상 저장
#   2 = 데이터 없음 (휴장일 또는 아직 미공시) → 워크플로우는 실패로 보지 않고 다음 실행에서 재시도
#   1 = 기술적 실패 (네트워크/셀레늄 오류가 재시도 후에도 지속) → 워크플로우 실패로 표시
EXIT_OK = 0
EXIT_NO_DATA = 2
EXIT_TECH_FAIL = 1

# driver.get / 스크래핑 자체를 몇 번까지 다시 시도할지
SCRAPE_RETRIES = 3
RETRY_BACKOFF_SEC = 8

# Seibro 해외주식 보고서는 상위 ~50종목. 이보다 적게 잡히면
# 그리드가 덜 그려진 상태에서 긁힌 '부분 스크랩'으로 보고 재시도한다.
MIN_VALID_ROWS = 10
# 조회 버튼 클릭 후 결과 그리드가 채워질 때까지 최대 대기(초)
RESULT_WAIT_SEC = 30


def click_safe(driver, wait, xpath, retries=5):
    """WebSquare 로딩 오버레이(__processbarIFrame)가 클릭을 가로채는 경우가 있어
    오버레이가 사라질 때까지 기다렸다가 클릭, 그래도 가로채이면 재시도."""
    for attempt in range(retries):
        try:
            wait.until(EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "iframe[name='__processbarIFrame']")))
            el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            el.click()
            return
        except ElementClickInterceptedException:
            if attempt == retries - 1:
                raise
            time.sleep(1)


def set_date_js(driver, element_id, ymd):
    """send_keys 대신 JS로 값 세팅 + 이벤트 발생 (캘린더 위젯 정상 인식)"""
    driver.execute_script("""
        var el = document.getElementById(arguments[0]);
        el.value = arguments[1];
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('blur',   {bubbles: true}));
    """, element_id, ymd)


def _new_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.page_load_strategy = "eager"
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)
    return driver


def scrape_once(ymd):
    """1회 시도. 성공 시 [(name, buy, sell), ...] 반환, 데이터가 비어 있으면 [] 반환.
    네트워크/셀레늄 오류는 예외를 그대로 올려서 상위 재시도 루프가 처리하게 한다."""
    driver = _new_driver()
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        click_safe(driver, wait, '//*[@id="a1_radio1_input_0"]')
        click_safe(driver, wait, '//*[@id="area_radio_2_input_2"]')
        click_safe(driver, wait, '//*[@id="area_radio_input_1"]')

        set_date_js(driver, "sd1_inputCalendar1_input", ymd)
        set_date_js(driver, "sd1_inputCalendar2_input", ymd)

        click_safe(driver, wait, '//*[@id="image2"]')

        # 고정 sleep 대신 결과 그리드가 채워질 때까지 폴링.
        # 행 수가 2회 연속 같고 MIN_VALID_ROWS 이상이면 렌더 완료로 본다.
        def row_count():
            return len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

        deadline = time.time() + RESULT_WAIT_SEC
        prev = -1
        time.sleep(3)
        while time.time() < deadline:
            cur = row_count()
            if cur >= MIN_VALID_ROWS and cur == prev:
                break
            prev = cur
            time.sleep(2)

        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        data = []
        for r in rows:
            cols = r.find_elements(By.TAG_NAME, "td")
            if len(cols) < 6:
                continue
            name = cols[3].text
            buy = cols[4].text
            sell = cols[5].text
            if name.strip() == "":
                continue
            data.append((name, buy, sell))
        return data
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scrape_with_retry(ymd):
    """일시적 오류(ERR_CONNECTION_RESET, timed out 등)와 부분 스크랩은 백오프 후 재시도.
    반환: rows 리스트([]이면 '데이터 없음', 그 외엔 MIN_VALID_ROWS 이상 보장).
    재시도 소진 시 RuntimeError."""
    last_err = None
    for attempt in range(1, SCRAPE_RETRIES + 1):
        try:
            data = scrape_once(ymd)
            if data and len(data) < MIN_VALID_ROWS:
                last_err = f"부분 스크랩 ({len(data)}행 < {MIN_VALID_ROWS})"
                print(f"  ⚠️ 시도 {attempt}/{SCRAPE_RETRIES}: {last_err}")
                if attempt < SCRAPE_RETRIES:
                    time.sleep(RETRY_BACKOFF_SEC * attempt)
                    continue
                raise RuntimeError(f"{ymd}: {last_err} — 재시도 후에도 지속")
            return data
        except (WebDriverException, TimeoutException) as e:
            last_err = e
            msg = str(e).splitlines()[0] if str(e) else e.__class__.__name__
            print(f"  ⚠️ 시도 {attempt}/{SCRAPE_RETRIES} 실패: {msg}")
            if attempt < SCRAPE_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise RuntimeError(f"{ymd}: {SCRAPE_RETRIES}회 재시도 후에도 실패 ({last_err})")


def save(ymd, data):
    html = "<table><thead><tr><th>종목명</th><th>매수</th><th>매도</th></tr></thead><tbody>"
    for name, buy, sell in data:
        html += f"<tr><td>{name}</td><td>{buy}</td><td>{sell}</td></tr>"
    html += "</tbody></table>"

    dst = DATA_DIR / f"re{ymd}.xls"
    if dst.exists():
        dst.unlink()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 저장 완료: {dst} ({len(data)}개 종목)")


def main():
    # 워크플로우에서 날짜 인자를 받음. 없으면 어제로 fallback
    ymd = sys.argv[1] if len(sys.argv) >= 2 else (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    print("다운로드 날짜:", ymd)

    try:
        data = scrape_with_retry(ymd)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(EXIT_TECH_FAIL)

    if not data:
        print(f"↷ {ymd} 데이터 없음 (휴장일 또는 아직 미공시) — 다음 실행에서 재시도")
        sys.exit(EXIT_NO_DATA)

    save(ymd, data)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
