# Deliverables

## Presentations

| File | What it is |
| --- | --- |
| `Cardiac_Opportunity_Agent_Round1.pptx` | The round-one submission: cover, the three permitted slides, and four appendix slides covering the framework, robustness, sources and limitations. |
| `Cardiac_Opportunity_Agent_Detailed.pptx` | The version for the shortlist round: the same argument at greater depth, plus architecture, the demand-versus-price read, the cross-hierarchy franchise view and an execution sequence. |

Both are generated from the live analysis, so a figure on a slide cannot
disagree with the scorecard behind it.

```bash
python scripts/build_visuals.py    # render the charts
python scripts/build_deck.py       # build both decks
python scripts/check_deck.py       # verify the layout
```

`check_deck.py` reads the shape geometry back out of the files and reports text
overflow, overlapping boxes, elements too close to the slide edge and font
sizes below the readable floor. It exits non-zero if it finds anything, so it
can gate a build.

## Written answers

The written deliverables live in `docs/` so that they are also published by the
documentation site:

| Document | Content |
| --- | --- |
| [`docs/case-answers.md`](../docs/case-answers.md) | All four case questions answered, with figures and citations |
| [`docs/slide-storyboard.md`](../docs/slide-storyboard.md) | What goes on each slide and why |
| [`docs/appendix-sources.md`](../docs/appendix-sources.md) | Every external source, formatted for the appendix |

## Data exports

`cardiac-agent export` writes the scorecard, the excluded spaces, the company
facts and the run metadata to `exports/`, for anyone who wants to rebuild a
chart in Excel or check a number by hand.
