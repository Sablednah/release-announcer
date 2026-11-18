#!/usr/bin/env python3
"""Announce new GitHub releases on social networks.

One central repo holds the credentials; projects.json lists the repos (and tag patterns) to watch. Each run reads
those repos' releases, and every release not yet in state/announced.json is posted to every network that has
credentials. Standard library only, so it runs on any GitHub runner with no install step.

    announce.py check [--dry-run]                       announce every new release (the scheduled run)
    announce.py post REPO TAG [--dry-run] [--only x,bluesky] [--text "..."]   announce one release now
    announce.py seed                                     mark every existing release as announced
    announce.py refresh OUTFILE                          refresh the 60-day Threads/Instagram tokens into OUTFILE

Networks: Bluesky, Mastodon, X, Tumblr, Facebook Page, Instagram, Threads. A network without credentials is
skipped. Ko-fi has no posting API: the workflow opens an issue with a ready-to-paste post instead.

A release body can steer its own announcement with an HTML comment (invisible on GitHub):
    <!-- announce: Custom text for the post -->      replaces the headline
    <!-- announce: skip -->                          never announce this release
"""
import base64, hashlib, hmac, json, os, re, secrets, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state", "announced.json")
PROJECTS = os.path.join(HERE, "projects.json")
UA = "release-announcer/1.0"
MAX_ATTEMPTS = 3          # a network that fails this many runs in a row is given up on (and reported)
NETWORKS = ["bluesky", "mastodon", "x", "tumblr", "facebook", "instagram", "threads"]


def env(name, default=""):
    return os.environ.get(name, "").strip() or default


# ---------------------------------------------------------------- HTTP

class HttpError(Exception):
    pass


def http(method, url, *, headers=None, data=None, json_body=None, form=None, raw=False, timeout=60):
    h = {"User-Agent": UA, **(headers or {})}
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        h["Content-Type"] = "application/json"
    elif form is not None:
        body = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = data
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise HttpError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {detail}") from None
    if raw:
        return out
    return json.loads(out) if out else {}


# ---------------------------------------------------------------- OAuth 1.0a (X and Tumblr)

def _pct(s):
    return urllib.parse.quote(str(s), safe="~-._")


