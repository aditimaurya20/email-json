
import os
import json
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict
from flask import Flask, request, jsonify

app = Flask(__name__)

IST = ZoneInfo("Asia/Kolkata")

RATES = {
    "USD": 1.0,
    "EUR": 1.11,
    "INR": 0.01112
}

DATA_FILE = os.path.join(os.path.dirname(__file__), "orders.jsonl")

PRODUCTS = [
    "Air Fryer", "Rice Cooker", "Kettle", "Mixer",
    "Grinder", "Juicer", "Toaster", "Blender"
]

REGIONS = ["Central", "North", "South", "East", "West"]

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}


def parse_dt(value):
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)

        return dt

    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=IST)


def load_orders():
    latest = {}

    with open(DATA_FILE, encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            row = json.loads(line)
            order_id = str(row.get("id", ""))

            if not order_id:
                continue

            if (
                order_id not in latest
                or parse_dt(row.get("updated_at", ""))
                > parse_dt(latest[order_id].get("updated_at", ""))
            ):
                latest[order_id] = row

    return list(latest.values())


ORDERS = load_orders()


def business_date(row):
    return parse_dt(row.get("created_at", "")).astimezone(IST).date()


def usd(row):
    currency = str(row.get("currency", "USD")).upper()
    amount = float(row.get("amount") or 0)

    return amount * RATES.get(currency, 1.0)


def money(value):
    return f"${value:,.2f} USD"


def find_filter(question, rows):
    q = question.lower()
    result = list(rows)

    # Product filter
    for product in PRODUCTS:
        if product.lower() in q:
            result = [
                r for r in result
                if str(r.get("product", "")).lower() == product.lower()
            ]
            break

    # Region filter
    for region in REGIONS:
        if re.search(r"\b" + re.escape(region.lower()) + r"\b", q):
            result = [
                r for r in result
                if str(r.get("region", "")).lower() == region.lower()
            ]
            break

    # Customer ID filter
    customer_match = re.search(r"\b(c\d{4})\b", q, re.I)

    if customer_match:
        customer_id = customer_match.group(1).upper()
        result = [
            r for r in result
            if str(r.get("customer", "")).upper() == customer_id
        ]

    # Order ID filter
    order_match = re.search(r"\b(ord-\d+)\b", q, re.I)

    if order_match:
        order_id = order_match.group(1).upper()
        result = [
            r for r in result
            if str(r.get("id", "")).upper() == order_id
        ]

    # Status filter
    if any(word in q for word in ["refund", "refunded", "refunds"]):
        result = [
            r for r in result if r.get("status") == "refunded"
        ]

    elif any(word in q for word in ["void", "cancelled", "canceled"]):
        result = [
            r for r in result if r.get("status") == "void"
        ]

    elif (
        any(word in q for word in [
            "paid order", "paid orders", "paid",
            "revenue", "sales", "sold", "earning",
            "earned", "how much"
        ])
    ):
        result = [
            r for r in result if r.get("status") == "paid"
        ]

    # Year and month filters
    year_match = re.search(r"\b(20\d{2})\b", q)
    year = int(year_match.group(1)) if year_match else None

    month = None

    for name, number in MONTHS.items():
        if re.search(r"\b" + name + r"\b", q):
            month = number
            break

    if year is not None and month is not None:
        result = [
            r for r in result
            if business_date(r).year == year
            and business_date(r).month == month
        ]

    elif month is not None:
        result = [
            r for r in result
            if business_date(r).month == month
        ]

    elif year is not None:
        result = [
            r for r in result
            if business_date(r).year == year
        ]

    # Explicit ISO dates
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", q)

    if dates:
        parsed_dates = [date.fromisoformat(d) for d in dates]

        if len(parsed_dates) >= 2:
            start_date, end_date = parsed_dates[0], parsed_dates[1]

            result = [
                r for r in result
                if start_date <= business_date(r) <= end_date
            ]

        else:
            target_date = parsed_dates[0]

            result = [
                r for r in result
                if business_date(r) == target_date
            ]

    return result


def answer_question(question):
    q = str(question or "").strip()
    ql = q.lower()

    if not q:
        return "Please provide a question about the order ledger."

    rows = find_filter(q, ORDERS)

    # Count distinct customers, not orders
    if (
        "customer" in ql
        and any(word in ql for word in [
            "how many", "count", "number of",
            "different customers", "distinct customers"
        ])
    ):
        paid_rows = [
            r for r in rows if r.get("status") == "paid"
        ]

        customers = {
            str(r.get("customer"))
            for r in paid_rows
            if r.get("customer") not in (None, "")
        }

        return str(len(customers))

    # Refund questions
    if any(word in ql for word in ["refund", "refunded", "refunds"]):
        if any(word in ql for word in [
            "how many", "count", "number of", "quantity of orders"
        ]):
            return str(len(rows))

        total = sum(usd(r) for r in rows)
        return money(total)

    # Void or cancelled order questions
    if any(word in ql for word in ["void", "cancelled", "canceled"]):
        if any(word in ql for word in [
            "how many", "count", "number of"
        ]):
            return str(len(rows))

        return money(sum(usd(r) for r in rows))

    # Specific order details
    if re.search(r"\bord-\d+\b", ql):
        if not rows:
            return "No matching order was found."

        row = rows[0]

        return (
            f"Order {row.get('id')}: "
            f"customer {row.get('customer')}, "
            f"region {row.get('region')}, "
            f"product {row.get('product')}, "
            f"quantity {row.get('qty')}, "
            f"status {row.get('status')}, "
            f"value {money(usd(row))}, "
            f"created {business_date(row).isoformat()}."
        )

    # Top / highest / most / best questions
    is_ranking = any(word in ql for word in [
        "top", "highest", "most", "best", "largest"
    ])

    has_group = any(word in ql for word in [
        "product", "item", "customer", "client", "region"
    ])

    if is_ranking and has_group:
        if any(word in ql for word in ["product", "item"]):
            group_key = "product"

        elif any(word in ql for word in ["customer", "client"]):
            group_key = "customer"

        else:
            group_key = "region"

        metric = (
            "qty"
            if any(word in ql for word in [
                "units", "quantity", "items sold", "most sold"
            ])
            else "revenue"
        )

        groups = defaultdict(float)

        for row in rows:
            if row.get("status") != "paid":
                continue

            key = row.get(group_key, "Unknown")

            if metric == "qty":
                groups[key] += float(row.get("qty") or 0)
            else:
                groups[key] += usd(row)

        if not groups:
            return "No matching paid orders were found."

        name, value = max(groups.items(), key=lambda item: item[1])

        if metric == "qty":
            return str(name)

        return str(name)

    # Count distinct customers for customer-count questions was handled above.
    # Count orders
    if any(word in ql for word in [
        "how many", "count", "number of",
        "total orders", "order count"
    ]):
        if "paid" in ql or "revenue" in ql or "sales" in ql:
            paid_rows = [
                r for r in rows if r.get("status") == "paid"
            ]
            return str(len(paid_rows))

        return str(len(rows))

    # Total units sold
    if any(word in ql for word in [
        "units", "quantity", "items sold", "how many items"
    ]):
        paid_rows = [
            r for r in rows if r.get("status") == "paid"
        ]

        units = sum(
            int(r.get("qty") or 0) for r in paid_rows
        )

        return str(units)

    # Revenue and average calculations
    paid_rows = [
        r for r in rows if r.get("status") == "paid"
    ]

    total = sum(usd(r) for r in paid_rows)

    if any(word in ql for word in [
        "average", "avg", "mean"
    ]):
        if not paid_rows:
            return money(0)

        return money(total / len(paid_rows))

    # Highest-revenue product/customer/region questions
    if any(word in ql for word in [
        "which", "what", "name"
    ]) and any(word in ql for word in [
        "revenue", "sales", "earned", "highest", "most"
    ]):
        if "product" in ql or "item" in ql:
            group_key = "product"
        elif "customer" in ql or "client" in ql:
            group_key = "customer"
        elif "region" in ql:
            group_key = "region"
        else:
            group_key = None

        if group_key:
            groups = defaultdict(float)

            for row in paid_rows:
                groups[row.get(group_key, "Unknown")] += usd(row)

            if groups:
                name, value = max(
                    groups.items(), key=lambda item: item[1]
                )
                return str(name)

    # Default: total paid revenue
    return money(total)


@app.get("/")
def health():
    return jsonify({
        "service": "The Ledger Agent",
        "status": "ok",
        "orders_loaded": len(ORDERS),
        "usage": 'POST JSON {"question":"..."} to this URL.'
    })


@app.post("/")
def ask():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict) or "question" not in payload:
        return jsonify({
            "error": "Send a JSON object containing a question string."
        }), 400

    try:
        answer = answer_question(payload.get("question"))
        return jsonify({"answer": answer})

    except Exception:
        app.logger.exception("Question processing failed")

        return jsonify({
            "answer": "Unable to process the question."
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
