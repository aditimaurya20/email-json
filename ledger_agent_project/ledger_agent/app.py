import os, json, re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from flask import Flask, request, jsonify

app = Flask(__name__)
IST = ZoneInfo('Asia/Kolkata')
RATES = {'USD': 1.0, 'EUR': 1.11, 'INR': 0.01112}
DATA_FILE = os.path.join(os.path.dirname(__file__), 'orders.jsonl')


def parse_dt(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=IST)


def load_orders():
    latest = {}
    with open(DATA_FILE, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row.get('id', ''))
            if key not in latest or parse_dt(row.get('updated_at', '')) > parse_dt(latest[key].get('updated_at', '')):
                latest[key] = row
    return list(latest.values())

ORDERS = load_orders()


def business_date(row):
    return parse_dt(row.get('created_at', '')).astimezone(IST).date()


def usd(row):
    return float(row.get('amount') or 0) * RATES.get(str(row.get('currency', 'USD')).upper(), 1.0)

PRODUCTS = ['Air Fryer', 'Rice Cooker', 'Kettle', 'Mixer', 'Grinder', 'Juicer', 'Toaster', 'Blender']
REGIONS = ['Central', 'North', 'South', 'East', 'West']


def find_filter(q, rows):
    ql = q.lower()
    out = rows
    for product in PRODUCTS:
        if product.lower() in ql:
            out = [r for r in out if r.get('product', '').lower() == product.lower()]
            break
    for region in REGIONS:
        if re.search(r'\b' + re.escape(region.lower()) + r'\b', ql):
            out = [r for r in out if r.get('region', '').lower() == region.lower()]
            break
    cm = re.search(r'\b(c\d{4})\b', ql, re.I)
    if cm:
        cid = cm.group(1).upper()
        out = [r for r in out if str(r.get('customer', '')).upper() == cid]
    om = re.search(r'\b(ord-\d+)\b', ql, re.I)
    if om:
        oid = om.group(1).upper()
        out = [r for r in out if str(r.get('id', '')).upper() == oid]
    if any(x in ql for x in ['refund', 'refunded', 'refunds']):
        out = [r for r in out if r.get('status') == 'refunded']
    elif any(x in ql for x in ['void', 'cancelled', 'canceled']):
        out = [r for r in out if r.get('status') == 'void']
    elif any(x in ql for x in ['paid order', 'paid orders', 'revenue', 'sales', 'sold', 'earning', 'earned', 'top-selling', 'top selling']) or 'how much' in ql:
        out = [r for r in out if r.get('status') == 'paid']
    # Year / month / explicit date range
    year_match = re.search(r'\b(202[0-9])\b', ql)
    month_names = {'january':1,'jan':1,'february':2,'feb':2,'march':3,'mar':3,'april':4,'apr':4,'may':5,'june':6,'jun':6,'july':7,'jul':7,'august':8,'aug':8,'september':9,'sep':9,'sept':9,'october':10,'oct':10,'november':11,'nov':11,'december':12,'dec':12}
    found_month = None
    for name, num in month_names.items():
        if re.search(r'\b'+name+r'\b', ql):
            found_month = num; break
    if year_match and found_month:
        y = int(year_match.group(1))
        out = [r for r in out if business_date(r).year == y and business_date(r).month == found_month]
    elif found_month:
        out = [r for r in out if business_date(r).month == found_month]
    elif year_match:
        y = int(year_match.group(1))
        out = [r for r in out if business_date(r).year == y]
    # ISO date or common numeric dates
    dates = re.findall(r'\b(202\d-\d{2}-\d{2})\b', ql)
    if dates:
        ds = [date.fromisoformat(x) for x in dates]
        if len(ds) >= 2:
            out = [r for r in out if ds[0] <= business_date(r) <= ds[1]]
        else:
            out = [r for r in out if business_date(r) == ds[0]]
    return out


def money(value):
    return f"${value:,.2f} USD"


