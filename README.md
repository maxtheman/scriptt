# scriptt 0.1.1

A harness for Claude Code in 2 files. Each message to an agent is a demand for computation. A small decision
model, d1, decides which functions of your world a message demands, before Claude reads it. You drag to disagree.

```bash
curl -fsSL https://scriptt.ai/install.sh | sh
```

- `hook/harness.py` and `hook/world.py`: the harness and the whitelist. See [hook/README.md](hook/README.md).
- `web/site/`: the page at [scriptt.ai](https://scriptt.ai). `python3.14 .scriptt/harness.py serve` shows the same page with your own events.
- `sh web/build.sh` builds the site into `web/public/`. `(cd web && npx cf deploy)` deploys it.

This branch is the small release. The earlier library and notebooks are in the history and on other branches.
