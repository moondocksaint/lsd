# Source — StarTrail-org/PixelRAG repository

- Canonical URL: https://github.com/StarTrail-org/PixelRAG
- Retrieved: 2026-06-30T09:39:00Z
- Ingestion mode: hybrid

## Summary

PixelRAG is a visual retrieval system built by UC Berkeley SkyLab, BAIR, and the Berkeley NLP Group. It renders webpages, PDFs, and images as screenshots, then retrieves over the images directly rather than flattening pages into parsed text. The system claims 18.1% accuracy gains over text-based RAG on benchmarks and up to 10x cheaper token costs through screenshot tiling.

## Key workflow families

### Rendering
- `pixelshot` renders a URL or document to screenshot tiles.
- Custom Chromium renderer with GPU-accelerated preprocessing.
- Output: image tiles stored locally or in a vector index.

### Retrieval pipeline stages
- Render: page or document to screenshot.
- Chunk: slice screenshots into overlapping tiles.
- Embed: encode tiles using a LoRA dual-tower visual embedding model.
- Index: store in FAISS or compatible vector store.
- Serve: expose a search API.

### Plugin usage (Claude Code)
- `pixelbrowse` plugin lets Claude screenshot a page and read the resulting image instead of raw HTML.
- One-line install for the Claude Code plugin.

### Hosted index
- A hosted visual index of Wikipedia (~30M pages) is available.
- Can be queried directly without building a local index.

## Why it is a hybrid-ingestion source

The repository page is more visually structured than a prose wiki article. Meaning comes from text, commands, code blocks, pipeline stage descriptions, plugin framing, and repository-style UI. A hybrid posture is more appropriate than pure text extraction.

## Source notes

This is an early-stage open-source repository. Commands and workflow stages may change as the project matures. Review command surfaces on any material source update.
