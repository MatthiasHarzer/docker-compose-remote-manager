FROM python:3.11

COPY . /app
WORKDIR /app

# Install dependencies
RUN python -m pip install -r requirements.txt

CMD ["uvicorn", "remote_manager.server:app", "--host", "0.0.0.0" , "--port", "8000"]
