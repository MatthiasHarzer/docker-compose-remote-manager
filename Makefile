OS_NAME := $(shell uname)
ifeq ($(OS_NAME), Darwin)
OPEN := open
else
OPEN := xdg-open
endif

format:
	@autopep8 ./remote_manager
	@isort ./remote_manager

run:
	@uvicorn remote_manager.server:app --host 0.0.0.0 --port 9090