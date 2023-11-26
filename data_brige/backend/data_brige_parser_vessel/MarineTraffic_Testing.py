# region Standard libraries
import json
import os
import urllib.parse
import zipfile
import signal
import random
import time
import os
import sys
from datetime import datetime
# endregion

# region External libraries
# import undetected_chromedriver.v2 as uc
from selenium import webdriver
from selenium.webdriver import Remote
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# from langdetect import detect, DetectorFactory
# endregion

# region Project internal libraries
import general
# from mt_operations.map.mt_map_operations import MapOperation
from mt_operations.map.mt_map_operations import MapOperationsList
from mt_operations.map.mt_map_operations import MapOperationsTypes
# endregion

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def write_log(comment):
    with open('log.txt', 'a') as f:
        f.write(f'\n{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}: {comment}')


write_log(f'----------------Run script on {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}----------------')

# with open("config.json", "r", encoding='utf-8-sig') as openfile:
#     config = json.load(openfile)
#
# PROXY_HOST = config['PROXY_HOST']
# PROXY_PORT = config['PROXY_PORT']
# try:
#     PROXY_USER = config['PROXY_USER']
#     PROXY_PASSWORD = config['PROXY_PASSWORD']
# except:
#     PROXY_USER = None
#     PROXY_PASSWORD = None
#
# FARM_NUMBER = config['FARM_NUMBER']


# region >> Load trace from file >>


# endregion

# driver = general.sel_connection()
# driver.get('https://www.marinetraffic.com/en/ais/home/centerx:28.879/centery:45.313/zoom:13')
# time.sleep(5)

# region Accept cucies
# agree_button = driver.find_element(By.XPATH, "//div[@class='qc-cmp2-summary-buttons']/button[@mode='primary']")
# agree_button.click()
# time.sleep(2)
# endregion

# map_element = driver.find_element(By.ID, "map_area")
# executing = True


# def handler(signum, frame):
#     res = input("Ctr-C was pressed. Do you really want to exit? y/n ")
#     if res == 'y':
#         raise Exception("Ctr-C exception.")
#         # exit(1)


MOL = MapOperationsList()
try:
    # signal.signal(signal.SIGINT, handler)

    def list_operation():
        MOL.initialize(False, False)
        list_id = 1
        for cur_step in MOL.inter_one_passage:
            print(f"{list_id}:", cur_step.get_dict())
            list_id += 1


    input_data = ""
    while input_data != "e" and input_data != "s":
        input_data = input("(s-start, sv-save, b-back, r-repeat, zi/zo-zoom in/out,"
                           "l-list,  a-append, cr-Coordinates renew, e-exit):")

        if input_data == "l":
            list_operation()
        elif input_data == 'sv':
            MOL.save_trace()
        elif input_data == 'cr':
            MOL.initialize(True, False)
            i = 1
            for cur_step in MOL.inter_renew:
                print(f"operation {i}")
                cur_step.execute()
                i += 1
                # print(f"{list_id}:", cur_step.get_dict())
                # list_id += 1
        elif input_data == "a":
            input_second = ""
            while input_second != "g":
                list_operation()
                input_second = input("Select Type of operation (g-go back, sv-save, "
                                     "0-Initialization, 1-Move, 6-clear vehicles)")

                if input_second == '1':
                    try:
                        input_operation = input("Movement x,y:")
                        (x, y) = input_operation.split(",")
                        check = input("Make check (yes,no) [no-default]:")
                        if check.lstrip("w.") == "":
                            check = 0
                        elif check == "yes":
                            check = True
                        elif check == "no":
                            check = False

                        MOL.append_operation(operation_type=int(input_second), x=int(x), y=int(y), checking=check)
                    except BaseException as e:
                        print(bcolors.WARNING + "Incorrect data format."+ bcolors.ENDC)
                        time.sleep(5)
                elif input_second == '6':
                    try:
                        input_operation = input("Direction (1-front,-1-back) [1-default]:")
                        if input_operation.lstrip("w.") == "":
                            direction = 1
                        else:
                            direction = int(input_operation)

                        MOL.append_operation(operation_type=int(input_second), direction_condition=direction)
                    except BaseException as e:
                        print(bcolors.WARNING + "Incorrect input." + bcolors.ENDC)
                        time.sleep(5)
                elif input_second == 'sv':
                    MOL.save_trace()

    if input_data == "s":

        end_less_circle = True

        while end_less_circle:
            try:
                MOL.initialize()

                circle_start = time.time()
                for cur_step in MOL:
                    cur_step.execute()
            except BaseException as e:
                print(f"Error: {e}")
                MOL.close_driver()


except BaseException as e:
    print("Exception: ", e)
finally:
    MOL.close_driver()
    print(f'----------------End script on {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}----------------)')
