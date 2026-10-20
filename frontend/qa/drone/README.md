# Drone workflow — explicit local adapters

From repository root:

```bash
python frontend/qa/drone/run.py
```

Requires the existing backend `.venv`, frontend frozen-lockfile dependencies,
Python Playwright/Pillow and Chromium. Dedicated ports **8013 / 5183**; artifacts
`/tmp/saq-drone-browser` or `SAQ_QA_ARTIFACTS`. Refuses occupied ports and stops
only its own processes. No shared runner or map A files are modified.

The runner scrubs Firebase/Gemini/SearchAPI/Vite configuration. Isolated runtime
uses MemoryStore, test identity, FakeFiles and synthetic Gemini MockTransport.
Browser rejects non-local requests. The drawn PNG is explicitly synthetic, not a
real drone photo. Three statuses are manufactured to verify UI behaviour; they
are not evidence of real model accuracy or construction-code compliance.

Checks: protected navigation/deep route; edit/add/remove checklist; upload and
byte-identical authenticated download; no automatic AI; explicit analysis;
visible/not_visible/uncertain; expert decisions and divider-separated history;
old-review isolation after a new analysis; reload without AI; unchanged R1–R6;
desktop/mobile layout; no external traffic/page errors. No paid requests or cloud
writes. Actual Gemini quality and Firebase Storage require separate cloud checks.
