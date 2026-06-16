# multiagent

`multiagent`, Python 3.11+ ile geliştirilecek multi-agent kod analiz aracı için başlangıç iskeletidir.

Amaç, farklı ajanların orkestrasyonunu, LLM entegrasyonlarını, MCP bağlantılarını, araçları ve bağlam yönetimini temiz paket sınırlarıyla geliştirmeye uygun bir temel sağlamaktır.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Ollama'nın yerelde çalıştığından ve kullanmak istediğiniz modelin indirildiğinden emin olun:

```bash
ollama pull qwen2.5-coder
```

## Geliştirme

```bash
ruff check .
ruff format .
mypy src
pytest
```

## Kullanım

Varsayılan model ile bir repoyu analiz etmek:

```bash
multiagent analyze .
```

Modeli komut satırından seçmek:

```bash
multiagent analyze . --model gemma2
```

JSON context çıktısı almak:

```bash
multiagent analyze . --json-out context.json
```

Ortam değişkeniyle varsayılan modeli değiştirmek:

```bash
MULTIAGENT_MODEL=qwen2.5-coder multiagent analyze .
```

## Katkı

Katkı göndermeden önce kalite kontrollerini çalıştırın:

```bash
ruff check .
ruff format --check .
mypy src tests
pytest
```

Yeni agent veya gateway davranışı eklerken ilgili birim testlerini de ekleyin. `mypy` CI'da bloklayıcıdır, bu yüzden public API'lerde ve test yardımcılarında tip ipuçlarını eksiksiz tutun.
