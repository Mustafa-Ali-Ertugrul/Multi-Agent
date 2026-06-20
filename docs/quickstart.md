# Quickstart

Bir Python reposunda `Multi-Agent`'i sıfırdan çalıştırmak için gereken
süre: **60 saniyenin altında**.

## 1. Kur

```bash
pip install multiagent
```

## 2. Statik analiz

Harici bir repo üzerinde temiz, LLM'siz analiz:

```bash
multiagent analyze ./my-project --security --knowledge-graph
```

Bu komut sırasıyla çalıştırır:

1. `knowledge-graph` — repo AST grafiğini üretir.
2. `security` — bandit + secret + SQLi/XSS/SSRF + pip-audit.
3. `reviewer` — kod inceleme önerileri (LLM çağrısı yapmaz).
4. `architect` — mimari özet (LLM varsa rapor üretir).
5. `test-runner` — `pytest` çalıştırır ve sonuçları bağlama yazar.
6. `build` — agent çıktılarından düzeltme diffleri önerir.

## 3. Bağlam çıktısı

```bash
multiagent analyze ./my-project --json-out run.json
```

`run.json` içinde `findings`, `decisions`, `agent_trace`,
`knowledge_graph`, `proposed_diffs` ve `benchmark_results` yer alır.
Şema detayı için [`ContextStore` mimari sayfasına](architecture.md)
bakın.

## 4. Belirli ajanları seç

```bash
# Yalnızca güvenlik taraması
multiagent analyze ./my-project --agents security,reviewer
```

Geçerli ajan adları:

```
memory, knowledge-graph, security, reviewer, architect,
test-runner, build, github_pr
```

## 5. Coordinator modu

LLM destekli ajan seçimi istiyorsanız:

```bash
multiagent analyze ./my-project --coordinator --model qwen2.5-coder:7b
```

Coordinator, `--task` ile verilen niyete göre hangi ajanların çalışacağına
karar verir ve akışı `fail_fast=False` ile yönetir.

## 6. GitHub PR üretimi

```bash
# Dry-run: PR'ı açmadan diff üretir
multiagent analyze ./my-project --open-pr

# Gerçek PR açar (GITHUB_TOKEN gerekli)
GITHUB_TOKEN=ghp_xxx multiagent analyze ./my-project --execute-pr
```

## Sık kullanılan komutlar

| Amaç                                       | Komut                                                                              |
| ------------------------------------------ | ---------------------------------------------------------------------------------- |
| İlk tarama                                  | `multiagent analyze ./repo --security`                                            |
| JSON rapor                                  | `multiagent analyze ./repo --json-out out.json`                                    |
| Sadece güvenlik                             | `multiagent analyze ./repo --agents security`                                      |
| LLM ile planlama                            | `multiagent analyze ./repo --coordinator --model <name>`                           |
| Hata olursa devam et                        | `multiagent analyze ./repo --continue-on-error`                                    |
| Ayrıntılı log                               | `multiagent analyze ./repo -v`                                                     |
| Birden çok model karşılaştırması            | `multiagent benchmark ./repo --task "fix SQLi" --models qwen,llama3`               |
