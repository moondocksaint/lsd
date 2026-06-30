# Ingestion Modes

LSD supports three ingestion modes. The builder selects the mode automatically based on source classification, or the user can override.

## Text-first

The page is fetched and normalised as text. Visual artifacts are not preserved unless the user requests them.

**Best for**: wiki articles, documentation pages, blog posts, long-form prose, FAQ pages, style guides.

**Strengths**:
- Fast, lightweight, and diffable.
- Produces a clean normalised source artifact.
- Easy version control and change detection.

**Limitations**:
- Loses layout, visual emphasis, and non-textual structure.
- May flatten table meaning if tables are complex.

**Example**: Wikipedia:Signs of AI writing

## Hybrid

The page is fetched as text and also preserved as a rendered screenshot with tiles. Both artifacts contribute to the package. The skill is compiled primarily from the text artifact but the visual artifact is kept as a complementary evidence layer.

**Best for**: repository pages, API documentation, reference pages with important tables or code blocks, pages where UI structure carries meaning.

**Strengths**:
- Preserves layout-dependent meaning alongside text.
- Provides a visual verification layer for the text extraction.
- Supports richer update detection (both text hash and visual diff).

**Limitations**:
- Requires more storage.
- Visual artifacts need refresh when the page changes significantly.
- Reconciliation between text and visual layers adds a review step.

**Example**: StarTrail-org/PixelRAG repository page

## Visual-first

The page is primarily retrieved as a rendered screenshot. The text layer is secondary and may be extracted from the image via VLM rather than HTML parsing.

**Best for**: dashboards, canvas-heavy pages, pages with diagrams or infographics as primary content, parser-hostile interfaces, pages where the rendered appearance is the only reliable representation.

**Strengths**:
- Captures exactly what a human sees.
- Works even when text extraction is unreliable.
- Preserves spatial relationships and visual hierarchy.

**Limitations**:
- Higher operational cost.
- Harder to diff and version.
- Depends on VLM quality for downstream extraction.

**Example**: (future test) — a visually heavy dashboard or infographic-first documentation page.

## Routing decision table

| Signal | Text-first | Hybrid | Visual-first |
|---|---|---|---|
| Prose-dominant | ✓ | | |
| Parser-friendly structure | ✓ | | |
| Repo / code / tables | | ✓ | |
| Important visual grouping | | ✓ | |
| Canvas / diagram dominant | | | ✓ |
| Parser-hostile | | | ✓ |
| Dashboard / interface | | | ✓ |
