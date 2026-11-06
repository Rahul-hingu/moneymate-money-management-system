from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date
import os

# -----------------------------------
# 1. FLASK APPLICATION CONFIGURATION
# -----------------------------------

app = Flask(__name__)

app.secret_key = "moneymate_secret_key_change_later"

DATABASE = "database.db"


# -----------------------------------
# 2. DATABASE CONNECTION
# -----------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------------
# 3. CREATE DATABASE TABLES
# -----------------------------------

def create_tables():

    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Savings goals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            goal_name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            saved_amount REAL DEFAULT 0,
            deadline TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Budget table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            month TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, category, month)
        )
    """)

    conn.commit()
    conn.close()


# -----------------------------------
# 4. LOGIN REQUIRED DECORATOR
# -----------------------------------

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login first!", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


# -----------------------------------
# 5. HOME PAGE
# -----------------------------------

@app.route("/")
def index():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# -----------------------------------
# 6. USER REGISTRATION
# -----------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters!", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
            """, (name, email, hashed_password))

            conn.commit()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            flash("Email already registered!", "danger")

        finally:
            conn.close()

    return render_template("register.html")


# -----------------------------------
# 7. USER LOGIN
# -----------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute("""
            SELECT * FROM users WHERE email = ?
        """, (email,)).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            flash("Welcome to MoneyMate!", "success")

            return redirect(url_for("dashboard"))

        flash("Invalid email or password!", "danger")

    return render_template("login.html")


# -----------------------------------
# 8. USER LOGOUT
# -----------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have logged out successfully.", "success")

    return redirect(url_for("login"))


# -----------------------------------
# 9. DASHBOARD
# -----------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    user_id = session["user_id"]

    conn = get_db()

    # Calculate total income
    income = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ? AND type = 'income'
    """, (user_id,)).fetchone()[0]

    # Calculate total expenses
    expenses = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
    """, (user_id,)).fetchone()[0]

    # Calculate balance
    balance = income - expenses

    # Get recent transactions
    transactions = conn.execute("""
        SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY transaction_date DESC, id DESC
        LIMIT 5
    """, (user_id,)).fetchall()

    # Get savings goals
    savings = conn.execute("""
        SELECT * FROM savings_goals
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        income=income,
        expenses=expenses,
        balance=balance,
        transactions=transactions,
        savings=savings
    )


# -----------------------------------
# 10. ADD AND VIEW TRANSACTIONS
# -----------------------------------

@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():

    user_id = session["user_id"]

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        amount = request.form.get("amount", "")
        category = request.form.get("category", "").strip()
        transaction_type = request.form.get("type", "")
        transaction_date = request.form.get(
            "transaction_date", str(date.today())
        )

        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0

        if (
            not title or not category
            or amount <= 0
            or transaction_type not in ["income", "expense"]
        ):
            flash("Please enter valid transaction details!", "danger")
            return redirect(url_for("transactions"))

        conn = get_db()

        conn.execute("""
            INSERT INTO transactions
            (user_id, title, amount, category, type, transaction_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            title,
            amount,
            category,
            transaction_type,
            transaction_date
        ))

        conn.commit()
        conn.close()

        flash("Transaction added successfully!", "success")

        return redirect(url_for("transactions"))

    conn = get_db()

    all_transactions = conn.execute("""
        SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY transaction_date DESC, id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "transactions.html",
        transactions=all_transactions
    )


# -----------------------------------
# 11. DELETE TRANSACTION
# -----------------------------------

