FROM python:3.12-slim
RUN useradd -m -u 1000 app
WORKDIR /home/app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app app.py VERSION ./
COPY --chown=app:app media/ ./media/
USER app
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]
