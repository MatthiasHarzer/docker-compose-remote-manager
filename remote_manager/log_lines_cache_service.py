import json
import os
import traceback
from typing import Iterable

from remote_manager.compose_parsing import ComposeLogLine
from remote_manager.compose_service import ComposeService

def _to_compose_log_line(line: list[str]) -> ComposeLogLine | None:
	if len(line) != 3:
		return None
	name, full_timestamp, log = line
	return name, full_timestamp, log

def _to_compose_log_lines(line: list[list[str]]) -> list[ComposeLogLine]:
	return [_to_compose_log_line(l) for l in line if _to_compose_log_line(l)]

def _load(file: str, services: Iterable[ComposeService]) -> None:
	if not os.path.exists(file):
		return

	with open(file, "r") as f:
		data = json.load(f)

		for service in services:
			if service.name not in data:
				continue

			if type(data[service.name]) is not list:
				continue

			lines = _to_compose_log_lines(data[service.name])
			service.set_log_lines(lines)

def _save(file: str, service: ComposeService) -> None:
	if os.path.exists(file):
		with open(file, "r") as f:
			data = json.load(f)
	else:
		data = {}

	data[service.name] = service.logs

	with open(file, "w") as f:
		json.dump(data, f)

class LogLinesCacheService:
	def __init__(self, cache_file: str):
		self.cache_file = cache_file

	def load_lines(self, services: Iterable[ComposeService]) -> None:
		"""
		Load the lines from the cache file.
		:param services: The services
		:return:
		"""
		try:
			_load(self.cache_file, services)
		except FileNotFoundError:
			traceback.print_exc()


	def save_lines(self, service: ComposeService) -> None:
		"""
		Save the lines to the cache file.
		:param service: The service
		:return:
		"""
		try:
			_save(self.cache_file, service)
		except FileNotFoundError:
			traceback.print_exc()

	def observe_service(self, service: ComposeService) -> None:
		"""
		Observe the service for log line changes.
		:param service: The service
		:return:
		"""

		def on_log_line(_):
			self.save_lines(service)

		service.listen(on_log_line)

	def observe_services(self, services: Iterable[ComposeService]) -> None:
		"""
		Observe the services for log line changes.
		:param services: The services
		:return:
		"""
		for service in services:
			self.observe_service(service)


