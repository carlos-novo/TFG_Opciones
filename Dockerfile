FROM python:3.11-slim

# Evitamos que Python genere archivos .pyc y forzamos salida estándar sin buffer
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Definir el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar librerías C (ej. yfinance/pandas)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamos primero el archivo de dependencias para aprovechar el caché de capas de Docker
COPY requirements.txt .

# Instalamos las librerías
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del proyecto
COPY . .

# Exponemos los puertos estándar de nuestras aplicaciones
EXPOSE 8000
EXPOSE 8501

# Por defecto, el contenedor se queda a la espera. El comando final se define en docker-compose.yml
CMD ["bash"]
