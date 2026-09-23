FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git cron openssh-client \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN git config --global user.name "Edward NAS (Docker)" && \
    git config --global user.email "edwardchin811227@gmail.com" && \
    git config --global pull.rebase true

RUN mkdir -p /root/.ssh && \
    echo "StrictHostKeyChecking no" > /root/.ssh/config && \
    chmod 400 /root/.ssh/config

COPY run_update.sh /app/run_update.sh
COPY crontab_config /etc/cron.d/cnnfng_cron

RUN chmod +x /app/run_update.sh && \
    chmod 0644 /etc/cron.d/cnnfng_cron

CMD ["/bin/bash", "-c", "if [ ! -d '/app/cnnfear-and-greed-index/.git' ]; then echo 'Cloning repo...' && git clone git@github.com:edwardchin811227/cnnfear-and-greed-index.git /app/cnnfear-and-greed-index || { echo 'Clone FAILED'; exit 1; }; fi && echo 'Repo ready. Starting cron...' && cron && echo 'Cron started. Keeping container alive...' && tail -f /dev/null"]
