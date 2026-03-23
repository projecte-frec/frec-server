FROM debian:trixie-20251103

RUN apt update -y
RUN apt install -y \
    python3 \
    python-is-python3 \
    python3-pip \
    unzip \
    curl
    
WORKDIR /app
COPY requirements.txt .

RUN pip install --break-system-packages -r requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["bash"]