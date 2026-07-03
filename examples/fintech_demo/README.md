# Fintech Demo

★ KEEP THIS WORKING AT ALL TIMES ★

Simultaneously: pilot demo, onboarding tutorial, e2e test fixture, and proof that Custos actually works.

## Run it end-to-end (< 5 min)

```bash
cd examples/fintech_demo
docker-compose -f docker-compose.demo.yml up --build
python agent/loan_bot.py
python inject_drift.py
```

Watch the dashboard for the drift severity rising and decisions shifting from ALLOW to REVIEW/BLOCK.

