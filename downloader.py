from pathlib import Path
import time
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921"

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def main():

    # 어제 날짜
    ymd = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

    print("다운로드 날짜:", ymd)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    wait = WebDriverWait(driver, 20)

    driver.get(URL)

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(2)

    driver.find_element(By.XPATH, '//*[@id="a1_radio1_input_0"]').click()
    driver.find_element(By.XPATH, '//*[@id="area_radio_2_input_2"]').click()
    driver.find_element(By.XPATH, '//*[@id="area_radio_input_1"]').click()

    start = driver.find_element(By.XPATH, '//*[@id="sd1_inputCalendar1_input"]')
    end = driver.find_element(By.XPATH, '//*[@id="sd1_inputCalendar2_input"]')

    start.clear()
    start.send_keys(ymd)

    end.clear()
    end.send_keys(ymd)

    driver.find_element(By.XPATH, '//*[@id="image2"]').click()

    time.sleep(6)

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

    html = "<table><thead><tr><th>종목명</th><th>매수</th><th>매도</th></tr></thead><tbody>"

    for name, buy, sell in data:
        html += f"<tr><td>{name}</td><td>{buy}</td><td>{sell}</td></tr>"

    html += "</tbody></table>"

    dst = DATA_DIR / f"re{ymd}.xls"

    if dst.exists():
        dst.unlink()

    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)

    print("저장 완료:", dst)

    driver.quit()


if __name__ == "__main__":
    main()
