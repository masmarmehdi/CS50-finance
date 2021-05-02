import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")
# db.execute("DROP TABLE purchases")
# db.execute("CREATE TABLE purchases(Symbol TEXT NOT NULL, Name TEXT, Shares INT, Price INT , TOTAL NUMERIC NOT NULL)")
# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT symbol, sum(shares) as total_shares
        FROM purchases
        WHERE user_id= :user_id
        group by symbol
        having total_shares > 0
    """,user_id=session["user_id"])
    holding = []

    budget = 0
    for row in rows:
        stock = lookup(row["symbol"])
        holding.append({
            "symbol":stock["symbol"],
            "name":stock["name"],
            "shares":row["total_shares"],
            "price":usd(stock["price"]),
            "total":usd(stock["price"] * row["total_shares"])
        })
        budget += stock["price"] * row["total_shares"]

    user_rows = db.execute("SELECT cash FROM users WHERE id=:user_id",user_id=session["user_id"])
    cash=user_rows[0]["cash"]
    budget += cash
    return render_template("index.html",holding=holding,cash=usd(cash),budget=usd(budget))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))   
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Missing symbol")
        if quote is None:
            return apology("Invalid symbol")
        shares = request.form.get("shares")
        row = db.execute("SELECT cash FROM users WHERE id=:id",id=session["user_id"])
        budget = row[0]["cash"]
        price = quote['price']
        total = int(shares) *  price
        currentTotal =  budget - total
        if currentTotal < 0:
            return apology("Can't afford it.")
        db.execute("UPDATE users SET cash=:currentTotal WHERE id=:id",currentTotal=currentTotal,id=session["user_id"])
        db.execute("INSERT INTO purchases(user_id,symbol,shares,price) VALUES(:user_id, :symbol, :shares, :price)",user_id=session["user_id"],symbol=symbol,shares=shares,price=price)
        flash("Bought successfully!")
        return redirect("/")
    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("""
        SELECT * FROM purchases
        WHERE user_id= :user_id
    """,user_id=session["user_id"])
    holding = []
    for row in rows:
        stock = lookup(row["symbol"])
        holding.append({
            "symbol":stock["symbol"],
            "shares":row["shares"],
            "price":usd(stock["price"]),
            "time" : row["time"]
        })
    return render_template("history.html",holding=holding)


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
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if not request.form.get("symbol") or request.form.get("symbol") not in quote['symbol']:
            return apology("must provide a symbol",400)
        return render_template("displayquote.html", name=quote['name'],symbol=quote['symbol'], price=quote['price'])
    return render_template("quote.html")
    # return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)

    if request.method == "POST":
        check_username = db.execute("SELECT username FROM users")
        # print(check_username)
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        if request.form.get("username"):
            for i in range(len(check_username)):
                if request.form.get("username") == check_username[i]['username']:
                    return apology("user already exist",400)
        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)
        if not request.form.get("confirmation"):
            return apology("must provide confirm password", 400)
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must be identical",400)
        # inserting the data into the database
        rows = db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))
        # Redirect user to home page
        return redirect("/")
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not symbol:
            return apology("Missing symbol")
        if quote is None:
            return apology("Invalid symbol")
        price = quote['price']
        shares = request.form.get("shares")
        rows = db.execute("SELECT symbol, SUM(shares) AS total_shares FROM purchases WHERE user_id= :user_id GROUP BY symbol HAVING total_shares > 0;", user_id=session['user_id'])
        for row in rows:
            if row['symbol'] == symbol:
                if int(shares) > row['total_shares']:
                    return apology("Not enough shares")
        rows = db.execute("SELECT cash FROM users WHERE id=:id",id=session["user_id"])
        budget = rows[0]["cash"]
        total = int(shares) *  price
        currentTotal =  budget + total
        db.execute("UPDATE users SET cash=:currentTotal WHERE id=:id",currentTotal=currentTotal,id=session["user_id"])
        db.execute("INSERT INTO purchases(user_id,symbol,shares,price) VALUES(:user_id, :symbol, :shares, :price)",user_id=session["user_id"],symbol=symbol,shares= -1*int(shares),price=price)
        flash("sold successfully!")
        return redirect("/")
    rows = db.execute("""
            SELECT symbol FROM purchases
            WHERE user_id= :user_id
            group by symbol
            having sum(shares) > 0;
        """,user_id=session["user_id"])
    return render_template("sell.html",symbols=[row['symbol'] for row in rows])


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
