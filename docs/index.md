# Multi-Agent

> Python kod analizi için tasarlanmış çok-ajanlı araç kiti. Paylaşımlı bir
> `ContextStore` üzerinde 9 uzman ajan sıralı çalışır; isteğe bağlı LLM
> katmanı mimari planlama, GitHub PR üretimi ve test koşumu ekler.

<div class="grid cards" markdown>

-   :material-rocket-launch: **60 saniyede başla**

    ---

    Sadece `pip install` + `multiagent analyze ./repo` ile çalışan ilk
    pipeline: inceleme + mimari + test + build.

    [:octicons-arrow-right-24: Quickstart](quickstart.md)

-   :material-robot: **9 uzman ajan**

    ---

    `security`, `reviewer`, `architect`, `test-runner`, `build`,
    `knowledge-graph`, `memory`, `github_pr`, `coordinator` — her biri
    tek sorumluluk alanı.

    [:octicons-arrow-right-24: Ajanlar](agents.md)

-   :material-cog-outline: **Konfigürasyon odaklı**

    ---

    `.multiagent.toml` veya `multiagent.toml` ile ajan seti, LLM sağlayıcı,
    MCP sunucusu ve benchmark modelleri tanımlanır.

    [:octicons-arrow-right-24: Yapılandırma](configuration.md)

-   :material-tools: **Opsiyonel MCP**

    ---

    stdio veya SSE üzerinden harici araçları çalıştırma; `--require-mcp`
    ile sıkı mod.

    [:octicons-arrow-right-24: MCP](mcp.md)

-   :material-graph: **Paylaşımlı AST cache**

    ---

    `ContextStore.ast_trees` + `get_ast()` sayesinde aynı dosya 3 ajan
    tarafından yeniden parse edilmez.

    [:octicons-arrow-right-24: Mimari](architecture.md)

-   :material-chart-line: **Benchmark**

    ---

    Aynı görevi birden çok LLM modeli ile çalıştırıp skorlayın; JSON
    çıktısı.

    [:octicons-arrow-right-24: Benchmark](benchmark.md)

</div>

## Platform modları

`Multi-Agent` üç katmanda çalışır:

| Katman          | İçerik                                                  | Gereksinim            |
| --------------- | ------------------------------------------------------- | --------------------- |
| **Statik**      | Secret tarama, SQLi/XSS/SSRF, bandit, pip-audit        | —                     |
| **Yarı-statik** | Reviewer, architect, knowledge-graph, test-runner      | —                     |
| **Aktif**       | Coordinator, GitHub PR, LLM destekli planlama          | Ollama veya API anahtarı |

Statik + yarı-statik katmanlar her zaman çalışır; aktif katman yalnızca
açıkça etkinleştirildiğinde veya `coordinator` seçildiğinde devreye girer.

## Ne zaman kullanılır

- Mevcut bir Python projesinde **hızlı güvenlik ve kalite taraması** yapmak
  istiyorsanız.
- Birden çok LLM modelini **aynı görev üzerinde karşılaştırmak**
  istiyorsanız.
- `architect`/`test-runner` çıktılarını kullanarak **LLM-destekli düzeltme
  diffleri** üretmek istiyorsanız.
- Birden çok ajanın **paylaşımlı bağlamla** sıralı çalışmasını görmek
  istiyorsanız (kendi orchestrator'ınız için şablon olarak).
