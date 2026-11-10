# scriptt 0.1.5

A harness for Claude Code in 2 files. Each message to an agent is a demand for computation. A small decision
model, d1, decides which functions of your world each sentence of a message asks for, before Claude reads it.
You see the decision on your own message, and you can disagree with it.

```bash
curl -fsSL https://scriptt.ai/install.sh | sh
```

- `hook/harness.py` and `hook/world.py`: the harness and the whitelist. See [hook/README.md](hook/README.md).
- `hook/mod/`: a mod for the Claude desktop app that draws d1's reading on each message that you type.
  In a terminal session of Claude Code: `/plugin install scriptt --marketplace maxtheman/scriptt`.
- `web/site/`: the page at [scriptt.ai](https://scriptt.ai). `python3.14 .scriptt/harness.py serve` shows the same page with your own events.
- `sh web/build.sh` builds the site into `web/public/`. `(cd web && npx cf deploy)` deploys it.

This branch is the small release. The earlier library and notebooks are in the history and on other branches.
