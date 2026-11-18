# Setting up each network

Everything goes into this repo's **Settings → Secrets and variables → Actions**. Secrets are the private keys (the
**Secrets** tab); variables are the plain settings (the **Variables** tab). A network without its secrets is simply
skipped, so set them up one at a time.

Then test each one with **Actions → Announce releases → Run workflow**: repo `Sablednah/CityWorld-ReForged`, tag
`v7.2.0`, *dry run* ticked, *only* the network's name. Untick *dry run* to post for real. When they all work, add the
variable **`ANNOUNCE_LIVE`** = `true` and new releases post by themselves.

The menus on these sites move around; if a step below doesn't match what you see, the idea is the same: an app with
permission to post, and a token for your own account.

## Bluesky

1. Settings → Privacy and security → **App passwords** → Add App Password.
2. Secrets: `BLUESKY_HANDLE` (for example `yourname.bsky.social`) and `BLUESKY_APP_PASSWORD`.

## Mastodon

1. Preferences → **Development** → New application. Any name; under scopes, tick only **`write:statuses`**. Submit.
2. Open the application and copy **Your access token**.
3. Variable `MASTODON_INSTANCE` (your server, for example `mastodon.social`); secret `MASTODON_TOKEN`.

## Tumblr

1. https://www.tumblr.com/oauth/apps → Register application. Any website and callback URL will do (for example
   `https://sablecraft.co.uk`). Copy the **OAuth Consumer Key** and **Secret Key**.
2. https://api.tumblr.com/console → enter those two → allow access → **Show keys**, and copy the **Token** and **Token
   Secret**.
3. Variable `TUMBLR_BLOG` (for example `yourblog.tumblr.com`); secrets `TUMBLR_CONSUMER_KEY`,
   `TUMBLR_CONSUMER_SECRET`, `TUMBLR_TOKEN`, `TUMBLR_TOKEN_SECRET`.

## Facebook Page, Instagram and Threads (one Meta app)

Make one app at **developers.facebook.com → My Apps → Create app**, and add the three use cases below to it. The app
can stay in development mode: it only ever posts to your own accounts, which have a role on the app.

### Facebook Page

1. Use case: **Manage everything on your Page**.
2. **Graph API Explorer**: pick your app, *Get User Access Token* with `pages_show_list`, `pages_read_engagement` and
   `pages_manage_posts`.
3. **Access Token Debugger**: paste it, *Extend Access Token* (that one lasts 60 days).
4. Back in the Explorer, with the extended token, run `me/accounts`. Your Page's `access_token` there **never
   expires** (check it in the debugger: "Expires: Never"), and its `id` is the Page ID.
5. Variable `FACEBOOK_PAGE_ID`; secret `FACEBOOK_PAGE_TOKEN`.

### Instagram

Instagram must be a **professional** account (Business or Creator: Instagram settings → Account type and tools).
Every Instagram post needs a picture: each project in `projects.json` has an `image`.

1. Use case: **Manage messaging and content on Instagram** → *API setup with Instagram login*.
2. Add your Instagram account and **Generate token** (it lasts 60 days; the Refresh tokens workflow renews it each
   month). The account's numeric ID is shown beside it.
3. Secret `INSTAGRAM_TOKEN`; variable `INSTAGRAM_USER_ID`.

### Threads

1. Use case: **Access the Threads API**, with `threads_basic` and `threads_content_publish`.
2. App roles → add your Threads account as a **Threads Tester**, then accept the invite in the Threads app (Settings →
   Account → Website permissions → Invites).
3. Use case settings → **User Token Generator** → generate a token for your account.
   If it is a short-lived one (an hour), swap it for a 60-day one by opening this in a browser:
   `https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=<APP SECRET>&access_token=<TOKEN>`
   (the app secret is under Threads use case settings).
4. Secret `THREADS_TOKEN`. (`THREADS_USER_ID` is optional; it defaults to your own account.)

## Keeping the 60-day tokens alive

The **Refresh tokens** workflow renews the Threads and Instagram tokens on the 1st of each month and saves them back
here. For that it needs one more secret, **`SECRETS_PAT`**: github.com → Settings → Developer settings →
**Fine-grained tokens** → Generate, *Only select repositories* → this repo, permission **Secrets: Read and write**.
If a refresh ever fails, it opens an issue, with weeks to spare before the token runs out.

## Optional

- `RELEASES_TOKEN` (secret): only needed to watch a **private** repo. A fine-grained token with *Contents: Read* on
  those repos.
- `META_GRAPH_VERSION` (variable): the Facebook/Instagram Graph API version, default `v23.0`. Meta retires each
  version about two years after it comes out; set a newer one then.

## Ko-fi

Ko-fi has no way to post from outside (its token only tells *you* about donations), so each new release opens an
**issue** here titled "Ko-fi: …" with the post ready to paste and links to everywhere it went. GitHub emails you
about it; close it once it's on Ko-fi.
