import requests
import json

url= "http://localhost:8000/api/v1/back/ping"
r = requests.get(url)
print(r)


url = "http://localhost:8000/api/v1/back/vehicle/ship"
data = {
    "id_mt": "349753",
    "vehicle_name": "MEIKE",
    "vehicle_type": "7",
    "vehicle_flag": "PA",
    "position_lat": "45.34703",
    "position_lon": "28.97601",
    "position_course": "80",
    "position_heading": "216",
    "position_speed": "0",
    "sync_moment": "2023-09-17 12:49:03.186179"
}


# headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
headers = {'Content-type': 'application/json', 'Accept': 'application/xml'}
r = requests.post(url, json=json.dumps(data))

# r = requests.post(url, data=json.dumps(data), headers=headers)
pass
print(r)