#!/bin/bash
if test -f venv/bin/activate; then
    source venv/bin/activate
fi

uvicorn remote_manager.server:app --host 0.0.0.0 --port 9090
