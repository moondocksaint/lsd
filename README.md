# LSD — Link-to-Skill Designer

> Turn any webpage into a reusable Claude skill.

LSD is a meta-skill builder. Give it a URL. It reads the page, classifies what kind of skill the page supports, chooses the right ingestion mode (text-first, hybrid, or visual-first), extracts and normalises the source, generates a complete skill package, and wires up source-dependency tracking so the skill can be refreshed when the page changes.

## Quick start

```
lsd build <url>
```

## Docs

See [`docs/`](docs/) for architecture, spec, and examples.

## Examples

See [`examples/`](examples/) for filled example packages:
- [`examples/wikipedia-ai-writing/`](examples/wikipedia-ai-writing/) — text-dominant source
- [`examples/pixelrag-repo/`](examples/pixelrag-repo/) — hybrid / visually structured source

## Status

Early scaffold. See [`ROADMAP.md`](ROADMAP.md).
