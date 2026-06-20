# Contributing

`Multi-Agent`'e katkıda bulunmak için izlenecek yol ve kalite
kapıları aşağıdadır.

## Geliştirme kurulumu

```bash
git clone https://github.com/Mustafa-Ali-Ertugrul/Multi-Agent.git
cd Multi-Agent
python -m pip install -e ".[dev,mcp,docs]"
```

Bu komutla birlikte gelir:

- `pytest`, `pytest-asyncio`, `pytest-cov`
- `ruff` (lint + format)
- `mypy` (strict mod)
- `bandit` (CI ile entegre)
- `mkdocs-material` (bu doküman sitesi)

## Çalıştırma kalıbı

1. Küçük, odaklı bir değişiklik yapın.
2. Bir ajan değiştiriyorsanız `tests/test_<agent>.py`'i güncelleyin
   veya yeni test ekleyin.
3. Kalite kapılarını lokal olarak çalıştırın:

    ```bash
    pytest -q
    ruff check src tests
    ruff format --check src tests
    mypy --strict src
    ```

4. PR açın. CI aynı kapıları koşar.

## Kalite kapıları (CI)

`pyproject.toml` ve `.github/workflows/` dosyalarındaki tanımlar:

| Kapı                         | Komut                                                  | Eşik / Kural                                  |
| ---------------------------- | ------------------------------------------------------ | --------------------------------------------- |
| Unit + integration tests     | `pytest -q`                                            | Tüm testler geçmeli                         |
| Coverage                     | `pytest --cov=src/multiagent --cov-fail-under=80`      | ≥ %80                                        |
| Lint                         | `ruff check src tests`                                 | `E, F, I, UP, B` seçili, `UP038` yoksayılır  |
| Format                       | `ruff format --check src tests`                        | 88 karakter satır uzunluğu                   |
| Tip kontrolü                 | `mypy --strict src`                                    | 27 paket dosyasında 0 hata                   |
| Bandit (güvenlik)            | `bandit -r src`                                        | `B603, B607` yoksayılır (subprocess testleri) |

`pytest` konfigürasyonunda `addopts = "--cov=... --cov-fail-under=80"`
ve `asyncio_mode = "strict"` ayarlıdır.

## Yeni ajan ekleme

1. `src/multiagent/agents/<name>.py` altında
   `BaseAgent`'tan türeyen bir sınıf:

    ```python
    from multiagent.agents.base import Agent
    from multiagent.context.store import ContextStore

    class MyAgent(Agent):
        @property
        def name(self) -> str:
            return "my-agent"

        def run(self, context: ContextStore) -> ContextStore:
            # ...
            return context
    ```

2. `tests/test_my_agent.py` altında en az bir test (mevcut ajan
   testlerini şablon olarak kullanın).
3. `multiagent.toml`'a ajan adını ekleyin veya dokümandaki
   [Ajanlar](agents.md) sayfasını güncelleyin.

## Commit mesajı

Conventional Commits kullanılır:

```
<type>(<scope>): <kısa özet>

<gövde: ne + neden>
<doğrulama + footer>
```

Yaygın `type`'lar: `feat`, `fix`, `perf`, `refactor`, `test`,
`docs`, `chore`, `ci`. Scope genellikle `security`, `context`,
`store`, `cli`, `architect` vb. ajan/modül adıdır.

## PR akışı

1. Feature branch açın (`feat/...`, `fix/...`).
2. CI yeşil olmalı.
3. Açıklayıcı PR gövdesi: **Ne + Neden + Nasıl doğrulandı +
   Risk değerlendirmesi + Checklist**.
4. Bir reviewer atayın.

## Dokümantasyon

Bu site `mkdocs-material` ile derlenir. Lokal önizleme:

```bash
pip install -e ".[docs]"
mkdocs serve
```

`http://127.0.0.1:8000` üzerinden canlı önizleme alırsınız.
Strict mod aktif (`strict: true`, `extra_strict_mode: true`) —
yani kırık link ve eksik sayfa build'i başarısız kılar.

## Davranış kuralları

- Destructive komutlar (`git reset --hard`, force-push, `rm -rf`)
  kullanıcı onayı olmadan çalıştırılmaz.
- Sırlar (API anahtarları, token'lar) repoya yazılmaz — bunun
  yerine `api_key_env` ve ortam değişkenleri kullanılır.
- Public API değişiklikleri `CHANGELOG`'da ve PR gövdesinde
  açıkça belirtilir.
