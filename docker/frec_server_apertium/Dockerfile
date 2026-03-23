FROM debian:trixie-20251103

RUN apt-get update -y
RUN apt-get install -y \
    python3 \
    python-is-python3 \
    python3-pip \
    unzip \
    curl \
    locales \
    apertium \
    apertium-apy \
    apertium-arg-cat apertium-cat-ita apertium-cat-srd apertium-eng-cat apertium-eo-ca \
    apertium-fra-cat apertium-oc-ca apertium-por-cat apertium-spa-cat

# remove typing-extensions to avoid conflict when it is pulled in by requirements.txt
RUN apt-get purge -y python3-typing-extensions

WORKDIR /app
COPY requirements.txt .

RUN pip install --break-system-packages -r requirements.txt

# set UTF8 locale, required for apertium to work
RUN sed -i '/ca_ES.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG ca_Es.UTF-8  
ENV LANGUAGE ca_ES:ca  
ENV LC_ALL ca_ES.UTF-8   

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["bash"]
