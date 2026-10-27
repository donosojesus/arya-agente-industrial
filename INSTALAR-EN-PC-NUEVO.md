# Instalar ARYA en un PC nuevo

Esta guía deja ARYA funcionando en otro computador, a partir del repositorio de GitHub. Toma unos 30 minutos, la mayor parte en descargas.

## 1. Requisitos (una vez por PC)

| Qué | Para qué | Cómo |
|---|---|---|
| Windows 11 con **WSL 2 y Ubuntu** | Todo se ejecuta desde Ubuntu | PowerShell como administrador: `wsl --install -d Ubuntu`, y reiniciar |
| **Docker Desktop** | Los seis servicios de la demo | docker.com; en Settings → Resources → WSL integration, activar Ubuntu |
| **Git** y **gh** (GitHub CLI) | Descargar el código | En Ubuntu: `sudo apt install -y git`; gh desde github.com/cli/cli o con `sudo apt install gh` |
| **uv** (opcional) | Entorno de Python para las pruebas y el libro | En Ubuntu: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Microsoft Edge | Abrir la pantalla y exportar los PDF | Viene con Windows |

## 2. Descargar el proyecto

En Ubuntu:

```bash

mkdir -p ~/proyectos && cd ~/proyectos
git clone https://github.com/donosojesus/arya-agente-industrial.git
cd arya-agente-industrial
```

Cualquier carpeta sirve; en Windows conviene clonar dentro de WSL o en `/mnt/c/Users/<usuario>/`.

## 3. Primer arranque (con Internet)

```bash
open -a Docker 2>/dev/null || powershell.exe -c "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'"
./scripts/start-demo.sh --build     # construye las 6 imágenes (la primera vez tarda varios minutos)
```

La primera ejecución crea el archivo `.env` y genera ahí los secretos locales: los tokens de control, del agente, del aprobador y de administración. **El `.env` nunca se sube a GitHub**, así que cada PC tiene sus propios tokens.

## 4. Conectar el modelo (Nemotron en la GB10)

Edita `.env` y revisa estas líneas:

```bash
NEMOTRON_BASE_URL=http://<ip-de-tu-gb10>:30081/v1
NEMOTRON_MODEL=nvidia/nemotron-3-nano
LLM_THINKING=off
```

Después `./scripts/start-demo.sh` (sin `--build`) y `./scripts/preflight.sh`, que debe terminar en `PLANT READY` y con "Nemotron: en linea".

## 5. Entorno de Python (para pruebas, ensayos y el libro)

```bash
uv venv --python 3.12 ~/.venvs/arya-industrial-demo
uv pip install --python ~/.venvs/arya-industrial-demo/bin/python -r requirements/dev.lock
~/.venvs/arya-industrial-demo/bin/python -m pytest -q      # 106 pruebas, unos 3 minutos
```

## 6. Lo que no está en GitHub

| Qué | Por qué | Cómo recuperarlo |
|---|---|---|
| `.env` y sus tokens | Son secretos | Se generan solos en el primer arranque (paso 3) |
| Imágenes de Docker | Se construyen | `./scripts/start-demo.sh --build` |
| Datos de los volúmenes (historian, CMMS, memoria) | Son datos de ejecución | Se crean vacíos; `./scripts/reset-demo.sh` carga las órdenes históricas |
| Entorno de Python | Se reconstruye | Paso 5 |

## 7. Comprobación final

```bash
./scripts/open-demo.sh
```

Se abre la pantalla dividida con la planta operando. Haz la pregunta "¿Cómo está la bomba P-101 ahora?": si ARYA responde con los valores de la planta, todo funciona.
