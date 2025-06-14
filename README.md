# Docker Compose Remote Management API

This is a very simple API to manage Docker compose applications via HTTP requests and receive logs via WebSockets.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

- Clone the repository
- Create a virtual environment using `python -m venv venv` (python 3.12+ is required)
- Activate the virtual environment using `source venv/bin/activate`
- Install the dependencies using `pip install -r requirements.txt`
- Create a `config.json` file in the projects root directory. See the [config.json](#configuring-the-api) section for more information.
- Run the API using the `start.sh` script
  - It may be required to make the script executable using `chmod +x start.sh`
- The API should now run on port `9090`

To set up a system-wide service, you can use the `compose-remote-manager.service`-unit-file-template.

## Usage
The API provides the following endpoints:

- `GET /services` - returns a list of all services that are accessible with a given access key
- `GET /status/{service}` -
returns `true` if the service is running, `false` otherwise 
- `POST /start/{service}` - runs `docker compose up -d` in the service directory (starts the service)
- `POST /stop/{service}` - runs `docker compose down` in the service directory (stops the service)
- `GET /logs/{service}` - returns the logs of the service (`docker compose logs`) format into an array of 3-tuples of the form `(service, timestamp, log)`, where `service` is the name of the service as defined in the `docker-compose.yml`
 file.
- `WS /ws/logs/{service}` - establishes a WebSocket connection to the service and returns the logs as they are generated. Does not include old logs.
- `POST /command/{service}` - runs a custom command in the service directory. The command should be passed as a JSON object in the request body. For example: `{"command": "ls -la"}`. The response will be the output of the command.

The `{service}` parameter is the name of the service as defined in the `config.json` file.


To access services that require an access key, append the query parameter `access_key` to the request. For example: 
`/logs/<service>?access_key=1234567890`

## Configuring the API

The `config.json` file contains the configuration for the docker compose applications and the access keys to access
those applications.
It should be in the following format:

```js
{
    // These are variable keys that can be used to restrict access to certain services
    "access-keys": {
        "general": "1234567890"
        ...
    },
    // The services that should be accassible via the API
    "services": {
        // The name of the service
        "service-name": {
            // The path to the directory where the docker-compose.yml file is located
            "cwd": "/path/to/dir",
            // The access key that is required to access this service. If not specified, no access key is required
            "access-key": "$general" // <- This is a variable name
        },
        "another-service": {
            "cwd": "/path/to/dir",
            "access-key": "1234567890",
            // The name of the docker-compose file (default: docker-compose.yml)
            "compose-file": "docker-compose.prod.yml"
        },
        "third-service": {
            "cwd": "/path/to/dir",
              
            // It's also possible to use a list of access keys (logical OR)
            "access-key": [
                "abc",
                "def",
            ]
        },
        "forth-service": {
          "cwd": "/path/to/dir",

          // It's also possible to restrict an access key to certain scopes
          "access-key": {
            "key": "$general",  // Specify the key
            "scope": [          // Restrict to specific scopes
                "logs",
                "status"
            ] 
          }
        }
        ...
    }
}
```

For the `access-key` field you can either use a string or a variable name (prefixed with a `$` sign) that is defined in
the `access-keys` field. To use an access key, that starts with a `$` sign, you have to escape it with a another `$`
sign. For example: `$$general` would require `...?access_key=$general`.

An example `config.json` file can be found [here](./config.example.json).

## Note on Docker compose services
Currently, it's not possible to start / stop / monitor single services defined in the `docker-comopse.yml` file. Only all services at once can be controlled.

## See Also
The [`docker-compose-remote-manager-web-app`](https://github.com/MatthiasHarzer/docker-compose-remote-manager-web-app) build on top of this server docker compose services via a simple web GUI.
