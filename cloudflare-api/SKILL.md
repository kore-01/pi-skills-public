---
name: cloudflare-api
description: Create and manage Cloudflare resources through the REST API using credentials from D:\PI\cloudflare-key.txt — Workers, Pages, KV namespaces and keys, Worker environment variables and secrets, custom domains and routes, D1, R2. Use this whenever the task involves creating, deploying, configuring or inspecting anything in Cloudflare, including "建个 Worker", "建 KV", "绑域名", "设置环境变量", "部署到 Cloudflare", or when a Cloudflare operation must succeed without the dashboard. Also use when wrangler is unavailable or a resource type has no wrangler command.
---

# Cloudflare API

Direct REST access to a Cloudflare account, so an agent can create and configure
real infrastructure instead of only describing it.

The official `cloudflare/skills` set is documentation: it teaches *what* to run.
This skill supplies the *how* — the endpoint, the exact body, and the credential
handling — especially for KV and custom domains, which the official skills barely
cover.

## Credentials

Read from `D:\PI\cloudflare-key.txt`. It holds two accounts; each block starts at
a user line and carries its own account id and Global API Key.

```bash
python scripts/accounts.py            # 列出账号（密钥打码）
python scripts/accounts.py --json     # 机读格式
```

A **Global API Key is 32 or 37 characters** and uses `X-Auth-Email` +
`X-Auth-Key`. A scoped **API Token is 40 characters** and uses
`Authorization: Bearer`. Mixing them up returns:

```
6003 Invalid request headers / 6111 Invalid format for Authorization header
```

So `cf_call` resolves the shape from the credential itself rather than assuming.

Never print a key. `accounts.py` masks them, and `cf_call` never echoes headers.

## Running an API call

```bash
python scripts/cf.py GET  /accounts/<account_id>/storage/kv/namespaces
python scripts/cf.py POST /accounts/<account_id>/storage/kv/namespaces '{"title":"my-ns"}'
python scripts/cf.py PUT  /accounts/<id>/storage/kv/namespaces/<ns>/values/<key> --raw "value"
python scripts/cf.py DELETE /accounts/<id>/storage/kv/namespaces/<ns>
```

`--account N` picks the Nth account from the key file (default 1). `--raw` sends a
plain-text body, which KV values require. `--json` pretty-prints the response.

Every response is `{"success": bool, "result": ..., "errors": [...]}`; `cf.py`
exits non-zero when `success` is false so a shell `&&` chain stops on failure.

## Endpoints worth knowing

Replace `{a}` with the account id, `{z}` with a zone id.

### KV

```
GET    /accounts/{a}/storage/kv/namespaces                    列出
POST   /accounts/{a}/storage/kv/namespaces    {"title":"x"}    创建
GET    /accounts/{a}/storage/kv/namespaces/{ns}/keys           列出键
PUT    /accounts/{a}/storage/kv/namespaces/{ns}/values/{k}     写（body 为原始值）
GET    /accounts/{a}/storage/kv/namespaces/{ns}/values/{k}     读
DELETE /accounts/{a}/storage/kv/namespaces/{ns}/values/{k}     删键
DELETE /accounts/{a}/storage/kv/namespaces/{ns}                删命名空间
```

A KV value is written as the **raw request body**, not JSON — `--raw` exists for
this. Writing `{"v":"x"}` would store the literal JSON text.

### Workers

```
GET    /accounts/{a}/workers/scripts                            列出
PUT    /accounts/{a}/workers/scripts/{name}                    上传（multipart）
DELETE /accounts/{a}/workers/scripts/{name}                    删除
GET    /accounts/{a}/workers/scripts/{name}/settings           读变量
PUT    /accounts/{a}/workers/scripts/{name}/settings           写变量/绑定
PATCH  /accounts/{a}/workers/scripts/{name}/settings           局部更新
```

Variables and secrets share the `bindings` array:

```json
{"bindings":[
  {"type":"plain_text","name":"FOO","text":"bar"},
  {"type":"secret_text","name":"TOKEN","text":"..."},
  {"type":"kv_namespace","name":"KV","namespace_id":"<ns>"}
]}
```

### Worker custom domain and routes

```
GET  /accounts/{a}/workers/domains                     列出已绑域名
PUT  /accounts/{a}/workers/domains                     绑定自定义域名
     {"environment":"production","hostname":"k3.example.com",
      "service":"<worker>","zone_id":"<z>"}
GET  /accounts/{a}/workers/scripts/{name}/routes
PUT  /accounts/{a}/workers/scripts/{name}/routes       {"routes":[{"pattern":"x.com/*","zone_id":"<z>"}]}
```

A custom domain needs the **zone in the same account**. If `GET /zones` does not
list it, the bind cannot succeed no matter which credential you use — say so
instead of retrying.

### Pages

```
GET  /accounts/{a}/pages/projects
POST /accounts/{a}/pages/projects            {"name":"x","production_branch":"main"}
GET  /accounts/{a}/pages/projects/{p}
POST /accounts/{a}/pages/projects/{p}/domains {"name":"x.example.com"}
```

A Pages *deployment* needs a multipart upload of the built files; for a static
bundle, `wrangler pages deploy <dir> --project-name <p>` is far less work than
hand-rolling the multipart body.

### Zones

```
GET /zones?per_page=100                  当前凭据可见的所有域名
GET /zones?name=example.com              按名字查（拿 zone_id）
```

## Verify before building

Before creating anything, confirm the three preconditions, because each failure
looks like a different error later:

```bash
python scripts/accounts.py                          # 凭据形态
python scripts/cf.py GET /accounts/<id>             # 账号可读
python scripts/cf.py GET '/zones?name=example.com'  # 域名归属
```

## What this skill cannot do

- It does not mint credentials. If a Global API Key is all there is, say so and
  recommend a scoped token: a Global Key is the whole account.
- It does not upload a Pages bundle by hand; use wrangler for that.
- It does not know your intended architecture — the `cloudflare` product-selection
  skill is the right place to decide *what* to build.
