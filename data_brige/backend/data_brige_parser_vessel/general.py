# ----------------- STANDARD -----------------
import time
# ----------------- EXTERNAL -----------------
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service

import chromedriver_autoinstaller

def sel_connection():
    chrome_options = webdriver.ChromeOptions()

    # chrome_options.add_argument("--headless")
    # chrome_options.add_argument("--disable-extensions")
    # chrome_options.add_argument("--disable-popup-blocking")
    # chrome_options.add_argument("--profile-directory=Default")
    # chrome_options.add_argument("--ignore-certificate-errors")
    # chrome_options.add_argument("--disable-plugins-discovery")
    # chrome_options.add_argument("--incognito")
    # chrome_options.add_argument("--user_agent=DN")
    chrome_options.add_argument('--no-first-run')
    chrome_options.add_argument('--no-service-autorun')
    chrome_options.add_argument('--password-store=basic')
    chrome_options.add_argument("--start-maximized")

    # chrome_options.add_argument('--ignore-ssl-errors=yes')
    # chrome_options.add_argument('--ignore-certificate-errors')

    # chrome_options.add_argument(f"--user-data-dir=e:\Farm\A{FARM_NUMBER}")
    # chrome_options.add_argument("--profile-directory=PROFILE")

    chrome_options.add_argument("--disable-infobars")
    # chrome_options.add_argument(f'--proxy-server={PROXY_HOST}:{PROXY_PORT}')
    chrome_options.add_argument('--enable-logging')
    chrome_options.add_argument('--log-level=0')

    # ---------------------------------------
    # capabilities = DesiredCapabilities.CHROME
    # capabilities["goog:loggingPrefs"] = {"performance": "ALL"}
    # chrome_options.AddAdditionalCapability("goog:loggingPrefs", {"performance": "ALL"});

    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    # service_obj = Service(r"d:\FILES\Bukovel\OneDrive\Projects\Aftertime\Development\BackEND\parser_vessel\utility\cd\119_chromedriver.exe")
    # driver = webdriver.Chrome(options=chrome_options,
    #                           service=service_obj)
    chromedriver_autoinstaller.install()
    driver = webdriver.Chrome(options=chrome_options)

    time.sleep(2)

    return driver