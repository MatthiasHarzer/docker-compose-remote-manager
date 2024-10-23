import asyncio
import json
import os
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from remote_manager.compose_parsing import ComposeLogLine
from remote_manager.compose_service import AccessKeyScope, CommandsOption
from remote_manager.config_parsing import parse_config
from remote_manager.ws_connection_manager import WsConnectionManager

CONFIG_FILE = os.getcwd() + "/config.json"

app = FastAPI()
ws_connection_manager = WsConnectionManager()
asyncio_loop = asyncio.get_event_loop()

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
    services = parse_config(cnt)


def _authenticate(service_name: str, access_key: str, scope: AccessKeyScope) -> tuple[bool, str | None]:
    """
    Authenticate the access key.
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = services.get(service_name)
    if not service:
        return False, f"Service {service_name} not found"
    if not service.allows(access_key, scope):
        return False, f"Key is not authorized to access scope {scope} of {service_name}"
    return True, None

def format_commands(commands: CommandsOption) -> dict | bool:
    if isinstance(commands, bool):
        return commands

    formatted_commands = {}

    for name, command in commands.items():
        formatted_commands[name] = {
            "label": command.label if not isinstance(command, bool) else name,
        }

    return formatted_commands

@app.get("/services")
async def get_services(access_key: str = None):
    """
    Get the services available services, accessible with the given access key.
    :param access_key: The access key
    :return:
    """

    allowed_services = []
    for service_name, service in services.items():
        if service.allows(access_key):
            allowed_services.append({
                "name": service_name,
                "scopes": service.get_access_key_allowed_scopes(access_key),
                "commands": format_commands(service.commands)
            })

    return allowed_services


@app.get("/status/{service_name}")
async def get_service_status(service_name: str, access_key: str = None):
    """
    Get the status of the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    """
    service = services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.STATUS)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    return service.running()


@app.post("/start/{service_name}")
async def start_service(service_name: str, access_key: str = None):
    """
    Starts the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = services.get(service_name)

    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.MANAGE)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    service.add_system_log_line( f"")
    service.add_system_log_line(f"Starting service '{service_name}'...")
    service.add_system_log_line(f"")

    service.start()

    return {"message": f"Started {service_name}"}


@app.post("/stop/{service_name}")
async def stop_service(service_name: str, access_key: str = None):
    """
    Stops the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.MANAGE)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    service.stop()

    service.add_system_log_line(f"")
    service.add_system_log_line(f"Stopped service '{service_name}'...")
    service.add_system_log_line(f"")

    return {"message": f"Stopped {service_name}"}


class CommandRequest(BaseModel):
    sub_service: str
    command: list[str]

@app.post("/command/{service_name}")
async def run_command(service_name: str, command_request: CommandRequest, access_key: str = None):
    """
    Run a command on the docker compose service
    :param service_name: The service name
    :param command_request: The command request
    :param access_key: The access key
    :return:
    """

    sub_service = command_request.sub_service
    command = command_request.command

    service = services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.COMMANDS)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    service.add_system_log_line(f"[{service_name}] Running command '{command}'")

    success, output = service.execute_command(sub_service, command)

    if not success:
        service.add_system_log_line(f"[{service_name}] Command failed: {output}")
    else:
        service.add_system_log_line(f"[{service_name}] Command output:\n{output}")

    return {"success": success, "output": output}

@app.get("/logs/{service_name}")
async def get_logs(service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service
    :param service_name: The service name
    :param access_key: The access key
    :return:
    """
    service = services.get(service_name)
    authorized, message = _authenticate(service_name, access_key, AccessKeyScope.LOGS)
    if not authorized:
        raise HTTPException(status_code=401, detail=message)

    return service.get_logs()


@app.websocket("/ws/logs/{service_name}")
async def ws_logs(websocket: WebSocket, service_name: str, access_key: str = None):
    """
    Get the logs of the docker compose service. Writes existing and new logs to the websocket.
    :param websocket:
    :param service_name:
    :param access_key:
    :return:
    """
    await ws_connection_manager.connect(websocket)

    service = services.get(service_name)
    if not service:
        await ws_connection_manager.send_personal_message(f"Service {service_name} not found", websocket)
        ws_connection_manager.disconnect(websocket)
        return

    if not service.allows(access_key, AccessKeyScope.LOGS):
        await ws_connection_manager.send_personal_message(
            f"Access key {access_key} is not authorized to get logs of {service_name}", websocket)
        ws_connection_manager.disconnect(websocket)
        return


    def _send_line(line: ComposeLogLine):
        if not line:
            return

        asyncio_loop.create_task(ws_connection_manager.send_personal_message(json.dumps(line), websocket))

    unregister = service.listen(_send_line)

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
