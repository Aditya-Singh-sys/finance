import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Load user's portfolio
    portfolio = db.execute("SELECT * FROM portfolio_{id}".format(id=session["user_id"]))

    # Calculate cash at hand
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # Update prices and calculate stock worth
    worth = cash
    for stock in portfolio:
        price = lookup(stock['symbol'])['price']
        worth += stock['qty'] * price
        stock.update({'price': price, 'total': stock['qty'] * price})

    # Display it
    return render_template("index.html", shares=portfolio, cash=usd(cash), worth=usd(worth))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached request via POST
    if request.method == "POST":

        # If symbol is blank
        if not request.form.get("symbol"):
            return apology("Must enter symbol", 400)

        response = lookup(request.form.get("symbol"))

        # If shares is blank
        if not request.form.get("shares"):
            return apology("Must enter shares", 400)

        # Valid qty
        try:

            qty = int(request.form.get("shares"))

        except:

            return apology("Invalid no. of shares", 400)

        if qty < 1:
            return apology("Invalid no. of shares", 400)

        # If stock doesn't exist
        if not response:
            return apology("Invalid stock symbol", 400)

        amt = qty * response["price"]

        # Check if user can afford stock
        if amt > float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]):
            return apology("Can't afford :(", 400)

        # Update cash
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", amt, session["user_id"])

        # Record transaction
        db.execute("INSERT INTO transactions (userid, symbol, qty, price, date) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], response["name"], qty, response["price"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # If stock is not there, add it
        if not db.execute('SELECT * FROM portfolio_{id} WHERE symbol = "{s}"'.format(id=session["user_id"], s=response["symbol"])):
            db.execute("INSERT INTO portfolio_{id} (symbol, name, qty, price, total) VALUES (?, ?, ?, ?, ?)".format(
                id=session["user_id"]), response["symbol"], response["name"], qty, response["price"], amt)

        # If stock is already there, update quantity
        else:
            db.execute(
                "UPDATE portfolio_{id} SET qty = qty + ? WHERE symbol = ?".format(id=session["user_id"]), qty, response["symbol"])

        # Return to homepage
        return redirect("/")

    # User reached request via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Load transactions
    transactions = db.execute("SELECT * FROM transactions WHERE userid = ?", session["user_id"])

    # Show page
    return render_template("history.html", shares=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # For POST request
    if request.method == "POST":

        # Check for blank symbol
        if not request.form.get("symbol"):
            return apology("Please enter symbol", 400)

        # Store stock details
        response = lookup(request.form.get("symbol"))

        # Check if stock exists
        if not response:
            return apology("Invalid symbol", 400)

        # Show quoted page with symbol
        return render_template("quoted.html", stock=response)

    # For GET request
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # POST
    if request.method == "POST":

        # Check if username is blank
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Check if username is already exists
        if db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username")):
            return apology("username already exists", 400)

        # Check if password is blank
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Check if confirmation is blank
        if not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        # Check if password and confirmation do not match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        # Insert new user to database
        id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                        request.form.get("username"), generate_password_hash(request.form.get("password")))

        # Create user's portfolio
        db.execute(
            "CREATE TABLE portfolio_{id} (symbol TEXT NOT NULL, name TEXT NOT NULL, qty INTEGER NOT NULL, price NUMERIC NOT NULL, total NUMERIC NOT NULL)".format(id=id))

        # Set session to current user
        session["user_id"] = id

        # Redirect user to homepage
        return redirect("/")

    # Get request
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Load user's portfolio
    portfolio = db.execute("SELECT * FROM portfolio_{id}".format(id=session["user_id"]))

    # For POST
    if request.method == "POST":

        # If no stock is selected
        if not request.form.get("symbol"):
            return apology("Must enter stock", 400)

        # Load stock details
        response = lookup(request.form.get("symbol"))

        # Check for invalid stock symbol
        if not response:
            return apology("Must enter valid stock", 400)

        # If shares not entered
        if not request.form.get("shares"):
            return apology("Must enter shares", 400)

        # If invalid input for shares
        try:
            qty = int(request.form.get("shares"))
        except:
            return apology("Must enter valid shares", 400)

        # If less than 1 input for shares
        if qty < 1:
            return apology("Must enter valid shares", 400)

        # Load available number of shares of stock
        available = db.execute("SELECT qty FROM portfolio_{id} WHERE symbol = ?".format(
            id=session["user_id"]), response["symbol"])[0]["qty"]

        # Check for availability of shares
        if qty > available:
            return apology("You don't have enough shares!", 400)

        # Record transaction
        amt = qty * response["price"]
        db.execute("INSERT INTO transactions (userid, symbol, qty, price, date) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], response["name"], -qty, response["price"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Update portfolio
        if qty == available:
            db.execute("DELETE FROM portfolio_{id} WHERE symbol = ?".format(id=session["user_id"]), response["symbol"])

        else:
            db.execute(
                "UPDATE portfolio_{id} SET qty = qty - ? WHERE symbol = ?".format(id=session["user_id"]), qty, response["symbol"])

        # Update cash
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amt, session["user_id"])

        # Redirect to homepage
        return redirect("/")

    # If GET
    return render_template("sell.html", stocks=portfolio)


@app.route("/changepw", methods=["GET", "POST"])
@login_required
def changepw():
    """Manage account"""

    # POST
    if request.method == "POST":

        # Check if username is blank
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Check if password is blank
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Check if confirmation is blank
        if not request.form.get("newpw"):
            return apology("must provide new password", 400)

        # Check if password and confirmation match
        if request.form.get("password") == request.form.get("newpw"):
            return apology("passwords must not match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Ensure user has entered his/her name only
        if rows[0]['id'] != session["user_id"]:
            return apology("Wrong username!", 400)

        # Update password
        db.execute("UPDATE users SET hash = ?", generate_password_hash(request.form.get("newpw")))

        # Clear session
        session.clear()

        # Redirect user to homepage
        return redirect("/")

    # Get request
    else:
        return render_template("changepw.html")


@app.route("/deleteacc", methods=["GET", "POST"])
@login_required
def deleteacc():
    """Manage account"""

    # POST
    if request.method == "POST":

        # Check if username is blank
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Check if password is blank
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Check if confirmation is blank
        if not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        # Check if password and confirmation do not match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure user has entered his/her name only
        if rows[0]['id'] != session["user_id"]:
            return apology("Wrong username!", 400)

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Delete user's porfolio
        db.execute("DROP TABLE portfolio_{id}".format(id=session["user_id"]))

        # Delete user from table
        db.execute("DELETE FROM users WHERE id = ?", session["user_id"])

        # Clear session
        session.clear()

        # Redirect user to homepage
        return redirect("/")

    # Get request
    else:
        return render_template("deleteacc.html")

