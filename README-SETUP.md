# Setup and publishing guide

This folder holds a terminal-style GitHub profile README for **github.com/DrEnosh**.

## What's in here

| Path | What it is |
|---|---|
| `README.md` | The profile page. Banner, project cards, tools, contact links, and a text version for mobile and screen readers. |
| `assets/enosh-halftone.png` | Your dotted portrait, 1254×1254, black dots on a transparent background. Made from the halftone you uploaded, dots unchanged. |
| `assets/profile-banner.svg` | The terminal banner as a vector file (portrait and font embedded). This is the editable source. |
| `assets/profile-banner.png` | A 2× render of the banner. The README shows this one. |
| `assets/project-*.svg` | One card per featured project. Each is a link to its repo. |
| `assets/tools.svg` | Tools & Technologies panel. |
| `scripts/generate_halftone.py` | Turns any portrait photo into a halftone (Pillow + NumPy). |
| `scripts/build_assets.py` | Rebuilds the banner, cards and tools panel from the `CONFIG` block at the top of the file. |

### Why the README uses the PNG banner

GitHub serves SVG files from your repo under a strict security policy. I tested the banner SVG under that same policy in Chromium and the portrait and font both showed, but I couldn't test Firefox or Safari, and browsers don't all treat images embedded inside an SVG the same way. The project cards and tools panel only contain text, so the worst case there is a fallback monospace font. The banner holds your portrait, which has to show up every time, so the README points at the PNG render. The SVG stays in the repo as the source you edit.

## Values used (all verified, no placeholders)

| Item | Value | Where it came from |
|---|---|---|
| GitHub username | `DrEnosh` | Your connected GitHub account |
| GitHub | https://github.com/DrEnosh | Same |
| LinkedIn | https://www.linkedin.com/in/dr-enosh | You gave it earlier |
| Email | enosh729@gmail.com | You gave it earlier |
| DentoRoute | https://github.com/DrEnosh/dentoroute | Public repo, checked |
| PanoSlice | https://github.com/DrEnosh/panoslice | Public repo, checked |
| Healthcare Forecasting | https://github.com/DrEnosh/hospital-admission-forecasting | Public repo, checked |

**Name format:** the banner says `Dr. Enosh A Paulson` (no dot after the A), the way you asked for it before. To use `A.` instead, change `"name"` in `scripts/build_assets.py`, rebuild, and update the two places it appears in `README.md`.

## Publish it

### 1. Rename the repo

A profile README only appears when the repo name matches your username exactly. Your new repo is `DrEnosh/git-profile`, so:

1. Open https://github.com/DrEnosh/git-profile/settings
2. Under **General → Repository name**, type `DrEnosh` and click **Rename**.
3. Keep it **Public**.

GitHub will show a note saying `DrEnosh/DrEnosh` is a special repository. That means it worked.

### 2. Add the files

**Option A: in the browser**

1. Open https://github.com/DrEnosh/DrEnosh
2. **Add file → Upload files**.
3. Drag in `README.md`, `README-SETUP.md`, and the `assets` and `scripts` folders.
4. Commit message: `Add terminal-style profile README`. Click **Commit changes**.

**Option B: with git**

```bash
git clone https://github.com/DrEnosh/DrEnosh.git
cd DrEnosh
# copy README.md, README-SETUP.md, assets/ and scripts/ from this folder into here
git add README.md README-SETUP.md assets scripts
git commit -m "Add terminal-style profile README"
git push origin main
```

### 3. Check it

1. Open https://github.com/DrEnosh
2. Look at it in both dark and light theme (avatar menu → Settings → Appearance).
3. Open it on your phone. The banner text will be small there, which is what the **Text version** section at the bottom is for.
4. Click each project card and make sure it opens the right repo.

## Change the text later

1. Edit the `CONFIG` block at the top of `scripts/build_assets.py`.
2. Install the tools once:
   ```bash
   pip install pillow numpy fonttools brotli playwright
   playwright install chromium
   ```
3. Rebuild everything:
   ```bash
   python scripts/build_assets.py
   ```
4. If you changed a project, its link or a profile row, update `README.md` too (links and the text version live there).
5. Commit and push.

The first run downloads JetBrains Mono (SIL Open Font License) into `~/.cache/enosh-profile-fonts`. Only the letters you use get embedded in the SVGs.

## Make a new portrait from a photo

```bash
python scripts/generate_halftone.py my-photo.jpg -o assets/new-halftone.png --svg assets/new-halftone.svg
```

Useful options:

- `--crop x,y,w,h` crops a square around your face first (source pixels).
- `--cell 7` gives finer dots, `--cell 10` coarser ones.
- `--highlight 0.12` keeps teeth and skin highlights cleaner.
- `--gamma 1.2` darkens midtones, `--gamma 0.85` lightens them.
- `--background white` for a white background instead of transparent.

The script never writes over the input photo. Write to a new file first, compare, then rename it to `assets/enosh-halftone.png` if you prefer it, and run `build_assets.py` so the banner picks it up.
