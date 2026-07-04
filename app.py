from flask import Flask, render_template, request
from flask import redirect, session, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "b6k9p@2#QvL8!nR7"

# ---------------------------
# DATABASE CONNECTION
# ---------------------------
def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------
# CREATE TABLE
# ---------------------------
def create_table():
    conn = get_db()

    # 1. Users Table (Original)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    
    # 2. Groups Table (New - Force Create)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_by TEXT,
            FOREIGN KEY(created_by) REFERENCES users(username)
        )
    ''')

    # 3. Members Table (New - Force Create)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            username TEXT,
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')

    # 4. Expenses Table (New - Force Create)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            description TEXT,
            amount REAL,
            paid_by TEXT,
            date TEXT,
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')
    
    conn.commit()
    conn.close()

create_table()

# ---------------------------
# REGISTER
# ---------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            conn = get_db()
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                         (username, password))
            conn.commit()
            conn.close()
            return redirect("/login")
        except:
            return "Username already exists!"

    return render_template("register.html")

# ---------------------------
# LOGIN
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["user"] = username
            return redirect("/home")
        else:
            return "Invalid Credentials!"

    return render_template("login.html")

# ---------------------------
 #HOME PAGE  budget splitter routes
 #---------------------------
@app.route("/home")
def home():
    if "user" in session:
        conn = get_db()
        # Fetch groups created by the user
        groups = conn.execute(
            "SELECT * FROM groups WHERE created_by = ?", (session["user"],)
        ).fetchall()
        conn.close()
        return render_template("home.html", user=session["user"], groups=groups)
    return redirect("/login")

@app.route("/create_group", methods=["POST"])
def create_group():
    if "user" in session:
        group_name = request.form["group_name"]
        members = [m.strip() for m in request.form["members"].split(",") if m.strip()]# Comma separated usernames
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Insert Group
        cursor.execute("INSERT INTO groups (name, created_by) VALUES (?, ?)", 
                       (group_name, session["user"]))
        group_id = cursor.lastrowid
        
        # Insert Members (add creator automatically if not listed)
        if session["user"] not in members:
            members.append(session["user"])
            
        for member in members:
            member = member.strip()
            if member:
                cursor.execute("INSERT INTO members (group_id, username) VALUES (?, ?)", 
                               (group_id, member))
        
        conn.commit()
        conn.close()
        return redirect("/home")
    return redirect("/login")

@app.route("/group/<int:group_id>")
def view_group(group_id):
    if "user" in session:
        conn = get_db()
        
        # Get Group Info
        group = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        
        # Get Members
        members = conn.execute("SELECT username FROM members WHERE group_id = ?", (group_id,)).fetchall()
        member_list = [m['username'] for m in members]
        
        # Get Expenses
        expenses = conn.execute(
            "SELECT * FROM expenses WHERE group_id = ? ORDER BY date DESC", (group_id,)
        ).fetchall()
        
        # CALCULATION LOGIC
        total_spent = 0
        balances = {m: 0.0 for m in member_list} # Dictionary to track who paid/owes
        
        for exp in expenses:
            total_spent += exp['amount']
            # Person who paid adds to their balance
            payer = exp['paid_by']
            if payer in balances:
                balances[payer] += exp['amount']
        
        # Calculate the fair share
        if len(member_list) > 0:
            share_per_person = total_spent / len(member_list)
        else:
            share_per_person = 0
            
        # Final balance: Positive means they are owed money, Negative means they owe
        for m in balances:
            balances[m] -= share_per_person
        conn.close()
        # ---------------- SETTLEMENT LOGIC ----------------
        debtors = []
        creditors = []

    for person, amount in balances.items():
        if amount < 0:
            debtors.append([person, abs(amount)])
        elif amount > 0:
            creditors.append([person, amount])

    settlements = []

    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor, debt_amount = debtors[i]
        creditor, credit_amount = creditors[j]

        pay_amount = min(debt_amount, credit_amount)

        settlements.append((debtor, creditor, round(pay_amount, 2)))

        debtors[i][1] -= pay_amount
        creditors[j][1] -= pay_amount

        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1

# ---------

    return render_template(
        "group_detail.html",
        group=group,
        expenses=expenses,
        members=member_list,
        balances=balances,
        settlements=settlements,
        total=total_spent
    )
    return redirect("/login")

@app.route("/add_expense/<int:group_id>", methods=["POST"])
def add_expense(group_id):
    if "user" in session:
        desc = request.form["description"]
        try:
            amount = float(request.form["amount"])
        except ValueError:
            return "Invalid amount entered!"
        paid_by = request.form["paid_by"]
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        conn = get_db()
        conn.execute(
            "INSERT INTO expenses (group_id, description, amount, paid_by, date) VALUES (?, ?, ?, ?, ?)",
            (group_id, desc, amount, paid_by, date)
        )
        conn.commit()
        conn.close()
        
        return redirect(f"/group/{group_id}")
    return redirect("/login")

@app.route("/delete_expense/<int:expense_id>/<int:group_id>")
def delete_expense(expense_id, group_id):
    if "user" in session:
        conn = get_db()

        # SECURITY CHECK (important)
        member = conn.execute(
            "SELECT * FROM members WHERE group_id=? AND username=?",
            (group_id, session["user"])
        ).fetchone()

        if not member:
            return "Unauthorized!", 403

        # DELETE EXPENSE
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        conn.close()

        return redirect(f"/group/{group_id}")

    return redirect("/login")
@app.route("/delete_account")
def delete_account():
    if "user" in session:
        username = session["user"]
        conn = get_db()

        # 1. Delete expenses paid by user
        conn.execute("DELETE FROM expenses WHERE paid_by = ?", (username,))

        # 2. Get groups created by user
        groups = conn.execute(
            "SELECT id FROM groups WHERE created_by = ?", (username,)
        ).fetchall()

        for g in groups:
            group_id = g["id"]

            # delete group-related data
            conn.execute("DELETE FROM expenses WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM members WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))

        # 3. Remove user from other groups
        conn.execute("DELETE FROM members WHERE username = ?", (username,))

        # 4. Delete user account
        conn.execute("DELETE FROM users WHERE username = ?", (username,))

        conn.commit()
        conn.close()

        session.pop("user", None)

        return "Account deleted successfully!"

    return redirect("/login")

# ---------------------------
# LOGOUT
# ---------------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ---------------------------
# RUN APP
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)