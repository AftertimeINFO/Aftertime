# region Standard libraries
import requests
import time
import json
import pprint
from datetime import datetime
# endregion

# region External libraries
from selenium import webdriver
from selenium.webdriver.common.by import By
# endregion

# region Project internal libraries
import general
from vehicle import Vehicle
# endregion

# SYNC_HOST_NAME = "localhost:8000"
SYNC_HOST_NAME = "front.api.aftertime"

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
    error_message = f'\n{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}: {comment}'
    print(bcolors.FAIL + error_message + bcolors.ENDC)
    with open('log.txt', 'a') as f:
        f.write(error_message)


class MapOperationsTypes:
    INITIALIZE = 0;
    MOVE = 1;
    SENDING = 3;
    CHECK = 5;
    CHECK = 5;


    def __init__(self):
        pass


def url_parse(url: str):
    lon_str = url[url.find("centerx")+8:]
    lon = float(lon_str[:lon_str.find("/")])

    lat_str = lon_str[lon_str.find("centery") + 8:]
    lat = float(lat_str[:lat_str.find("/")])

    zoom_str = lat_str[lat_str.find("zoom") + 5:]
    zoom = int(zoom_str)

    return {
        'lat': lat,
        'lon': lon,
        'zoom': zoom
    }


class Operation:
    __slots__ = (
        'structure',
        'map_operations'
    )

    def __init__(self, structure: dict, map_operations: "MapOperationsList"):
        self.structure = structure
        self.map_operations = map_operations

    def get_dict(self):
        return self.structure

    def __str__(self):
        return json.dumps(self.structure)

    def _renew_posision(self):
        # renew_operation
        if self.map_operations.renew_operation is True:
            url_structure = url_parse(self.map_operations.driver.current_url)
            if ((self.structure["direction_condition"] is None and self.map_operations.direction == 1) or
                (self.structure["direction_condition"] == self.map_operations.direction == 1)):
                self.structure["lat"] = url_structure["lat"]
                self.structure["lon"] = url_structure["lon"]
                self.structure["zoom"] = url_structure["zoom"]

        pass

    def _check_fix_position(self):
        if self.structure["checking"] is True:
            if self.map_operations.direction == 1:
                url_structure = url_parse(self.map_operations.driver.current_url)
                if (abs(self.structure["lat"] - url_structure["lat"]) > 0.01*(20-url_structure["zoom"])*(20-url_structure["zoom"]) or
                        abs(self.structure["lon"] - url_structure["lon"]) > 0.01*(20-url_structure["zoom"])*(20-url_structure["zoom"]) or
                            self.structure["zoom"] != url_structure["zoom"]):
                    self.map_operations.open_position(self.structure['lat'], self.structure['lon'], self.structure['zoom'])
                    write_log(f"Incorrect position on iteration {self.map_operations._position+1} on passage {self.map_operations.passage_id}: "
                              f"lat need {self.structure['lat']} cur {url_structure['lat']} "
                              f"lon need {self.structure['lon']} cur {url_structure['lon']} "
                              f"zoom need {self.structure['zoom']} cur {url_structure['zoom']}"
                              )

    def execute(self):
        driver = self.map_operations.driver
        map_element = self.map_operations.map_element
        direction = self.map_operations.direction
        vehicles = self.map_operations.vehicles
        initialized = self.map_operations.initialized

        if initialized is None or initialized is False and self.structure["operation_type"] != 0:
            write_log("ERROR: Can't do operation without initialization.");
            raise Exception("Can't do operation without initialization.")

        if self.structure["operation_type"] == 0 and self.map_operations.initialized is False:
            self.map_operations.open_position(self.structure['lat'], self.structure['lon'], self.structure['zoom'])
            self.map_operations.initialized = True
            self.map_operations.grab_data()
        elif self.structure["operation_type"] == 1:
            x = self.structure["x"]*direction
            y = self.structure["y"]*direction
            # time.sleep(2)
            action = webdriver.ActionChains(driver)

            make_action = action.click_and_hold(map_element)
            make_action.perform()
            try:
                action.move_by_offset(x, y).perform()
            except Exception as e:
                print("Error on MOVE to: ", x, y)
            else:
                print("Moving (x,y)", x, y)
            finally:
                action.release().perform()

            time.sleep(1)

            self._renew_posision()
            self._check_fix_position()
            self.map_operations.grab_data()
        elif self.structure["operation_type"] == 2:
            z = self.structure["z"] * direction
            print("Zooming %i" % z)
            if z > 0:
                button_zoom = driver.find_element(By.CLASS_NAME, "leaflet-control-zoom-in")
            else:
                button_zoom = driver.find_element(By.CLASS_NAME, "leaflet-control-zoom-out")
            # ==================================
            if z < 0:
                step_range = z * -1
            else:
                step_range = z
            # ==================================
            for i in range(step_range):
                button_zoom.click()
                time.sleep(1)

            self._check_fix_position()
            self.map_operations.grab_data()
        elif self.structure["operation_type"] == 3:
            print('Start of sending')
            if self.structure["direction_condition"] is None or self.structure["direction_condition"] == direction:
                import concurrent.futures as lib_cf

                def sent_to_server(input_json, exec_info):
                    print("", end=exec_info)
                    url = f"http://{SYNC_HOST_NAME}/api/v1/back/vehicle/ship"
                    r = requests.post(url, json=json.loads(input_json))

                with lib_cf.ThreadPoolExecutor(max_workers=200) as executor:
                    elem_i = 1
                    for ship_id, ship_data in vehicles.items():

                        executor.submit(sent_to_server, ship_data.get_json(), f"\rSending {elem_i}/{len(vehicles.items())} element")
                        # print(f"Sending {elem_i}/{len(vehicles.items())} element")
                        elem_i += 1

                vehicles = []
            print('End of sending')
        elif self.structure["operation_type"] == 4:
            time.sleep(self.structure["delay"])
        elif self.structure["operation_type"] == 5:
            pass
        elif self.structure["operation_type"] == 6:
            self.map_operations.vehicles = {}


