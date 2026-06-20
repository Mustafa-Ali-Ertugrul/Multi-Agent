# MCP integration

`Multi-Agent`, Model Context Protocol (MCP) üzerinden harici araçlara
erişebilir. İki taşıma desteklenir:

- **stdio** — yerel bir komutu spawn ederek.
- **SSE** — uzak bir HTTP-SSE uç noktasına bağlanarak.

MCP opsiyoneldir: ayarlanmadan da tüm statik ajanlar çalışır.

## stdio modu

Bir komut + argüman listesi olarak yapılandırılır:

=== "Yapılandırma dosyası"

    ```toml
    [multiagent]
    mcp_command = "npx"
    mcp_args = ["-y", "@modelcontextprotocol/server-git"]
    ```

=== "Komut satırı"

    ```bash
    multiagent analyze ./repo \
        --mcp-command npx \
        --mcp-args "-y @modelcontextprotocol/server-git"
    ```

CLI `--mcp-args` tek bir string alır ve boşlukla ayrıştırır.

## SSE modu

Uzak bir MCP sunucusuna bağlanmak için:

```toml
[multiagent]
mcp_url = "https://mcp.example.com/sse"
```

```bash
multiagent analyze ./repo --mcp-url https://mcp.example.com/sse
```

`mcp_command` ve `mcp_url` aynı anda ayarlanmamalıdır — ikisi de
verildiğinde CLI stdio'yu tercih eder.

## Sıkı mod (`--require-mcp`)

Varsayılan olarak MCP çağrısı başarısız olursa (sunucu çöker, araç
yoksa) ajan yumuşak şekilde loglar ve devam eder. **Sıkı mod** ise
MCP zorunluluğu getirir:

```bash
multiagent analyze ./repo --require-mcp
# veya
```

```toml
[multiagent]
require_mcp = true
```

Sıkı modda:

- MCP sunucusu başlatılamazsa → `MCPClientError` raise.
- Aracı sunucu tanımıyorsa → raise.
- Ajan MCP'ye bağımlıysa ve bağlantı koparsa → raise.

Sıkı mod CI'de ve "MCP yoksa analiz anlamsız" senaryolarında
önerilir.

## Araç keşfi

MCP bağlandığında `MCPClient.tools()` mevcut araçları listeler.
`architect`, `reviewer` ve `coordinator` ajanları bu listeyi kendi
LLM çağrılarına araç olarak sunabilir. Hangi aracın hangi ajan
tarafından kullanıldığı `ContextStore.agent_trace` içinde kayıt
altına alınır.

## Örnek: GitHub MCP

```toml
[multiagent]
mcp_command = "npx"
mcp_args = ["-y", "@modelcontextprotocol/server-github"]
memory_path = ".multiagent/memory.sqlite"
```

Bu yapılandırma ile Coordinator, repo hakkında bilgi toplamak için
GitHub MCP araçlarını (`search_repositories`, `get_file_contents`,
...) kullanabilir ve `architect` çıktısını `memory`'ye kalıcı
olarak yazabilir.

## Güvenlik notları

- MCP sunucu komutu güvenilir bir kaynaktan gelmelidir (`npx -y` her
  çalıştırmada indirir).
- API anahtarları `multiagent.toml`'a **yazılmamalıdır** — bunun
  yerine `api_key_env` ile ortam değişkenine yönlendirilir.
- Sıkı mod (`require_mcp = true`) prod ortamlarında tercih edilir.

## Hata ayıklama

```bash
multiagent -v analyze ./repo --require-mcp
```

`-v` (verbose) MCP bağlantısı, araç listesi ve her çağrının
girdisini/çıktısını loglar. JSON çıktısı
(`--json-out out.json`) `agent_trace` altında MCP hata mesajlarını
saklar.
