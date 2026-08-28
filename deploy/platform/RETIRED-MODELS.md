# Retired models still advertised by the gateway

Measured against `api.codechi.me` on 2026-08-28 by calling every model the
gateway lists in `/v1/models` with a one-token completion.

**24 of 31 work. Seven do not**, and they are still offered to every client —
NUFI chat, NUFI Studio, and any agent adapter. A caller that picks one gets an
opaque failure: Studio, for instance, shows only *"An error occurred"*.

Worse, four of the dead names sort to the **top** of Studio's model dropdown,
so the default choice is a broken one.

## Remove these from the LiteLLM config

```
Nufi-lab/models/gemini-2.0-flash
Nufi-lab/models/gemini-2.0-flash-001
Nufi-lab/models/gemini-2.0-flash-lite
Nufi-lab/models/gemini-2.0-flash-lite-001
Nufi-lab/models/gemini-3-pro-preview
Nufi-lab/models/gemini-robotics-er-1.5-preview
Nufi-lab/models/gemini-omni-flash-preview      # returns 400, not 404
```

Upstream's message on the 2.0-flash family:

> This model models/gemini-2.0-flash is no longer available. Please update your
> code to use models/gemini-3.6-flash for the latest features and improvements.

## Verified working

```
gemini                                        Nufi-lab/models/gemini-3-flash-preview
Nufi-lab/models/gemini-2.5-flash              Nufi-lab/models/gemini-3.1-pro-preview
Nufi-lab/models/gemini-2.5-pro                Nufi-lab/models/gemini-3.1-pro-preview-customtools
Nufi-lab/models/gemini-2.5-flash-lite         Nufi-lab/models/gemini-3.1-flash-lite-preview
Nufi-lab/models/gemini-2.5-flash-image        Nufi-lab/models/gemini-3.1-flash-lite
Nufi-lab/models/gemini-flash-latest           Nufi-lab/models/gemini-3-pro-image-preview
Nufi-lab/models/gemini-flash-lite-latest      Nufi-lab/models/gemini-3-pro-image
Nufi-lab/models/gemini-pro-latest             Nufi-lab/models/gemini-3.1-flash-image-preview
Nufi-lab/models/gemma-4-26b-a4b-it            Nufi-lab/models/gemini-3.1-flash-image
Nufi-lab/models/gemma-4-31b-it                Nufi-lab/models/gemini-3.1-flash-lite-image
Nufi-lab/models/nano-banana-pro-preview       Nufi-lab/models/gemini-3.5-flash
                                              Nufi-lab/models/gemini-robotics-er-1.6-preview
```

## Reproducing this

```bash
KEY=<a gateway key>
curl -s -H "Authorization: Bearer $KEY" https://api.codechi.me/v1/models \
  | python3 -c "import sys,json;print('\n'.join(m['id'] for m in json.load(sys.stdin)['data']))" \
  | while read -r m; do
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 \
        -X POST https://api.codechi.me/v1/chat/completions \
        -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
        -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}")
      printf '%-6s %s\n' "$code" "$m"
    done
```

Worth re-running after any Google deprecation notice. A model list is not
static, and nothing currently alerts on a name going dead.
