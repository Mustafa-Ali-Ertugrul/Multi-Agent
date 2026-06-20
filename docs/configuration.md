# Configuration

`Multi-Agent` üç katmanda yapılandırılabilir:

1. **Komut satırı flag'leri** (`multiagent analyze ...`) — tek seferlik.
2. **TOML yapılandırma dosyası** — repo başına kalıcı.
3. **Ortam değişkenleri** — gizli anahtarlar ve global varsayılanlar.

## Yapılandırma dosyası

Yer arama sırası (ilk bulunan kullanılır):

1. Komutta açıkça verilen yol (`load_config(path)`).
2. `./multiagent.toml`
3. `./.multiagent.toml`

Hiçbiri yoksa tüm alanlar `Config()` default'larına düşer.

### Tam şema

```toml
[multiagent]
# LLM sağlayıcı ayarları (Ollama için)
model = "qwen2.5-coder:7b"          # default: ortamdan
base_url = "http://localhost:11434"  # default: ortamdan

# Çalıştırılacak ajan listesi (sıra önemli)
agents = ["reviewer", "architect", "test-runner", "build"]

# MCP entegrasyonu (bkz. mcp.md)
mcp_command = "npx"                  # stdio için
mcp_args = ["-y", "@modelcontextprotocol/server-git"]
mcp_url = "https://mcp.example.com/sse"  # SSE için
require_mcp = false

# Davranış anahtarları
coordinator = false          # LLM ile ajan seçimi
memory = false               # Kalıcı SQLite hafıza
security = false             # SecurityAgent'i pipeline'a ekler
knowledge_graph = false      # KnowledgeGraphAgent'i ekler
max_agent_iterations = 2     # Coordinator için üst sınır
exclude_dirs = [".venv", "node_modules", ".git"]
llm_failure_mode = "fallback"  # "fatal" | "fallback"

# Memory (iki biçim kabul edilir)
memory_path = ".multiagent/memory.sqlite"
# veya
# [multiagent.memory]
# path = ".multiagent/memory.sqlite"

# Benchmark için birden çok model
[[multiagent.benchmark.models]]
name = "qwen"
provider = "ollama"
model = "qwen2.5-coder:7b"

[[multiagent.benchmark.models]]
name = "llama3"
provider = "openai"
model = "llama-3.1-70b"
base_url = "https://api.example.com/v1"
api_key_env = "LLAMA_API_KEY"
cost_per_1k_tokens = 0.0008
```

### Alan açıklamaları

| Anahtar                         | Tür          | Varsayılan                                | Açıklama                                                  |
| ------------------------------- | ------------ | ----------------------------------------- | --------------------------------------------------------- |
| `model`                         | `str?`       | `MULTIAGENT_MODEL` veya `None`            | Tek başına çalışan ajanlar için LLM modeli               |
| `base_url`                      | `str?`       | `MULTIAGENT_BASE_URL`                     | OpenAI-uyumlu uç noktası veya Ollama URL'si              |
| `agents`                        | `list[str]`  | `[reviewer, architect, test-runner, build]` | Çalıştırılacak ajan isimleri (sıra = çalışma sırası)    |
| `mcp_command` / `mcp_args`      | `str?`/list  | `None`                                    | stdio MCP sunucusu için komut ve argümanlar               |
| `mcp_url`                       | `str?`       | `None`                                    | SSE MCP sunucusu için URL                                |
| `require_mcp`                   | `bool`       | `false`                                   | MCP hata verirse sert exception fırlat                    |
| `coordinator`                   | `bool`       | `false`                                   | LLM-destekli ajan seçimini açar                          |
| `memory`                        | `bool/dict`  | `false`                                   | Kalıcı SQLite hafızayı açar (`memory.path` ile yol verilebilir) |
| `memory_path`                   | `str`        | `.multiagent/memory.sqlite`               | MemoryAgent'in SQLite dosyası                            |
| `security`                      | `bool`       | `false`                                   | SecurityAgent pipeline'a ekler                            |
| `knowledge_graph`               | `bool`       | `false`                                   | KnowledgeGraphAgent pipeline'a ekler                      |
| `max_agent_iterations`          | `int`        | `2`                                       | Coordinator'ün en fazla kaç tur atacağı (min 1)         |
| `exclude_dirs`                  | `list[str]`  | `[.venv, node_modules, .git]`             | `load_repo` sırasında atlanan klasörler                  |
| `llm_failure_mode`              | `str`        | `"fallback"`                              | `"fatal"` → LLM hatası raise; `"fallback"` → logla & devam et |
| `benchmark.models[]`            | `list`       | `[]`                                      | Benchmark alt komutu için model listesi                  |
| `benchmark.models[].name`       | `str`        | zorunlu                                   | Benchmark çıktısında görünecek kısa ad                  |
| `benchmark.models[].provider`   | `str`        | `"ollama"`                                | `ollama` veya `openai`                                   |
| `benchmark.models[].model`      | `str`        | zorunlu                                   | Provider'a gönderilecek tam model adı                   |
| `benchmark.models[].base_url`   | `str?`       | `None`                                    | OpenAI-uyumlu uç noktası                                |
| `benchmark.models[].api_key_env`| `str?`       | `None`                                    | API anahtarını içeren ortam değişkeninin adı            |
| `benchmark.models[].cost_per_1k_tokens` | `float?` | `None`                                 | 1k token başına maliyet (raporlama için)                 |

## Ortam değişkenleri

| Değişken             | Açıklama                                                  |
| -------------------- | --------------------------------------------------------- |
| `MULTIAGENT_MODEL`   | CLI `--model` öncesi okunan varsayılan LLM modeli       |
| `MULTIAGENT_BASE_URL`| LLM uç noktası (Ollama veya OpenAI-uyumlu)               |
| `MULTIAGENT_API_KEY` | OpenAI-uyumlu sağlayıcılar için API anahtarı             |
| `GITHUB_TOKEN`       | `github_pr` ajanının gerçek PR açması için                |

## Öncelik sırası

Bir ayar hem config hem ortam hem komut satırında verildiğinde:

```
komut satırı flag > ortam değişkeni > config dosyası > Config() default
```

Örnek: `--model llama3` verildiğinde, `MULTIAGENT_MODEL` ve
`multiagent.toml`'daki `model` yoksayılır.

## Doğrulama

Yapılandırma dosyanız doğru parse ediliyorsa:

```bash
multiagent analyze ./repo --json-out /tmp/out.json
cat /tmp/out.json | python -c "import json,sys; print(json.load(sys.stdin)['run_id'])"
```

komutu bir `run_id` döndürmelidir (yapılandırma hatalıysa CLI daha
parse aşamasında hata fırlatır).
