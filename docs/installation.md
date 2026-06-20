# Installation

`Multi-Agent` Python **3.11+** gerektirir. Sistem bağımlılığı yoktur; tüm
analiz saf Python ile yapılır (Bandit ve `pip-audit` opsiyonel binary'ler
olarak çağrılır).

## Temel kurulum

=== "Linux / macOS"

    ```bash
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install multiagent
    ```

=== "Windows (PowerShell)"

    ```powershell
    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -U pip
    pip install multiagent
    ```

=== "Windows (cmd)"

    ```bat
    py -3.11 -m venv .venv
    .venv\Scripts\activate.bat
    python -m pip install -U pip
    pip install multiagent
    ```

## Kaynak koddan kurulum (geliştirici)

```bash
git clone https://github.com/Mustafa-Ali-Ertugrul/Multi-Agent.git
cd Multi-Agent
python -m pip install -e ".[dev]"
```

## Opsiyonel `[extras]`

`pyproject.toml` üzerinden gruplanmış opsiyonel bağımlılıklar:

| Extra        | İçerik                                          | Ne zaman?                          |
| ------------ | ----------------------------------------------- | ---------------------------------- |
| `mcp`        | `mcp>=1.0` — Model Context Protocol istemcisi  | MCP entegrasyonu kullanıyorsanız   |
| `dev`        | `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `bandit` | Test/lint/typecheck için |
| `docs`       | `mkdocs-material`, `mkdocstrings`, `pymdown-extensions` | Bu doküman sitesini derlemek için |

```bash
# MCP destekli analiz
pip install "multiagent[mcp]"

# Geliştirici kurulumu
pip install -e ".[dev,mcp]"

# Dokümantasyonu lokal derlemek için
pip install -e ".[docs]"
```

## Opsiyonel sistem araçları

| Araç        | Ne yapar                                | Yoksa ne olur?                              |
| ----------- | --------------------------------------- | ------------------------------------------- |
| `bandit`    | Statik güvenlik taraması               | `SecurityAgent` "Bandit unavailable" notu ekler |
| `pip-audit` | Bağımlılık CVE taraması               | `SecurityAgent` "pip-audit not installed" notu ekler |
| Ollama      | Lokal LLM çıkarımı (`--coordinator`)   | LLM çağrıları fallback ile sonuçsuz kalır   |

## Doğrulama

```bash
multiagent --help
multiagent analyze --help
multiagent benchmark --help
```

`multiagent analyze --help` çıktısı, [Quickstart](quickstart.md)'ta
gösterilen 20+ flag'i içermelidir.
