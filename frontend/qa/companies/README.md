# Local company workflow (explicit adapters)

From repository root, with backend lockfile dependencies, frontend `npm ci`,
Python Playwright and Chromium installed:

```bash
python frontend/qa/companies/run.py
```

Uses dedicated localhost ports **8012 / 5182**, an isolated temporary working
folder, MemoryStore, synthetic Homeportal/ADATA/Gemini HTTP responses and test
identity. The runtime strips application credentials and Vite origins; it never
calls Firebase, public registries, Gemini or SearchAPI. Screenshots/results/logs:
`/tmp/saq-company-browser` (override `SAQ_QA_ARTIFACTS`). Browser blocks non-local
requests. It does not click source links; it validates their exact targets.

The synthetic QA workspace explicitly sets `demo_only=False` to exercise the
optional real-scope creation contract. That is not a production setting change
or import of real companies. Test sources use fictional BINs/names/addresses.

Checks: login, search → preview → explicit save/import, two separate roles on the
complex, company page, BIN-matched registration citation, explicit refresh,
direct-page reload, mobile overflow and unauthenticated API denial.

The common release runner and map A files are untouched. This separate runner
reuses only the existing release test Auth/Firebase adapters. It stops only its
own process groups, refuses occupied ports, and writes no application fixtures
outside its disposable memory store. No deployment is performed.