def oauth1_header(method, url, consumer_key, consumer_secret, token, token_secret, params=None,
                  nonce=None, timestamp=None):
    """HMAC-SHA1 OAuth 1.0a. `params` are query/form params that must be signed; a JSON body is never signed."""
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    allp = {**(params or {}), **oauth}
    pstr ="&".join(f"{k}={v}" for k, v in sorted((_pct(k), _pct(v)) for k, v in allp.items()))
    base = "&".join([method.upper(), _pct(url), _pct(pstr)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


# ---------------------------------------------------------------- composing the post

URL_RE = re.compile(r"https?://\S+")


def x_length(text):
    """X and Mastodon count every link as 23 characters."""
    return len(URL_RE.sub("x" * 23, text))


def compose(post, limit, measure=len):
    """Headline + link + hashtags, dropping hashtags then shortening the headline until it fits `limit`."""
    head, link, tags = post["headline"], post["link"], post["hashtags"]
    tagline = " ".join("#" + t for t in tags)

    def build(h, with_tags):
        parts = [h]
        if link:
            parts.append(link)
        if with_tags and tagline:
            parts.append(tagline)
        return "\n\n".join(parts)

    for with_tags in (True, False):
        text = build(head, with_tags)
        if measure(text) <= limit:
            return text
    h = head
    while h and measure(build(h + "…", False)) > limit:
        h = h[:-1]
    return build(h.rstrip() + "…", False)


def post_for(rule, release):
    tag, title = release["tag_name"], (release.get("name") or release["tag_name"]).strip()
    body = release.get("body") or ""
    m = re.search(r"<!--\s*announce:\s*(.*?)\s*-->", body, re.S)
    override = m.group(1).strip() if m else ""
    if override.lower() == "skip":
        return None
    version = re.sub(rule.get("tags", "^"), "", tag, count=1) if rule.get("tags") else tag
    name = rule.get("name", "")
    if name and name.lower() not in title.lower():      # "2.13.0 — Heal heals you" -> "LegendQuest 2.13.0 — ..."
        title = f"{name} {title}"
    headline = override or rule.get("template", "New release: {title}").format(
        title=title, name=name, version=version, tag=tag)
    return {
        "repo": rule["repo"], "tag": tag, "title": title, "headline": headline,
        "link": rule.get("link") or release["html_url"], "release_url": release["html_url"],
        "hashtags": rule.get("hashtags", []), "image": rule.get("image", ""),
        "networks": rule.get("networks", NETWORKS),
    }


# ---------------------------------------------------------------- networks
# Each returns the URL of the new post (or True), or raises. `dry` prints what it would send instead.

def bluesky(post, dry):
    handle, password = env("BLUESKY_HANDLE"), env("BLUESKY_APP_PASSWORD")
    if not (handle and password):
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    service = env("BLUESKY_SERVICE", "https://bsky.social")
    text = compose(post, 300)
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(),
              "langs": ["en"]}
    # Bluesky does not turn links or hashtags into links by itself: each needs a facet over its UTF-8 bytes.
    facets, b = [], text.encode()
    for mm in URL_RE.finditer(text):
        s = len(text[:mm.start()].encode()); e = s + len(mm.group().encode())
        facets.append({"index": {"byteStart": s, "byteEnd": e},
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": mm.group()}]})
    for mm in re.finditer(r"(?<!\S)#(\w+)", text):
        s = len(text[:mm.start()].encode()); e = s + len(mm.group().encode())
        facets.append({"index": {"byteStart": s, "byteEnd": e},
                       "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": mm.group(1)}]})
    if facets:
        record["facets"] = facets
    card = {"uri": post["link"], "title": post["title"], "description": post["headline"]}
    if dry:
        print(f"  [bluesky] {len(text)} chars, card {card['uri']}, thumb {post['image'] or '-'}\n{indent(text)}")
        return "dry-run"
    sess = http("POST", f"{service}/xrpc/com.atproto.server.createSession",
                json_body={"identifier": handle, "password": password})
    auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    if post["image"]:
        try:
            img = http("GET", post["image"], raw=True)
            if len(img) <= 976_000:
                blob = http("POST", f"{service}/xrpc/com.atproto.repo.uploadBlob", data=img,
                            headers={**auth, "Content-Type": "image/jpeg"})
                card["thumb"] = blob["blob"]
        except HttpError as e:
            print(f"  [bluesky] no thumbnail: {e}")
    record["embed"] = {"$type": "app.bsky.embed.external", "external": card}
    r = http("POST", f"{service}/xrpc/com.atproto.repo.createRecord", headers=auth,
             json_body={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record})
    return f"https://bsky.app/profile/{handle}/post/{r['uri'].rsplit('/', 1)[-1]}"


def mastodon(post, dry):
    instance, token = env("MASTODON_INSTANCE").rstrip("/"), env("MASTODON_TOKEN")
    if not (instance and token):
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    if not instance.startswith("http"):
        instance = "https://" + instance
    text = compose(post, 500, x_length)
    if dry:
        print(f"  [mastodon] {x_length(text)} chars on {instance}\n{indent(text)}")
        return "dry-run"
    key = hashlib.sha256(f"{post['repo']}@{post['tag']}".encode()).hexdigest()   # a retry can never double-post
    r = http("POST", f"{instance}/api/v1/statuses", form={"status": text, "visibility": "public", "language": "en"},
             headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key})
    return r.get("url") or True


