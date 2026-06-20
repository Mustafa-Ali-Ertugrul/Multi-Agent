# Benchmark

`multiagent benchmark` alt komutu, **aynı görevi birden çok LLM modeli
ile çalıştırıp skorlayan** bir A/B test ortamıdır. Amaç: bir model
değişikliğinin güvenlik bulgusu sayısına, test sonucuna ve diff
üretme kalitesine etkisini hızlıca ölçmek.

## Hızlı başlangıç

```bash
multiagent benchmark ./repo \
    --task "Fix SQL injection in db.py" \
    --models qwen,llama3,gpt-4o
```

`--models` virgülle ayrılmış model **adlarıdır** (yapılandırma
dosyasındaki `[[multiagent.benchmark.models]]` girdilerinin `name`
alanı). En az bir model `--models`'da listelenmelidir.

## Model tanımı

Her benchmark modeli `multiagent.toml` altında
`[[multiagent.benchmark.models]]` ile tanımlanır:

```toml
[[multiagent.benchmark.models]]
name = "qwen"
provider = "ollama"
model = "qwen2.5-coder:7b"
# base_url / api_key_env opsiyonel; provider'a göre farklılaşır

[[multiagent.benchmark.models]]
name = "gpt-4o"
provider = "openai"
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"
cost_per_1k_tokens = 0.005
```

Provider'a göre gerekli ortam değişkenleri:

| Provider  | Bağlantı                              | Anahtar env var                  |
| --------- | ------------------------------------- | -------------------------------- |
| `ollama`  | `MULTIAGENT_BASE_URL` (varsayılan `http://localhost:11434`) | — |
| `openai`  | `base_url` veya `MULTIAGENT_BASE_URL` | `api_key_env` (örn. `OPENAI_API_KEY`) |

## Skorlanan metrikler

Her model için `ContextStore.benchmark_results` listesine bir
`BenchmarkResult` yazılır:

| Alan                    | Tür        | Açıklama                                              |
| ----------------------- | ---------- | ----------------------------------------------------- |
| `name`                  | `str`      | Modelin kısa adı                                    |
| `provider`              | `str`      | `ollama` veya `openai`                              |
| `model`                 | `str`      | Provider'a gönderilen tam ad                       |
| `score`                 | `float`    | 0-100 arası bileşik skor (test + diff + güvenlik)  |
| `duration_seconds`      | `float`    | Toplam çalışma süresi                               |
| `tests_passed`          | `bool`     | `pytest` exit-code 0 mı                             |
| `diff_generated`        | `bool`     | `BuildAgent` anlamlı bir diff üretti mi             |
| `high_security_findings`| `int`      | `severity="high"` bulgu sayısı                      |
| `error`                 | `str|None` | Çalışma sırasında oluşan hata mesajı (varsa)        |

## JSON çıktısı

```bash
multiagent benchmark ./repo \
    --task "..." \
    --models qwen,llama3 \
    --json-out bench.json
```

```json
{
  "benchmark_results": [
    {
      "name": "qwen",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b",
      "score": 78.5,
      "duration_seconds": 12.4,
      "tests_passed": true,
      "diff_generated": true,
      "high_security_findings": 0,
      "error": null
    },
    {
      "name": "llama3",
      "provider": "openai",
      "model": "llama-3.1-70b",
      "score": 82.0,
      "duration_seconds": 18.7,
      "tests_passed": true,
      "diff_generated": true,
      "high_security_findings": 1,
      "error": null
    }
  ]
}
```

## İpuçları

- `--continue-on-error` ile bir modelin hatası diğerlerini
  engellemez.
- Tek bir model için `--models qwen` kullanabilir, çıktıyı
  kendi dashboard'unuzda karşılaştırabilirsiniz.
- `llm_failure_mode = "fallback"` (varsayılan) LLM hatasında
  skorlamayı yine de tamamlar; `"fatal"` ise run'ı durdurur.
- Bir model için `api_key_env` ayarlanmamışsa ve provider `openai`
  ise benchmark hata kaydı oluşturur ve devam eder (`error` alanı
  dolar).
