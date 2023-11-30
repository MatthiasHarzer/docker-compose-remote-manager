import asyncio
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from remote_manager.compose_executor import ComposeExecutor
from remote_manager.config import Config
from remote_manager.process_stdout_reader import ProcessStdoutReader
from remote_manager.ws_connection_manager import WsConnectionManager

CONFIG_FILE = os.getcwd() + "/config.json"

app = FastAPI()
ws_connection_manager = WsConnectionManager()
asyncio_loop = asyncio.get_event_loop()
log_process_reader: dict[str, ProcessStdoutReader] = {}

origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Config file {CONFIG_FILE} not found")

with open(CONFIG_FILE, "r") as f:
    cnt = json.load(f)
    config = Config.from_json(cnt)


def _get_log_process_reader(executor: ComposeExecutor) -> ProcessStdoutReader:
    service = executor.service

    def _on_close():
        # Remove dead process readers
        log_process_reader.pop(service.name)

    if service.name not in log_process_reader:
        reader = ProcessStdoutReader(executor.get_log_process())
        reader.on_close(_on_close)
        log_process_reader[service.name] = reader

    return log_process_reader[service.name]


def _authenticate(service_name: str, access_key: str) -> (bool, str | None):
    """
    Authenticate the access key.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    if not service:
        return False, f"Service {service_name} not found"
    if not service.allows(access_key):
        return False, f"Key is not authorized to access {service_name}"
    return True, None


@app.get("/status/{service_name}")
async def get_service_status(service_name: str, access_key: str = None):
    """
    Get the status of the docker compose service defined by the service_name in the config file.
    :param service_name: The service name
    :param access_key: The access key
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key)
    if not authorized:
        return {"message": message}

    compose_executor = ComposeExecutor(service)

    return compose_executor.status()


@app.post("/start/{service_name}")
async def start_service(service_name: str, access_key: str = None):
    """
    Starts the docker compose service defined by the service_name in the config file.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)

    authorized, message = _authenticate(service_name, access_key)
    if not authorized:
        return {"message": message}

    composes_executor = ComposeExecutor(service)
    composes_executor.start()

    return {"message": f"Started {service_name}"}


@app.post("/stop/{service_name}")
async def stop_service(service_name: str, access_key: str = None):
    """
    Stops the docker compose service defined by the service_name in the config file.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key)
    if not authorized:
        return {"message": message}

    compose_executor = ComposeExecutor(service)
    compose_executor.stop()

    return {"message": f"Stopped {service_name}"}


@app.get("/logs/{service_name}")
async def get_logs(service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service defined by the service_name in the config file.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key)
    if not authorized:
        return {"message": message}

    compose_executor = ComposeExecutor(service)
    lines = compose_executor.get_logs()

    return PlainTextResponse("\n".join(lines))


@app.websocket("/ws/logs/{service_name}")
async def websocket_endpoint(websocket: WebSocket, service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service defined by the service_name in the config file. Writes existing and new
    logs to the websocket.
    :param websocket:
    :param service_name:
    :param access_key:
    :return:
    """
    await ws_connection_manager.connect(websocket)

    service = config.services.get(service_name)
    if not service:
        await ws_connection_manager.send_personal_message(f"Service {service_name} not found", websocket)
        ws_connection_manager.disconnect(websocket)
        return

    if not service.allows(access_key):
        await ws_connection_manager.send_personal_message(
            f"Access key {access_key} is not authorized to get logs of {service_name}", websocket)
        ws_connection_manager.disconnect(websocket)
        return

    compose_executor = ComposeExecutor(service)
    reader = _get_log_process_reader(compose_executor)

    def _send_line(line: str):
        asyncio_loop.create_task(ws_connection_manager.send_personal_message(line, websocket))

    unregister = reader.on_read_line(_send_line, 100)

    while True:
        try:
            # Check if connection is active
            await asyncio.wait_for(websocket.receive_bytes(), timeout=1.0)
        except asyncio.TimeoutError:
            # Connection is still alive
            await asyncio.sleep(1.0)
            continue
        except WebSocketDisconnect:
            # Connection closed by client
            break
        else:
            # Received some data from the client, ignore it
            continue

    unregister()
    ws_connection_manager.disconnect(websocket)
