FROM python:3.13-slim
WORKDIR /app
COPY requirements/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt --break-system-packages
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python3 -m playwright install chromium --with-deps
ENV VOB_BROWSER=1
COPY . .
CMD ["python", "run.py"]

