# The Ledger Agent

A small Flask HTTPS-ready service for the Acme Appliances order ledger assignment. It reads the supplied export (`orders.jsonl`) and responds to POST requests with JSON.

## Local test

1. Install Python 3.10 or newer.
2. In this folder, run `pip install -r requirements.txt`.
3. Run `python app.py`.
4. Test with:

```bash
curl -X POST http://127.0.0.1:8000/ \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the total revenue in West?"}'
```

The response shape is `{"answer":"..."}`. A GET request to `/` is a health check.

## Deploy on Render

1. Create a GitHub repository and upload all four files: `app.py`, `orders.jsonl`, `requirements.txt`, and `Procfile` (the `render.yaml` file is optional).
2. In Render, choose **New + → Web Service**, connect the repository, and select Python.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Deploy. Render provides a public HTTPS URL. Use that URL for the assignment's endpoint.
6. Test by sending a POST request to the URL root with JSON body `{"question":"What is total revenue?"}`.

## Ledger rules implemented

- Latest `updated_at` row wins for duplicate order IDs.
- Business dates are interpreted in Asia/Kolkata.
- Only `paid` rows count toward revenue.
- Currency conversion uses USD=1, EUR=1.11, INR=0.01112.
- Refunded order value is reported separately and is not counted as paid revenue.

## Important limitation

This starter implementation uses lightweight question parsing, not a general-purpose language model. It supports common questions about revenue, refunds, order counts, quantities, products, customers, regions, dates/months, and order IDs. Test it with likely quiz questions and extend `answer_question()` if your evaluator asks for a metric not yet covered. The assignment's unseen-question requirement may need broader interpretation than simple pattern matching.
