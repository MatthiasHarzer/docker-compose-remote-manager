import asyncio
import json
import os
import re
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from remote_manager.compose_executor import ComposeExecutor
from remote_manager.config import Config, AccessKeyScope
from remote_manager.compose_process_stdout_reader import ComposeProcessStdoutReader
from remote_manager.util import parse_compose_log_lines, parse_compose_log_line, ParsedComposeLogLine
from remote_manager.ws_connection_manager import WsConnectionManager

CONFIG_FILE = os.getcwd() + "/config.json"

app = FastAPI()
ws_connection_manager = WsConnectionManager()
asyncio_loop = asyncio.get_event_loop()
log_process_reader: dict[str, ComposeProcessStdoutReader] = {}

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

logs_cache: dict[str, list[ParsedComposeLogLine]] = {}

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Config file {CONFIG_FILE} not found")

with open(CONFIG_FILE, "r") as f:
    cnt = json.load(f)
    config = Config.from_json(cnt)


def _get_log_process_reader(executor: ComposeExecutor) -> ComposeProcessStdoutReader:
    service = executor.service

    def _on_close():
        # Remove dead process readers
        log_process_reader.pop(service.name)

    if service.name not in log_process_reader:
        reader = ComposeProcessStdoutReader(executor.get_log_process())
        reader.on_close(_on_close)
        log_process_reader[service.name] = reader

    return log_process_reader[service.name]


def _authenticate(service_name: str, access_key: str, scope: AccessKeyScope) -> (bool, str | None):
    """
    Authenticate the access key.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    if not service:
        return False, f"Service {service_name} not found"
    if not service.allows(access_key, scope):
        return False, f"Key is not authorized access scope {scope} of {service_name}"
    return True, None


def _add_system_log_line(service_name: str, line: str) -> None:
    now = datetime.now()
    parsed = ("system", now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), f"{line}")
    compose_executor = ComposeExecutor(config.services.get(service_name))
    line_reader = _get_log_process_reader(compose_executor)
    line_reader.add_system_log_line(parsed)



@app.get("/services")
async def get_services(access_key: str = None):
    """
    Get the services available services, accessible with the given access key.
    :param access_key: The access key
    :return:
    """

    allowed_services = []
    for service_name, service in config.services.items():
        if service.allows(access_key):
            allowed_services.append({
                "name": service_name,
                "scopes": service.get_access_key_allowed_scopes(access_key)
            })

    return allowed_services


@app.get("/status/{service_name}")
async def get_service_status(service_name: str, access_key: str = None):
    """
    Get the status of the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.STATUS)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    compose_executor = ComposeExecutor(service)

    return compose_executor.status()


@app.post("/start/{service_name}")
async def start_service(service_name: str, access_key: str = None):
    """
    Starts the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)

    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.MANAGE)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    _add_system_log_line(service_name, f"")
    _add_system_log_line(service_name, f"Starting {service_name}...")
    _add_system_log_line(service_name, f"")

    composes_executor = ComposeExecutor(service)
    composes_executor.start()



    return {"message": f"Started {service_name}"}


@app.post("/stop/{service_name}")
async def stop_service(service_name: str, access_key: str = None):
    """
    Stops the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.MANAGE)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    compose_executor = ComposeExecutor(service)
    compose_executor.stop()

    _add_system_log_line(service_name, f"")
    _add_system_log_line(service_name, f"Stopped {service_name}...")
    _add_system_log_line(service_name, f"")

    return {"message": f"Stopped {service_name}"}


@app.get("/logs/{service_name}")
async def get_logs(service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = config.services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.LOGS)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    compose_executor = ComposeExecutor(service)

    if not compose_executor.status() and service_name in logs_cache:
        return sorted(set(logs_cache[service_name]), key=lambda x: x[1])

    lines = compose_executor.get_logs()

    logs_cache[service_name] = parse_compose_log_lines(lines)

    return sorted(set(logs_cache[service_name]), key=lambda x: x[1])


@app.websocket("/ws/logs/{service_name}")
async def websocket_endpoint(websocket: WebSocket, service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service. Writes existing and new logs to the websocket.
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

    if not service.allows(access_key, AccessKeyScope.LOGS):
        await ws_connection_manager.send_personal_message(
            f"Access key {access_key} is not authorized to get logs of {service_name}", websocket)
        ws_connection_manager.disconnect(websocket)
        return

    compose_executor = ComposeExecutor(service)
    reader = _get_log_process_reader(compose_executor)

    def _send_line(line: ParsedComposeLogLine):

        if not line:
            return

        if service_name not in logs_cache:
            logs_cache[service_name] = []

        logs_cache[service_name].append(line)

        if len(logs_cache[service_name]) > 250:
            logs_cache[service_name] = logs_cache[service_name][-250:]

        asyncio_loop.create_task(ws_connection_manager.send_personal_message(json.dumps(line), websocket))

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