def answer_question(question):
    q = str(question or '').strip()
    if not q:
        return 'Please provide a question about the order ledger.'
    ql = q.lower()
    rows = find_filter(q, ORDERS)
    # Non-revenue metrics for refunded/void filters are status-specific. Otherwise revenue is paid-only.
    if any(w in ql for w in ['refund', 'refunded', 'refunds']):
        total = sum(usd(r) for r in rows)
        if any(w in ql for w in ['how many', 'count', 'number of', 'quantity of orders']):
            return f"There are {len(rows)} refunded orders matching the question."
        return f"Total value of refunded orders matching the question is {money(total)} (converted to USD)."
    if any(w in ql for w in ['void', 'cancelled', 'canceled']):
        if any(w in ql for w in ['how many', 'count', 'number of']):
            return f"There are {len(rows)} void orders matching the question."
        return f"The total value of void orders matching the question is {money(sum(usd(r) for r in rows))}."
    # Top / highest / best by product, customer, or region
    if any(w in ql for w in ['top', 'highest', 'most', 'best', 'largest']) and any(w in ql for w in ['product', 'item', 'customer', 'region', 'sales', 'revenue', 'sold']) and not any(p.lower() in ql for p in PRODUCTS):
        group_key = 'product' if any(w in ql for w in ['product', 'item', 'sold']) else ('customer' if 'customer' in ql or 'client' in ql else 'region')
        metric = 'qty' if any(w in ql for w in ['units', 'quantity', 'items sold', 'most sold']) else 'revenue'
        groups = defaultdict(float)
        for r in rows:
            if r.get('status') == 'paid':
                groups[r.get(group_key, 'Unknown')] += float(r.get('qty') or 0) if metric == 'qty' else usd(r)
        if not groups:
            return 'No matching paid orders were found.'
        name, val = max(groups.items(), key=lambda kv: kv[1])
        amount = f'{val:,.0f} units' if metric == 'qty' else money(val)
        return f"The {group_key} with the highest {('units sold' if metric == 'qty' else 'revenue')} is {name}, at {amount}."
    # Counts and quantities
    if any(w in ql for w in ['units', 'quantity', 'items sold', 'how many items']) and not any(w in ql for w in ['how much', 'revenue', 'sales amount']):
        paid = [r for r in rows if r.get('status') == 'paid']
        return f"Total units in matching paid orders: {sum(int(r.get('qty') or 0) for r in paid):,}."
    if any(w in ql for w in ['how many', 'count', 'number of', 'total orders', 'order count']):
        if 'paid' in ql or 'revenue' in ql or 'sales' in ql:
            rows = [r for r in rows if r.get('status') == 'paid']
            return f"There are {len(rows)} paid orders matching the question."
        return f"There are {len(rows)} orders matching the question."
    # List/detail for a specific order/customer
    if re.search(r'\bord-\d+\b', ql):
        if not rows: return 'No matching order was found.'
        r = rows[0]
        return f"Order {r['id']}: customer {r['customer']}, region {r['region']}, product {r['product']}, quantity {r['qty']}, status {r['status']}, order value {money(usd(r))}, created {business_date(r).isoformat()} (Asia/Kolkata)."
    # Revenue is default for financial questions; only paid rows count.
    paid = [r for r in rows if r.get('status') == 'paid']
    total = sum(usd(r) for r in paid)
    if any(w in ql for w in ['average', 'avg', 'mean']) and ('order' in ql or 'sale' in ql or 'revenue' in ql or 'amount' in ql):
        avg = total / len(paid) if paid else 0
        return f"Average value per paid order matching the question is {money(avg)} across {len(paid)} paid orders."
    if any(w in ql for w in ['which', 'what', 'name']) and any(w in ql for w in ['product', 'customer', 'region']) and any(w in ql for w in ['revenue', 'sales', 'sold', 'highest', 'most']) and not any(p.lower() in ql for p in PRODUCTS):
        key = 'product' if 'product' in ql else ('customer' if 'customer' in ql else 'region')
        groups = defaultdict(float)
        for r in paid: groups[r[key]] += usd(r)
        if groups:
            name, val = max(groups.items(), key=lambda kv: kv[1])
            return f"{name} has the highest revenue at {money(val)}."
    
        return f"Total revenue is {money(total)} from {len(paid)} matching paid orders."


@app.get('/')
def health():
    return jsonify({'service':'The Ledger Agent','status':'ok','orders_loaded':len(ORDERS),'usage':'POST JSON {"question":"..."} to this URL.'})

@app.post('/')
def ask():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or 'question' not in payload:
        return jsonify({'error':'Send a JSON object containing a question string.'}), 400
    try:
        return jsonify({'answer': answer_question(payload.get('question'))})
    except Exception:
        app.logger.exception('Question processing failed')
        return jsonify({'answer':'I could not process that question. Please try asking about revenue, refunds, orders, products, customers, regions, or dates.'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    app.run(host='0.0.0.0', port=port)
