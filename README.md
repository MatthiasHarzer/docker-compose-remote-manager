# Docker Compose Remote Management API

This is a very simple API to manage Docker compose applications via HTTP requests and receive logs via WebSockets.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### Installation

- Copy the [`docker-compose.yml`](./docker-compose.yml) file into your local directory.
- Create a `config.json` file in the same directory as the `docker-compose.yml` file. See the [config.json](#configuring-the-api) section for more information.
- Update the path to the `config.json` file in the `docker-compose.yml` file to match your local path.
- Run `docker compose up -d --build` to start the container.
- The server should now run on `0.0.0.0:9090` (you can change the port in the `docker-compose.yml` file)

### Usage
The API provides the following endpoints:

- `GET` `/status/{service}` -
returns `true` if the service is running, `false` otherwise 
- `POST` `/start/{service}` - runs `docker compose up -d` in the service directory (starts the service)
- `POST` `/stop/{service}` - runs `docker compose down` in the service directory (stops the service)
- `GET` `/logs/{service}` - returns the logs of the service (`docker compose logs`)

- `WS` `/ws/logs/{service}` - establishes a WebSocket connection to the service and returns the logs as they are generated

The `{service}` parameter is the name of the service as defined in the `config.json` file.

### Configuring the API

The `config.json` file contains the configuration for the docker compose applications and the access keys to access
those applications.
It should be in the following format:

```js
{
    // These are variable keys that can be used to restrict access to certain services
    "access-keys": {
        "generale": "1234567890",
        ...
    },
    // The services that should be accassible via the API
    "services": {
        // The name of the service
        "service-name": {
            // The path to the directory where the docker-compose.yml file is located
            "cwd": "/path/to/dir",
            // The access key that is required to access this service. If not specified, no access key is required
            "access-key": "$generale"
            // <- This is a variable name
        },
        "another-service": {
            "cwd": "/path/to/dir",
            "access-key": "1234567890",
            // The name of the docker-compose file (default: docker-compose.yml)
            "compose-file": "docker-compose.prod.yml"
        },
        ...
    }
}
```

For the `access-key` field you can either use a string or a variable name (prefixed with a `$` sign) that is defined in
the `access-keys` field. To use an access key, that starts with a `$` sign, you have to escape it with a another `$`
sign. For example: `$$generale`.

An example `config.json` file can be found [here](./config.example.json).

### Note on Docker compose services
Currently, it's not possible to start / stop / monitor single services defined in the `docker-comopse.yml` file. Only all services at once can be controlled.
