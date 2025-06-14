#!/bin/bash
if test -f venv/bin/activate; then
    source venv/bin/activate
fi

make run
