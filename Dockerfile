# Any container host (Fly, Railway, Cloud Run, a VPS): docker build -t priyanka .
FROM python:3.12-slim

# ffmpeg is the only system dependency: Bulbul's WAV format drifts and Saaras
# rejects what it does not recognise, so every reply is re-encoded to 16 kHz mono.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Platforms inject $PORT and expect the app on 0.0.0.0 (server.py reads both).
ENV TUTOR_HOST=0.0.0.0
EXPOSE 7860

CMD ["python", "server.py"]
