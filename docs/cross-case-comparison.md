# Cross-case comparison

This memo compares the two filled example packages.

## Sources

1. **Wikipedia:Signs of AI writing** — text-dominant wiki/project page
2. **StarTrail-org/PixelRAG repository page** — visually structured repository page

## Comparison table

| Dimension | Wikipedia package | PixelRAG package |
|---|---|---|
| Source type | Text-heavy wiki/project page | Visually structured repository page |
| Primary value | Heuristic rules and editing signals | Workflow, routing, and integration guidance |
| Best ingestion mode | Text-first | Hybrid |
| Visual path role | Optional verification | Important complementary evidence |
| Best first skill | AI Writing Tells Reviewer | Visual Web-Ingestion Advisor |
| Skill family | Reviewer, rewriter, editor companion | Ingestion advisor, integration planner, workflow coach |
| Rule density | High | Medium |
| Procedure density | Low | High |
| Maintenance sensitivity | Heuristic and caveat drift | Command, workflow, and framing changes |
| Promotion posture | Monitored, manual approval | Monitored, manual approval |

## Main lessons

### 1. The page type determines the skill form

A heuristic-rich wiki page becomes a reviewer or rewriter. A visually structured repo page becomes an advisor or workflow skill. The builder should not force all pages into the same skill template.

### 2. Ingestion mode is a build decision

Text-first is the most efficient path for parser-friendly prose. Hybrid is better when layout, code, or structure carries meaning alongside text.

### 3. Opportunity mapping must precede compilation

Both examples show that the right skill form is not obvious from the URL alone. The builder needs a classification and opportunity-mapping stage before it can compile well.

### 4. Governance should match source failure modes

For Wikipedia, the risk is heuristic drift or caveat changes. For the PixelRAG repo, the risk is command surface or workflow changes. The same governance policy applies but the review criteria differ.

### 5. Dual architecture is justified

The two examples together confirm that the meta-skill needs a routing layer, not a single ingestion path.
