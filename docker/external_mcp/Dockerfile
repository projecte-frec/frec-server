FROM debian:trixie-20251103

RUN apt update -y
RUN apt install -y \
    nodejs \
    npm \
    python3 \
    python-is-python3 \
    python3-pip
    
RUN pip install mcp-proxy --break-system-packages
RUN pip install uv --break-system-packages
RUN npm install -g deno

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["bash"]