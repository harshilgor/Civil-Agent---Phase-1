FROM python:3.12-slim

WORKDIR /app

COPY services/sizer-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/sizer-api/ .

ENV SIZER_API_PORT=8001
EXPOSE 8001

CMD ["python", "main.py"]
