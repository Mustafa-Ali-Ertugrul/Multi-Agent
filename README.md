# multiagent

`multiagent`, Python 3.11+ ile geliştirilecek multi-agent kod analiz aracı için başlangıç iskeletidir.

Amaç, farklı ajanların orkestrasyonunu, LLM entegrasyonlarını, MCP bağlantılarını, araçları ve bağlam yönetimini temiz paket sınırlarıyla geliştirmeye uygun bir temel sağlamaktır.

## Mimari ve Agent Akış Diyagramı

Sistem, bir kod deposu (repo) üzerindeki sorunları incelemek ve düzeltmek için bir dizi ajanı orkestre eder. Aşağıdaki metin bazlı akış diyagramı, ajanların (Agent) nasıl sırayla çalıştığını gösterir:

```text
[ ContextStore ] (Kod deposunun kopyası ve o anki durumu)
       │
       ▼
1. ReviewerAgent    --> Statik analiz ve güvenlik taraması yapar. (Varsa MCP araçlarını kullanır)
       │
       ▼
2. ArchitectAgent   --> Mimari analiz, bağımlılık kontrolü ve yapısal tavsiyeler verir.
       │
       ▼
3. TestRunnerAgent  --> Testleri koşturur (pytest vs.), başarısızlıkları analiz eder.
       │
       ▼
4. BuildAgent       --> LLM aracılığıyla Unified Diff üretir (ve istenirse dosyaları günceller).
       │
       ▼
5. GitHubPRAgent    --> Üretilen Diff'i uygular, yeni bir branch açar, commit atar ve GitHub üzerinde PR oluşturur.
```

Her agent `ContextStore` nesnesine kendi bulgularını (findings) ve kararlarını (decisions) ekler.

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

## Kullanım

Varsayılan model ile bir repoyu analiz etmek:

```bash
multiagent analyze .
```

### Uçtan Uca Çalıştırma (End-to-End)

Tüm zinciri (Reviewer → Architect → Test-runner → Build → GitHubPRAgent) uçtan uca çalıştırmak, otomatik olarak diff uygulayıp GitHub üzerinde Pull Request (PR) açmak için:

```bash
export GITHUB_TOKEN="ghp_xxx_sizin_tokeniniz_xxx"
multiagent analyze . \
    --agents reviewer,architect,test-runner,build,github_pr \
    --apply \
    --open-pr \
    --execute-pr
```

- `--apply`: BuildAgent tarafından oluşturulan diff'in projedeki dosyalara uygulanmasını sağlar.
- `--open-pr`: Pipeline'a GitHub PR Agent'ı ekler (eğer `--agents` ile sadece spesifik ajanlar verilmediyse).
- `--execute-pr`: GitHub PR Agent'ın `dry_run` modundan çıkıp gerçek bir Pull Request açmasını sağlar (Bu parametre verilmezse değişiklikler commitlenmez, sadece PR detayı ekrana yazdırılır).

### GITHUB_TOKEN Kullanımı

Eğer `GitHubPRAgent`'in gerçek bir PR açmasını (veya dry-run yaparken yetki hatası almasını engellemek) isterseniz, ortam değişkeni olarak `GITHUB_TOKEN` belirtmelisiniz:

```bash
export GITHUB_TOKEN="ghp_xxxxxx"
multiagent analyze . --open-pr
```

### MCP (Model Context Protocol) Yapılandırması

Agent'lar, sunulan MCP (Model Context Protocol) araçlarını kullanarak dış analizler (statik analiz, test vs.) yapabilirler. Bir MCP sunucusunu sürece bağlamak için `--mcp-command` veya `--mcp-url` (SSE için) kullanabilirsiniz. Ajanlar başarısız olursa yerel yedeğe (fallback) döner. Eğer MCP'nin zorunlu olmasını isterseniz `--require-mcp` kullanabilirsiniz.

```bash
multiagent analyze . \
    --mcp-command "node" \
    --mcp-args "server.js" \
    --require-mcp
```

### Geliştirme Seçenekleri

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

## Geliştirme ve Test

```bash
ruff check .
ruff format .
mypy src tests
pytest
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
