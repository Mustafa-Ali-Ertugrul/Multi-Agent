# Agents

`Multi-Agent`'in dokuz uzman ajanı vardır. Her birinin tek sorumluluk
alanı, deterministik bir girdi/çıktı sözleşmesi ve `ContextStore`'a
yazdığı alanlar bellidir.

| Ajan               | Ne yapar                                                    | Yazdığı alan(lar)               |
| ------------------ | ----------------------------------------------------------- | ------------------------------- |
| `memory`           | SQLite'a yapılandırılmış kayıt yazar/okur                  | `memories`                      |
| `knowledge-graph`  | Python dosyalarından AST-temelli modül/sınıf/fonksiyon grafiği üretir | `knowledge_graph`              |
| `security`         | Bandit + secret + SQLi/XSS/SSRF + pip-audit                 | `findings` (kaynak: `security:*`) |
| `reviewer`         | Stil + basit bug önerileri (LLM'siz çalışır)                | `decisions`, `proposed_diffs`  |
| `architect`        | Mimari özet (LLM varsa zenginleştirir)                      | `decisions`                     |
| `test-runner`      | `pytest` çalıştırır, sonuçları bağlama yazar               | `decisions`, `agent_trace`     |
| `build`            | Diğer ajanların bulgularından düzeltme diffleri üretir      | `proposed_diffs`                |
| `github_pr`        | Diff'i GitHub PR'ına dönüştürür (`--open-pr` / `--execute-pr`) | `decisions`                   |
| `coordinator`      | LLM-destekli ajan seçimi ve iteratif yürütme                | `agent_trace`, `proposed_diffs` |

## Çalıştırma sırası

CLI, ajanları aşağıdaki sırayla planlar (config'den veya
`--agents` ile özelleştirilebilir):

1. `memory` (kalıcı hafıza açıksa)
2. `knowledge-graph` (`--knowledge-graph` veya coordinator ile)
3. `security` (`--security` veya coordinator ile)
4. `reviewer`
5. `architect`
6. `test-runner`
7. `build`
8. `github_pr` (`--open-pr` veya `--execute-pr` ile)

## Güvenlik dedektörleri

`SecurityAgent` aşağıdaki imzaları ayrı `Finding` kaynakları olarak
yayar:

| Kaynak                | Dedektör                                            | Severity    |
| --------------------- | --------------------------------------------------- | ----------- |
| `security:secret`     | Hardcoded API key/token pattern (regex, satır-bağımsız) | high        |
| `security:sqli`       | `cursor.execute(...)`'a dynamic argüman: doğrudan f-string / `.format()`, ya da modülde risky atanmış değişken | high |
| `security:ssrf`       | `requests.get/post`, `httpx.get/post`, `client.get/post` çağrılarında sabit-olmayan URL | medium |
| `security:xss`        | `Markup(...)`, `mark_safe(...)`, `render_template_string(...)` veya f-string HTML çıktısı | medium |
| `security:cve`        | `pip-audit` ile raporlanan bilinen CVE'ler (dependency manifest varsa) | high / low |

Riskli atama tespiti (SQLi) **modül-geniş** tek geçişte yapılır:
`_risky_assigned_names(tree)` her dosya için bir kez `ast.walk` çağırır
ve `JoinedStr`/`BinOp`/`format()` hedefi olan tüm isimleri bir `set`'te
toplar. Sonra her `execute(name)` çağrısı `name.id in risky_names` ile
O(1) kontrol edilir.

## Coordinator modu

`--coordinator` verildiğinde standart sıralı plan atlanır. Coordinator
LLM'e `--task`'i ve mevcut bağlamı verir; ajan LLM'in seçtiği sırada
çalışır ve `max_agent_iterations` ile sınırlı iterasyon yapar. Hata
olursa `agent_trace`'e düşer ve sonraki adımı yeniden sorar (LLM
`fatal` modda değilse).

## Ajan yazma

Yeni bir ajan eklemek için `multiagent/agents/` altında `BaseAgent`'tan
türeyen bir sınıf yazmanız yeterlidir:

```python
from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore

class MyAgent(Agent):
    @property
    def name(self) -> str:
        return "my-agent"

    def run(self, context: ContextStore) -> ContextStore:
        # ... oku / yaz ...
        return context
```

CLI'a eklemek için `multiagent.toml`'a ajan adını ekleyin:

```toml
[multiagent]
agents = ["reviewer", "architect", "my-agent", "build"]
```

Testler `tests/test_<agent>.py` altına, `pytest`'in mevcut fixture
şablonlarını izleyerek eklenir.
