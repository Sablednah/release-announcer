# The Facebook Page's pictures

`profile.png` (1024x1024) and `cover.png` (1640x924) are what **Actions -> Update the Facebook Page** uploads.
`../sablecraft.jpg` is the cover as a JPEG: the picture a note carries when it has none of its own.

Both are drawn from the website's own brand, so they change when it does: the `~/` mark is
`assets/img/logo-favicon.svg` in the `sablecraft` theme, the wordmark is the site header, and the colours and
fonts are the theme's `tailwind.config.js` (cobalt `#0047AB`, steel `#060C16`, JetBrains Mono, Space Grotesk).

Edit the `.html`, then render it with Chrome at the picture's exact size:

```bash
CH="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
"$CH" --headless=new --user-data-dir='C:\Users\<you>\AppData\Local\Temp\chrome-headless-sc' --hide-scrollbars \
  --force-device-scale-factor=1 --virtual-time-budget=8000 --window-size=1640,924 \
  --screenshot='D:\Repos\sable\Release-Announcer\images\page\cover.png' \
  'file:///D:/Repos/sable/Release-Announcer/images/page/cover.html'
```

(`--window-size=1024,1024` for `profile.html`. The separate `--user-data-dir` keeps it out of a Chrome that is
already open; `--virtual-time-budget` waits for the web fonts.)

- **The profile picture is cropped to a circle**, so the square has no rounded corners of its own and the mark
  stays well inside.
- **A phone shows the whole cover; a desktop shows only the middle band**, about 600 of the 924 pixels. Everything
  that matters sits between the four corner marks.
