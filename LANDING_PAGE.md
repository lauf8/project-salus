# Landing page

The public landing page is served at `/overview` (`front/src/Overview.jsx`, `front/src/overview.css`, `front/src/overview-tour.js`). `front/src/bootstrap.jsx` loads it instead of the application when the path matches.

## Content

The sections follow the presentation narration, with the focus on prediction:

| Section id | Narration |
| --- | --- |
| `top` | Astronauts will be too far from Earth to wait for help. |
| `problem` | Health care in space is reactive. |
| `data` | Physical and mental health, spacecraft conditions and NASA space weather. |
| `prediction` | Using artificial intelligence, it anticipates risks. |
| `alerts` | It alerts the medical team before they become problems. |
| `learning` | With every mission, it learns and gets more accurate. |
| `closing` | Project Salus: to predict is to protect. |

Screenshots live in `front/public/overview/` and come from `img/` (see `asset-audit.json`). They use fictional demonstration records. The hero chart is an illustration, labeled as such. Model metrics shown come from the synthetic cohort documented in `PREDICTIVE_INTELLIGENCE.md` and are labeled as pipeline verification, not clinical validation.

## Narrated tour

Open `/overview?tour` to scroll through the sections automatically while the narration plays. The default length is 42 seconds; set another length with `/overview?tour=50`. Each section starts at a time proportional to the number of narration words before it. Any key press stops the tour.

## Limitations

- The mission-risks screenshot shows synthetic mission names from the seed data (for example `Atlântico 03`, `Vanguarda`, `Nascente`). They are proper names in the image, not interface text.
- The tour does not play audio. Start the narration and the page at the same time.

## Verification

From `front/`:

```bash
npm test
npm run typecheck
npm run build
npm run test:overview:e2e
```

`test:overview:e2e` starts Vite, renders the page at desktop and phone widths, checks that the visible text, alternative text and labels are English, that every image loads, that there is no horizontal scroll, that the screenshot viewer opens and that the narrated tour reaches the closing section.
