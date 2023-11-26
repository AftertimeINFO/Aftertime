import os
import django
from config import settings
import uvicorn
from asgiref.sync import async_to_sync, sync_to_async
from fastapi import FastAPI
from dotenv import load_dotenv

from pydantic import BaseModel
from version import VERSION

app = FastAPI()


load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from core.api.vehicles.ships import get_by_uuid
from core.api.structures.objects import api_ships
from fastapi import Body
from fastapi import Request

from django.conf import settings

import psutil

process = psutil.Process(os.getpid())


class ShipData(BaseModel):
    id_mt: str | int | list | dict | dict | bool | None = None
    vehicle_name: str | int | list | dict | bool | None = None
    vehicle_type: str | int | list | dict | bool | None = None
    vehicle_flag: str | int | list | dict | bool | None = None
    position_lat: str | int | list | dict | bool | None = None
    position_lon: str | int | list | dict | bool | None = None
    position_course: str | int | list | dict | bool | None = None
    position_heading: str | int | list | dict | bool | None = None
    position_speed: str | int | list | dict | bool | None = None
    sync_reverse_stamp: str | int | list | dict | bool | None = None
    sync_moment: str | int | list | dict | bool | None = None


@app.get('/ping')
async def ping():
    return f"pong v.{VERSION}"

@app.get('/api/v1/debug/memory')
async def debug_get_memory():
    return process.memory_info().rss

@app.get('/api/v1/debug/get_module_name')
async def get_param():
    return os.getenv("DJANGO_SETTINGS_MODULE")

@app.get('/api/v1/debug/get_db_configuration')
async def get_param_config():
    return settings.DATABASES

@app.post('/api/v1/back/vehicle/ship')
async def ship_operation(structure: ShipData):
    new_ship = await sync_to_async(api_ships.update_by_json)(structure.dict())
    respond = {"ship created": str(new_ship.uuid)}
    del new_ship
    return respond


if __name__ == '__main__':
    uvicorn.run('api_service:app', host='0.0.0.0', port=8000)

