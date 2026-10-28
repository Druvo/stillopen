# README pictures

Every picture in the README is made from the real app, with an invented demo person (Jane Doe, nine jobs across the stages, one tailored CV with a flagged claim,
a few public openings), never a real account. `manage.py e2e_seed --demo` makes the data; it refuses to run without `STILLOPEN_E2E=1`.

```bash
cd frontend
pnpm install && pnpm build
pnpm readme:images          # needs the Chrome you already have; E2E_PYTHON=path/to/python if python is not on your PATH, E2E_PORT to change port 8788
```

This writes `dashboard.png`, `board.png`, `cv-fact-check.png`, `insights.png`, `openings.png` (1440x900) and `mobile.png` (390x844) here, plus five frames in
`.frames/` (ignored by git). It is not part of `pnpm e2e`.

The GIF needs [ffmpeg](https://ffmpeg.org/) (nothing else uses it; no test needs it). From this folder:

```bash
ffmpeg -y -framerate 0.5 -i .frames/frame-%02d.png -vf "scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer" demo.gif
```

(`-framerate 0.5` shows each frame for two seconds; keep the result under 5 MB.) Re-run both steps whenever the screens change.
