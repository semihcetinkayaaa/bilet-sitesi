import os
from contextlib import closing

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "degistir-beni")
DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    with closing(get_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(42)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    event_date TIMESTAMP NOT NULL,
                    price NUMERIC(10,2) NOT NULL,
                    capacity INTEGER NOT NULL,
                    sold INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id SERIAL PRIMARY KEY,
                    event_id INTEGER NOT NULL REFERENCES events(id),
                    buyer_name TEXT NOT NULL,
                    buyer_email TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("SELECT COUNT(*) AS c FROM events")
            if cur.fetchone()["c"] == 0:
                cur.execute("""
                    INSERT INTO events (name, venue, event_date, price, capacity) VALUES
                    ('Rock Gecesi', 'Kadıköy Sahne', NOW() + INTERVAL '10 days', 350, 100),
                    ('Caz Akşamı', 'Beyoğlu Salon', NOW() + INTERVAL '20 days', 500, 60),
                    ('Stand-up Show', 'Beşiktaş Tiyatro', NOW() + INTERVAL '30 days', 250, 80)
                """)


BASE = """
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bilet Sitesi</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  a { color: #0a58ca; text-decoration: none; }
  .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .msg { background: #e7f5e7; border: 1px solid #b6deb6; padding: .6rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
  .err { background: #fdeaea; border-color: #e5b4b4; }
  input { padding: .5rem; margin: .25rem 0 .75rem; width: 100%; box-sizing: border-box; }
  button { padding: .6rem 1.2rem; background: #0a58ca; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; }
  td, th { text-align: left; padding: .4rem; border-bottom: 1px solid #eee; }
  .muted { color: #777; }
</style>
</head>
<body>
<h1><a href="{{ url_for('index') }}">🎟️ Bilet Sitesi</a></h1>
<p><a href="{{ url_for('index') }}">Etkinlikler</a> · <a href="{{ url_for('tickets') }}">Satılan biletler</a></p>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for cat, m in messages %}<div class="msg {{ 'err' if cat == 'error' }}">{{ m }}</div>{% endfor %}
{% endwith %}
{% block body %}{% endblock %}
</body>
</html>
"""

INDEX = BASE.replace("{% block body %}{% endblock %}", """
{% for e in events %}
<div class="card">
  <h3>{{ e.name }}</h3>
  <p class="muted">{{ e.venue }} · {{ e.event_date.strftime('%d.%m.%Y %H:%M') }}</p>
  <p><strong>{{ e.price }} ₺</strong> · Kalan: {{ e.capacity - e.sold }} / {{ e.capacity }}</p>
  {% if e.capacity - e.sold > 0 %}
    <a href="{{ url_for('buy', event_id=e.id) }}">Bilet al →</a>
  {% else %}
    <span class="muted">Tükendi</span>
  {% endif %}
</div>
{% endfor %}
""")

BUY = BASE.replace("{% block body %}{% endblock %}", """
<div class="card">
  <h3>{{ e.name }}</h3>
  <p class="muted">{{ e.venue }} · {{ e.event_date.strftime('%d.%m.%Y %H:%M') }} · {{ e.price }} ₺ / bilet</p>
  <p>Kalan bilet: {{ e.capacity - e.sold }}</p>
  <form method="post">
    <label>Ad Soyad</label>
    <input name="name" required>
    <label>E-posta</label>
    <input name="email" type="email" required>
    <label>Adet</label>
    <input name="quantity" type="number" min="1" max="{{ e.capacity - e.sold }}" value="1" required>
    <button type="submit">Satın al</button>
  </form>
</div>
""")

TICKETS = BASE.replace("{% block body %}{% endblock %}", """
<h2>Satılan biletler</h2>
<table>
  <tr><th>#</th><th>Etkinlik</th><th>Alıcı</th><th>Adet</th><th>Tarih</th></tr>
  {% for t in tickets %}
  <tr>
    <td>{{ t.id }}</td><td>{{ t.name }}</td>
    <td>{{ t.buyer_name }}<br><span class="muted">{{ t.buyer_email }}</span></td>
    <td>{{ t.quantity }}</td><td>{{ t.created_at.strftime('%d.%m.%Y %H:%M') }}</td>
  </tr>
  {% else %}
  <tr><td colspan="5" class="muted">Henüz bilet satılmadı.</td></tr>
  {% endfor %}
</table>
""")


@app.route("/")
def index():
    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM events ORDER BY event_date")
        events = cur.fetchall()
    return render_template_string(INDEX, events=events)


@app.route("/buy/<int:event_id>", methods=["GET", "POST"])
def buy(event_id):
    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        e = cur.fetchone()
    if not e:
        flash("Etkinlik bulunamadı.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        qty = int(request.form["quantity"])
        if qty < 1:
            flash("Geçersiz adet.", "error")
            return redirect(url_for("buy", event_id=event_id))

        with closing(get_conn()) as conn, conn:
            with conn.cursor() as cur:
                # Kapasite kontrolü ve satış aynı işlemde yapılır (çifte satışı önler)
                cur.execute(
                    "UPDATE events SET sold = sold + %s "
                    "WHERE id = %s AND sold + %s <= capacity RETURNING id",
                    (qty, event_id, qty),
                )
                if cur.fetchone() is None:
                    flash("Yeterli bilet kalmadı.", "error")
                    return redirect(url_for("index"))
                cur.execute(
                    "INSERT INTO tickets (event_id, buyer_name, buyer_email, quantity) "
                    "VALUES (%s, %s, %s, %s)",
                    (event_id, name, email, qty),
                )
        flash(f"{qty} adet bilet alındı. Teşekkürler {name}!")
        return redirect(url_for("index"))

    return render_template_string(BUY, e=e)


@app.route("/tickets")
def tickets():
    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT t.*, e.name FROM tickets t
            JOIN events e ON e.id = t.event_id
            ORDER BY t.created_at DESC
        """)
        rows = cur.fetchall()
    return render_template_string(TICKETS, tickets=rows)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
