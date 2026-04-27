FROM python:3.12-slim

WORKDIR /app

COPY services/sizer-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "pydantic>=2,<3"

# Build with the monorepo root as context so the sibling engine is available.
COPY civilagent-sizer /tmp/civilagent-sizer
RUN pip install --no-cache-dir /tmp/civilagent-sizer

COPY services/sizer-api/ .

ENV SIZER_API_PORT=8001
EXPOSE 8001

CMD ["python", "main.py"]