def x(post, dry):
    keys = [env(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(keys):
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    text = compose(post, 280, x_length)
    if dry:
        print(f"  [x] {x_length(text)} chars\n{indent(text)}")
        return "dry-run"
    url = "https://api.x.com/2/tweets"
    auth = oauth1_header("POST", url, keys[0], keys[1], keys[2], keys[3])
    r = http("POST", url, json_body={"text": text}, headers={"Authorization": auth})
    return f"https://x.com/i/status/{r['data']['id']}"


def tumblr(post, dry):
    keys = [env(k) for k in ("TUMBLR_CONSUMER_KEY", "TUMBLR_CONSUMER_SECRET", "TUMBLR_TOKEN", "TUMBLR_TOKEN_SECRET")]
    blog = env("TUMBLR_BLOG")
    if not (all(keys) and blog):
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    blog = blog.replace("https://", "").replace("http://", "").strip("/")
    content = [{"type": "text", "text": post["headline"]}]
    if post["image"]:
        content.append({"type": "image", "media": [{"url": post["image"], "type": "image/jpeg"}]})
    content.append({"type": "link", "url": post["link"], "title": post["title"]})
    payload = {"content": content, "tags": ",".join(post["hashtags"]), "state": "published"}
    if dry:
        print(f"  [tumblr] blog {blog}, tags {payload['tags']}\n{indent(post['headline'] + chr(10) + post['link'])}")
        return "dry-run"
    url = f"https://api.tumblr.com/v2/blog/{blog}/posts"
    auth = oauth1_header("POST", url, *keys)
    r = http("POST", url, json_body=payload, headers={"Authorization": auth})
    pid = r.get("response", {}).get("id_string") or r.get("response", {}).get("id")
    return f"https://{blog}/post/{pid}" if pid else True


GRAPH = lambda: f"https://graph.facebook.com/{env('META_GRAPH_VERSION', 'v23.0')}"


def facebook(post, dry):
    page, token = env("FACEBOOK_PAGE_ID"), env("FACEBOOK_PAGE_TOKEN")
    if not (page and token):
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    text = compose(post, 5000)
    if dry:
        print(f"  [facebook] page {page}, link preview {post['link']}\n{indent(text)}")
        return "dry-run"
    r = http("POST", f"{GRAPH()}/{page}/feed", form={"message": text, "link": post["link"], "access_token": token})
    return f"https://www.facebook.com/{r['id']}" if r.get("id") else True


def _meta_publish(base, user, token, create, label):
    """Instagram and Threads both make a container, wait for it, then publish it."""
    c = http("POST", f"{base}/{user}/{'media' if label == 'instagram' else 'threads'}", form={**create, "access_token": token})
    cid = c["id"]
    for _ in range(30):
        st = http("GET", f"{base}/{cid}?fields=status{',status_code' if label == 'instagram' else ''}&access_token={token}")
        s = st.get("status_code") or st.get("status") or "FINISHED"
        if s == "FINISHED":
            break
        if s in ("ERROR", "EXPIRED"):
            raise HttpError(f"{label} container {cid}: {st}")
        time.sleep(3)
    r = http("POST", f"{base}/{user}/{'media_publish' if label == 'instagram' else 'threads_publish'}",
             form={"creation_id": cid, "access_token": token})
    return r.get("id")


def instagram(post, dry):
    user, token = env("INSTAGRAM_USER_ID", "me"), env("INSTAGRAM_TOKEN")
    if not token:
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    if not post["image"]:
        print("  [instagram] skipped: this project has no image, and Instagram posts must have one")
        return "skipped: no image"
    text = compose(post, 2200)          # links in a caption are not clickable, but the address still helps
    if dry:
        print(f"  [instagram] image {post['image']}\n{indent(text)}")
        return "dry-run"
    base = f"https://graph.instagram.com/{env('META_GRAPH_VERSION', 'v23.0')}"
    pid = _meta_publish(base, user, token, {"image_url": post["image"], "caption": text}, "instagram")
    return f"instagram media {pid}"


def threads(post, dry):
    user, token = env("THREADS_USER_ID", "me"), env("THREADS_TOKEN")
    if not token:
        if not dry:
            return None
        print("  (no credentials yet: preview only)")
    text = compose(post, 500)
    if dry:
        print(f"  [threads] link card {post['link']}\n{indent(text)}")
        return "dry-run"
    pid = _meta_publish("https://graph.threads.net/v1.0", user, token,
                        {"media_type": "TEXT", "text": text, "link_attachment": post["link"]}, "threads")
    return f"threads post {pid}"


POSTERS = {"bluesky": bluesky, "mastodon": mastodon, "x": x, "tumblr": tumblr, "facebook": facebook,
           "instagram": instagram, "threads": threads}


def indent(t):
    return "\n".join("      | " + line for line in t.splitlines())


# ---------------------------------------------------------------- releases and state

def releases(repo):
    headers = {"Accept": "application/vnd.github+json"}
    tok = env("RELEASES_TOKEN") or env("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return http("GET", f"https://api.github.com/repos/{repo}/releases?per_page=30", headers=headers)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"seeded": [], "releases": {}}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")


def rule_key(rule):
    return f"{rule['repo']} {rule.get('tags', '')}"


def matching(rule, rels):
    pat = re.compile(rule.get("tags") or "")
    return [r for r in rels if not r.get("draft") and not r.get("prerelease") and pat.search(r["tag_name"])]


def announce(post, record, dry, only=None):
    """Post to every network not yet done for this release. Returns the networks given up on in this run."""
    gave_up = []
    print(f"== {post['repo']} {post['tag']}: {post['headline']}")
    for name in post["networks"]:
        if only and name not in only:
            continue
        done = record.get(name)
        if isinstance(done, str) or done is True:
            print(f"  [{name}] done earlier: {done}")
            continue
        try:
            res = POSTERS[name](post, dry)
        except Exception as e:                       # one network failing must not stop the others
            n = (done or {}).get("failed", 0) + 1 if isinstance(done, dict) else 1
            print(f"  [{name}] FAILED ({n}/{MAX_ATTEMPTS}): {e}")
            if not dry:
                record[name] = {"failed": n, "error": str(e)[:300]} if n < MAX_ATTEMPTS else f"gave up: {str(e)[:200]}"
                if n >= MAX_ATTEMPTS:
                    gave_up.append(name)
            continue
        if res is None:
            print(f"  [{name}] no credentials, skipped")
            if not dry:
                record[name] = "skipped: no credentials"
            continue
        if not dry:
            record[name] = res
            print(f"  [{name}] posted: {res}")
    return gave_up


def failure_issue(post, record, names):
    lines = [f"Announcing {post['title']} failed {MAX_ATTEMPTS} times on: {', '.join(names)}. It will not be tried again.",
             "", *[f"- {n}: {record.get(n)}" for n in names], "",
             "Fix the credentials (SETUP.md), then post it by hand: Actions -> Announce releases -> Run workflow, "
             f"repo `{post['repo']}`, tag `{post['tag']}`, only `{','.join(names)}`, dry run unticked."]
    return {"title": f"Announce failed: {post['title']}", "body": "\n".join(lines)}


def kofi_issue(post, record):
    """Ko-fi cannot be posted to; the workflow opens this as an issue so the text is a paste away."""
    lines = [f"Ko-fi has no posting API, so here is {post['title']} ready to paste into a Ko-fi post.", "",
             "**Title**", "", post["title"], "", "**Text**", "", post["headline"], "", post["link"], "",
             f"Release notes: {post['release_url']}", ""]
    posted = [f"- {k}: {v}" for k, v in record.items() if isinstance(v, str) and v.startswith("http")]
    if posted:
        lines += ["Posted:", *posted, ""]
    failed = [f"- {k}: {v}" for k, v in record.items() if isinstance(v, str) and v.startswith("gave up")]
    if failed:
        lines += ["**Failed** (not retried):", *failed]
    return {"title": f"Ko-fi: {post['title']}", "body": "\n".join(lines)}


def cmd_check(dry, seed_only=False):
    rules = json.load(open(PROJECTS))
    st = load_state()
    issues = []
    for rule in rules:
        rels = matching(rule, releases(rule["repo"]))
        key = rule_key(rule)
        if key not in st["seeded"]:
            # First sight of a project: everything already released counts as announced, so adding a repo to
            # projects.json never floods the feeds with its back catalogue.
            for r in rels:
                st["releases"].setdefault(f"{rule['repo']}@{r['tag_name']}", {"seeded": True})
            st["seeded"].append(key)
            print(f"seeded {key}: {len(rels)} existing release(s) marked as announced")
            continue
        if seed_only:
            continue
        for r in reversed(rels):                     # oldest first
            rk = f"{rule['repo']}@{r['tag_name']}"
            rec = st["releases"].get(rk, {})
            if rec.get("seeded") or rec.get("skip"):
                continue
            post = post_for(rule, r)
            if post is None:
                st["releases"][rk] = {"skip": True}
                continue
            fresh = not rec
            gave_up = announce(post, rec, dry)
            if not dry:
                st["releases"][rk] = rec
                if fresh:
                    issues.append(kofi_issue(post, rec))
                elif gave_up:
                    issues.append(failure_issue(post, rec, gave_up))
    if not dry:
        save_state(st)
        if issues:
            with open(os.path.join(HERE, "kofi-issues.json"), "w") as f:
                json.dump(issues, f)


def cmd_post(repo, tag, dry, only, text):
    rules = [r for r in json.load(open(PROJECTS)) if r["repo"] == repo and re.search(r.get("tags") or "", tag)]
    rule = rules[0] if rules else {"repo": repo}
    rel = next((r for r in releases(repo) if r["tag_name"] == tag), None)
    if not rel:
        sys.exit(f"!! {repo} has no release {tag}")
    post = post_for(rule, rel) or post_for(rule, {**rel, "body": ""})
    if text:
        post["headline"] = text
    st = load_state()
    rk = f"{repo}@{tag}"
    rec = st["releases"].get(rk, {})
    rec.pop("seeded", None)
    rec.pop("skip", None)
    announce(post, rec, dry, only)
    if not dry:
        st["releases"][rk] = rec
        save_state(st)
        with open(os.path.join(HERE, "kofi-issues.json"), "w") as f:
            json.dump([kofi_issue(post, rec)], f)


def cmd_refresh(outfile):
    """Threads and Instagram long-lived tokens last 60 days; each refresh gives a fresh 60. Run monthly."""
    out, problems = {}, []
    for name, url, grant in (("THREADS_TOKEN", "https://graph.threads.net/refresh_access_token", "th_refresh_token"),
                             ("INSTAGRAM_TOKEN", "https://graph.instagram.com/refresh_access_token", "ig_refresh_token")):
        tok = env(name)
        if not tok:
            continue
        try:
            r = http("GET", f"{url}?grant_type={grant}&access_token={urllib.parse.quote(tok)}")
            out[name] = r["access_token"]
            print(f"{name}: refreshed, valid {int(r.get('expires_in', 0)) // 86400} days")
        except Exception as e:
            problems.append(f"{name}: {e}")
            print(f"{name}: FAILED {e}")
    with open(outfile, "w") as f:
        json.dump(out, f)
    if problems:
        sys.exit(1)


def main(argv):
    args = argv[1:]
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    def opt(name):
        if name in args:
            i = args.index(name)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return ""

    only = [o.strip() for o in opt("--only").split(",") if o.strip()]
    text = opt("--text")
    if not args:
        sys.exit(__doc__)
    if args[0] == "check":
        cmd_check(dry)
    elif args[0] == "seed":
        cmd_check(False, seed_only=True)
    elif args[0] == "post" and len(args) == 3:
        cmd_post(args[1], args[2], dry, only, text)
    elif args[0] == "refresh" and len(args) == 2:
        cmd_refresh(args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
