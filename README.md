# Release Announcer

Posts every new GitHub release of the projects in `projects.json` to Bluesky, Mastodon, Tumblr, a Facebook Page,
Instagram and Threads, and opens a ready-to-paste issue for Ko-fi. All the keys live here, once; the projects
themselves need nothing.

Every half hour **Announce releases** reads each project's releases. A release not yet in `state/announced.json` is
posted to every network that has credentials, and the state is committed. A network that fails is retried on the
next two runs, then reported in the Ko-fi issue. Drafts and pre-releases are never announced.

Setting up the networks: **[SETUP.md](SETUP.md)**.

## Adding a project

One entry in `projects.json`:

```json
{"repo": "Sablednah/MobHealth-NeoForge", "tags": "^v(?=\\d)", "name": "MobHealth",
 "link": "https://www.curseforge.com/minecraft/mc-mods/...",
 "hashtags": ["Minecraft", "MinecraftMods"], "image": "https://raw.githubusercontent.com/..../screenshot.jpg"}
```

- `tags`: which of the repo's release tags this entry covers (a regular expression). One repo can have several
  entries, like CityWorld's add-ons, each with its own name and link.
- `name`: put in front of the release title when the title doesn't already say it.
- `link`: where the post points (default: the GitHub release page).
- `image`: a public JPEG URL. Instagram needs one; Bluesky and Tumblr show it.
- Optional: `template` (default `New release: {title}`; also `{name}`, `{version}`, `{tag}`) and `networks` (a list,
  to post a project to only some).

A project's existing releases are marked as announced the first time it's seen, so adding one never floods the
feeds with its back catalogue. To announce an older release anyway, run the workflow by hand with its repo and tag.

## Steering one release

In the release notes, an HTML comment (invisible on GitHub):

- `<!-- announce: Trains in the subway! CityWorld 7.2.0 is out -->` replaces the headline.
- `<!-- announce: skip -->` keeps the release quiet.

## Posting something that is not a release

**Post a note** is for news with no release behind it, such as a significant change to the website. It goes to the
Facebook Page unless told otherwise:

```bash
gh workflow run say.yml -R Sablednah/release-announcer -f dry_run=false \
  -f text="The CrawlSpace pages are live: dungeon cutaways and the mobile game" \
  -f link=https://sablecraft.co.uk/legendquest-crawlspace/
```

- `only`: `facebook` by default; a list of networks, or `all`.
- `hashtags`, `image` (default `images/sablecraft.jpg`) and `title` are optional.
- Leave `dry_run` out to see every network's post without sending anything.

A note is remembered by its text and link (under `notes` in `state/announced.json`, with where it was posted), so
the same one twice posts once.

## The Facebook Page's picture and cover

**Update the Facebook Page** sets the Page's profile picture and cover photo from `images/page/profile.png` and
`images/page/cover.png`, then reads both back from the Page. It uses the Page token the posts already use. A dry run
(the default) only shows what the Page has now. [images/page/README.md](images/page/README.md) says how the two
pictures are made.

## Running it locally

`python3 announce.py post Sablednah/CityWorld-ReForged v7.2.0 --dry-run` prints every network's post, and
`python3 announce.py say "..." --dry-run` a note's. No dependencies beyond Python 3.