@app.route("/delete_transaction/<int:id>", methods=["POST"])
@login_required
def delete_transaction(id):

    conn = get_db()

    conn.execute("""
        DELETE FROM transactions
        WHERE id = ? AND user_id = ?
    """, (id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Transaction deleted successfully!", "success")

    return redirect(url_for("transactions"))


# -----------------------------------
# 12. SAVINGS GOALS
# -----------------------------------

@app.route("/savings", methods=["GET", "POST"])
@login_required
def savings():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        goal_name = request.form.get("goal_name", "").strip()
        target_amount = request.form.get("target_amount", "")
        deadline = request.form.get("deadline", "")

        try:
            target_amount = float(target_amount)
        except (ValueError, TypeError):
            target_amount = 0

        if not goal_name or target_amount <= 0:
            flash("Enter a valid savings goal!", "danger")
        else:

            conn.execute("""
                INSERT INTO savings_goals
                (user_id, goal_name, target_amount, deadline)
                VALUES (?, ?, ?, ?)
            """, (user_id, goal_name, target_amount, deadline))

            conn.commit()

            flash("Savings goal created!", "success")

        conn.close()

        return redirect(url_for("savings"))

    all_savings = conn.execute("""
        SELECT * FROM savings_goals
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template("savings.html", savings=all_savings)


# -----------------------------------
# 13. UPDATE SAVINGS PROGRESS
# -----------------------------------

@app.route("/update_savings/<int:id>", methods=["POST"])
@login_required
def update_savings(id):

    saved_amount = request.form.get("saved_amount", "")

    try:
        saved_amount = float(saved_amount)
    except (ValueError, TypeError):
        saved_amount = -1

    if saved_amount < 0:
        flash("Enter a valid savings amount!", "danger")
        return redirect(url_for("savings"))

    conn = get_db()

    goal = conn.execute("""
        SELECT * FROM savings_goals
        WHERE id = ? AND user_id = ?
    """, (id, session["user_id"])).fetchone()

    if goal and saved_amount <= goal["target_amount"]:

        conn.execute("""
            UPDATE savings_goals
            SET saved_amount = ?
            WHERE id = ? AND user_id = ?
        """, (saved_amount, id, session["user_id"]))

        conn.commit()

        flash("Savings progress updated!", "success")

    elif goal:
        flash("Saved amount cannot exceed the target!", "danger")
    else:
        flash("Savings goal not found!", "danger")

    conn.close()

    return redirect(url_for("savings"))


# -----------------------------------
# 14. DELETE SAVINGS GOAL
# -----------------------------------

@app.route("/delete_savings/<int:id>", methods=["POST"])
@login_required
def delete_savings(id):

    conn = get_db()

    conn.execute("""
        DELETE FROM savings_goals
        WHERE id = ? AND user_id = ?
    """, (id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Savings goal deleted!", "success")

    return redirect(url_for("savings"))


# -----------------------------------
# 15. BUDGET MANAGEMENT
# -----------------------------------

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():

    user_id = session["user_id"]
    current_month = date.today().strftime("%Y-%m")

    conn = get_db()

    if request.method == "POST":

        category = request.form.get("category", "").strip()
        amount = request.form.get("amount", "")

        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0

        if not category or amount <= 0:
            flash("Enter a valid budget!", "danger")
        else:

            conn.execute("""
                INSERT INTO budgets (user_id, category, amount, month)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, category, month)
                DO UPDATE SET amount = excluded.amount
            """, (user_id, category, amount, current_month))

            conn.commit()

            flash("Budget saved successfully!", "success")

        conn.close()

        return redirect(url_for("budget"))

    budgets = conn.execute("""
        SELECT
            b.*,
            COALESCE((
                SELECT SUM(t.amount)
                FROM transactions t
                WHERE t.user_id = b.user_id
                AND t.category = b.category
                AND t.type = 'expense'
                AND substr(t.transaction_date, 1, 7) = b.month
            ), 0) AS spent
        FROM budgets b
        WHERE b.user_id = ? AND b.month = ?
    """, (user_id, current_month)).fetchall()

    conn.close()

    return render_template("budget.html", budgets=budgets)


# -----------------------------------
# 16. FINANCIAL REPORTS
# -----------------------------------

@app.route("/reports")
@login_required
def reports():

    user_id = session["user_id"]

    conn = get_db()

    monthly_data = conn.execute("""
        SELECT
            substr(transaction_date, 1, 7) AS month,
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expenses
        FROM transactions
        WHERE user_id = ?
        GROUP BY substr(transaction_date, 1, 7)
        ORDER BY month ASC
    """, (user_id,)).fetchall()

    category_data = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        monthly_data=monthly_data,
        category_data=category_data
    )


if __name__ == "__main__":

    create_tables()

    app.run(debug=True)