# scriptt

A Claude Code hook.

> This branch is the small first release: the hook and its website. The rest of scriptt
> (the harness, the library, the notebooks) is kept on other branches and comes back later.

## Layout

| Path | What it holds |
|---|---|
| `hook/` | The hook. See `hook/README.md`. |
| `web/site/index.html` | The website: one file with an interactive demo of the hook. |
| `web/build.sh` | Copies the site into `web/public/`, the folder that is deployed. |

## Preview the site

```bash
sh web/build.sh && python3 -m http.server 2750 --directory web/public
```

Then open http://127.0.0.1:2750. Deploying is a separate, manual step.