class MapOperationsList:
    configuration = {
        'first_load_pause': 10
    }
    # region Standard
    __slots__ = (
        'operations',
        'direction',
        'direction_next',
        'passage_id',
        'passage_id_next',
        '_position',
        'vehicles',
        'one_passage_inter',
        'renew_operation',
        'driver',
        'map_element',
        'initialized',
    )

    def __iter__(self):
        self._position = 0
        self.passage_id = 1
        self.direction = 1
        return self

    def __next__(self):
        if self.direction_next is not None:
            self.direction = self.direction_next
            self.direction_next = None
        if self.passage_id_next is not None:
            self.passage_id = self.passage_id_next
            self.passage_id_next = None

        if self.passage_id > 1 and self.one_passage_inter is True:
            self.one_passage_inter = False
            if self.renew_operation is not None:
                self.renew_operation = None
            raise StopIteration

        if len(self.operations) == 0:
            raise StopIteration

        self._position += 1*self.direction

        if len(self.operations) <= self._position or (self._position == 0 and self.passage_id > 1):
            self.direction_next = self.direction*-1
            self.passage_id_next = self.passage_id+1

        return Operation(self.operations[self._position-1], self)

    def __init__(self):
        self.operations = []
        self._position = None
        self.direction = 1
        self.direction_next = None
        self.passage_id = 0
        self.passage_id_next = None
        self.vehicles = {}
        self.one_passage_inter = False
        self.renew_operation = None
        self.initialized = False
        self.map_element = None
        self.driver = None
    # endregion

    def close_driver(self):
        if self.driver is not None:
            try:
                self.driver.close()
            except BaseException as e:
                pass
        self.driver = None

    def initialize(self, full=True, reload=True):
        if full is True:
            if self.driver is None:
                self.driver = general.sel_connection()
        if len(self.operations) == 0 or reload is True:
            self.load_trace()

    def open_position(self, lat, lon, zoom):
        self.driver.get(f"https://www.marinetraffic.com/en/ais/home/centerx:{lon}/centery:{lat}/zoom:{zoom}")
        time.sleep(3)
        try:
            agree_button = self.driver.find_element(By.XPATH, "//div[@class='qc-cmp2-summary-buttons']/button[@mode='primary']")
        except:
            agree_button = None
        if agree_button is not None:
            time.sleep(1)
            agree_button.click()
            time.sleep(self.configuration['first_load_pause'])
        else:
            time.sleep(1)
        self.map_element = self.driver.find_element(By.ID, "map_canvas")


    @property
    def inter_one_passage(self):
        self.one_passage_inter = True
        return iter(self)

    @property
    def inter_renew(self):
        self.one_passage_inter = True
        self.renew_operation = True
        return iter(self)


    def grab_data(self):
        driver = self.driver
        logs_raw = driver.get_log("performance")

        # logs_raw = driver.get_log("browser")

        logs = [json.loads(lr["message"])["message"] for lr in logs_raw]
        vehicle_map_elements = []

        # print(logs_raw)

        # def log_filter(log_):
        #     return (
        #         # is an actual response
        #             log_["method"] == "Network.responseReceived"
        #             # and json
        #             and "json" in log_["params"]["re`sponse"]["mimeType"]
        #     )

        for log in logs:
            try:
                request_id = log["params"]["requestId"]
                resp_url = log["params"]["response"]["url"]

                moment_generation = log["params"]["response"]["headers"]["last-modified"]
                mg_datetime = datetime.strptime(moment_generation[0:-4], "%a, %d %b %Y %H:%M:%S")

                if (resp_url.endswith("station:0")):
                    # print(f"Caught {resp_url}")
                    content = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                    content_body = json.loads(content['body'])
                    content_body["moment"] = mg_datetime

                    if (len(content_body['data']['rows']) > 0):
                        vehicle_map_elements.append(content_body)
            except:
                pass

        for cur_map_element in vehicle_map_elements:
            for cur_vehicle in cur_map_element['data']['rows']:
                ship_id = cur_vehicle['SHIP_ID']

                if ship_id.isnumeric():
                    new_vehicle = Vehicle(
                        id=cur_vehicle['SHIP_ID'],
                        name=cur_vehicle['SHIPNAME'],
                        type=cur_vehicle['SHIPTYPE'],
                        flag=cur_vehicle['FLAG'],
                        lat=cur_vehicle['LAT'],
                        lon=cur_vehicle['LON'],
                        course=cur_vehicle['COURSE'],
                        heading=cur_vehicle['HEADING'],
                        speed=cur_vehicle['SPEED'],
                        load_moment=cur_map_element['moment'],
                        sync_elapsed=cur_vehicle['ELAPSED']
                    )

                    if str(new_vehicle.id_mt) not in self.vehicles:
                        self.vehicles[str(new_vehicle.id_mt)] = new_vehicle
                    else:
                        if self.vehicles[str(new_vehicle.id_mt)].sync_moment < new_vehicle.sync_moment:
                            self.vehicles[str(new_vehicle.id_mt)] = new_vehicle
                        else:
                            pass

                    # print('ID',new_vehicle.id_mt)
                    # print("rows:", len(cur_vehicle['data']['rows']))
                    # print(cur_vehicle)
                else:
                    # TODO Hidden ship
                    pass
        print(f"Log contains {len(logs_raw)} lines. "
              f"Total log vehicles: {len(vehicle_map_elements)}. "
              f"Number of vehicles:{len(self.vehicles.items())}.")

    def load_trace(self, file_name='trace.json'):
        self.operations = []
        with open(file_name, 'r') as f:
            jso_str = f.read()
            self.json_load(jso_str)

    def save_trace(self, file_name='trace.json'):
        json_str = self.get_json()
        with open(file_name, 'w') as f:
            f.write(pprint.pformat(json_str, compact=True).replace("'", "").replace('(', '').replace(')', ''))

    def json_load(self, json_str):
        preload_operation = json.loads(json_str)
        for cur_operation in preload_operation:
            if 'checking' not in cur_operation:
                cur_operation['checking'] = False
            elif cur_operation['checking'] is None:
                cur_operation['checking'] = False
        self.operations = preload_operation

    def append_operation(self,
                         operation_type,
                         x=None,
                         y=None,
                         z=None,
                         direction_condition=None,
                         delay=None,
                         lat=None,
                         lon=None,
                         zoom=None,
                         checking=None,
                         **kwargs
                         ):
        self.operations.append(
            self._get_operation_dict(
                operation_type=operation_type,
                x=x,
                y=y,
                z=z,
                direction_condition=direction_condition,
                delay=delay,
                lat=lat,
                lon=lon,
                zoom=zoom,
            )
        )
        pass

    def _get_operation_dict(self,
                            operation_type,
                            x=None,
                            y=None,
                            z=None,
                            direction_condition=None,
                            delay=None,
                            lat=None,
                            lon=None,
                            zoom=None,
                            checking=None,
                            ):
        return {
            'operation_type': operation_type,
            'x': x,
            'y': y,
            'z': z,
            'direction_condition': direction_condition,
            'delay': delay,
            'lat': lat,
            'lon': lon,
            'zoom': zoom,
            'checking': checking
        }

    def get_json(self):
        json_str = json.dumps(self.operations)
        return json_str
