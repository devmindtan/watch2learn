# Public UI, private backend

Watch2Learn can be used from any device without paying for a server: the static
UI is published publicly, and it calls the backend running on your own machine.
Videos, models, the database and all processing stay on that machine.

```text
phone / laptop browser
  └─ https://<user>.github.io/watch2learn/        static UI (apps/web)
        └─ https://<machine>.<tailnet>.ts.net     Tailscale Funnel → 127.0.0.1:8000
              └─ pnpm dev (FastAPI, SQLite, data/media, ASR, translation, Ollama)
```

When your machine is off, the UI still loads but shows "Mất kết nối".

## 1. Create an access token (required before exposing anything)

```bash
pnpm remote:token            # creates data/access-token (Git-ignored, mode 600)
pnpm remote:token --rotate   # replace it if it ever leaks
```

With a token present every `/api/*` request needs `Authorization: Bearer <token>`.
Video and thumbnail URLs are HMAC-signed and expire after 6 hours, because media
elements cannot send headers. Signed URLs only allow reading.

## 2. Allow the public UI origin and start the backend

```bash
WATCH2LEARN_ALLOWED_ORIGINS=https://<user>.github.io pnpm dev
```

`localhost`/`127.0.0.1` origins are always allowed. Chrome Private Network Access
preflights are answered, so a public HTTPS page can also reach
`http://127.0.0.1:8000` on the same machine.

## 3. Expose the backend over HTTPS (free)

Tailscale Funnel (free on the personal plan, already installed here):

```bash
tailscale funnel --bg 8000     # prints https://<machine>.<tailnet>.ts.net
tailscale funnel --bg off      # stop exposing
```

Alternatives that also cost nothing: Cloudflare Tunnel (`cloudflared tunnel --url
http://127.0.0.1:8000`, random `trycloudflare.com` URL), or a router port forward
with your own TLS. Anything on the public internet is protected only by the
token, so keep it secret.

## 4. Publish the UI

`.github/workflows/pages.yml` uploads `apps/web` to GitHub Pages when it changes
on `main`. Enable it once in the repository: Settings → Pages → Source: GitHub
Actions. GitHub Pages is free for public repositories. Any static host works: the
UI is plain HTML/CSS/JS with relative asset paths.

## 5. Connect

Open the published UI, press the server button in the top bar, enter the Funnel
URL and the token, then "Kiểm tra" → "Lưu & kết nối". Settings are stored in that
browser only.

## Notes

- The YouTube player loads from YouTube in the browser; every other request goes
  to your backend.
- Microphone recording (pronunciation check) needs HTTPS or localhost, which both
  GitHub Pages and Funnel provide.
- Upload limits: 4 GB per video. There is no rate limiting; do not share the token.
