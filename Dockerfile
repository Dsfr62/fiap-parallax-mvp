FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY parallax ./parallax
COPY dados ./dados
COPY web ./web
RUN useradd --create-home parallax
USER parallax
ENV PARALLAX_HOST=0.0.0.0
EXPOSE 8000
CMD ["sh", "-c", "python -m parallax.setup && python -m parallax"]
