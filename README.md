# payday-agent-tests

Simple CLI to query Payday ERP:

```bash
# vendors
python app.py vendors

# balances as of date
python app.py balances --asof 2025-06-30

# statement (+ optional CSV)
python app.py statement --vendor-id <ID> --from 2025-01-01 --to 2025-12-31 --csv out.csv
