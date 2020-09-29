import os, urllib.parse, requests, math
from flask import Flask, render_template, request, redirect, session
import time


def apiprice(ticker):
    # load price from NY
    try:
        API_KEY = os.environ.get('myAPI_KEY_finnhub')
        response = requests.get(f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote_plus(ticker)}&token={API_KEY}")
        response.raise_for_status()

    except requests.RequestException:
        return None

    try:
        resp = response.json()
        return{
            "price": float(resp['c'])
        }

    except (KeyError, TypeError, ValueError):
        return None


def apiexchange(base):
    try:
        API_KEY = os.environ.get('myAPI_KEY_finnhub')
        response = requests.get(f"https://finnhub.io/api/v1/forex/rates?base={base}&token={API_KEY}")
        response.raise_for_status()

    except requests.RequestException:
        return None

    try:
        resp = response.json()
        return resp['quote']['USD']

    except (KeyError, TypeError, ValueError):
        return None

def error_page(message):
    return render_template("error_page.html",message=message)

def load_portfolio_info(userid,portfolio_db,cash_db,loadprice):

    if loadprice == False:
        # save tickers price
        tickers_price = {}
        for key in session.get('portfolio_ticker'):
            tickers_price[key] = {'price': key['price']}

        # save old exchange prices before clear cash info in session
        exchanges = {}
        exchanges['rub'] = {'tousd': session.get('portfolio_cash')['rub']["tousd"]}
        exchanges['rub'] = {'toeuro': session.get('portfolio_cash')['rub']["toeuro"]}
        exchanges['euro'] = {'tousd': session.get('portfolio_cash')['euro']["tousd"]}
        exchanges['usd'] = {'toeuro': session.get('portfolio_cash')['usd']["toeuro"]}

    # load ticker info: number, price, fullPrice, currency
    portfolio_ticker = load_ticker_info(userid, portfolio_db, loadprice)

    # load class info : desired fraction, active ticker, real fraction, reb. suggestion

    # load cash info: rub, euro, usd, rub in usd, rub in euro, total_euro, total_usd
    portfolio_cash = load_cash_info(userid, cash_db, loadprice)

    # calculate total
    # calculate real fraction for class
    # calculate rebalance suggestion

    # clear session
    session.pop('portfolio_ticker', None)
    session.pop('portfolio_cash', None)
    session.pop('total', None)
    # session.pop('classes', None)

    # save everything in session


    return None

def load_ticker_info(userid, ticker_db, loadprice):
    # function to fill in portfolio_ticker: number, price, full_price, currency

    # load data from db tickers
    datas = ticker_db.query.filter_by(userid=userid).all()
    print(f"Extracted from ticker_db data is {datas}")

    # check new user
    if len(datas) == 0:
        return False

    portfolio_ticker = {}
    # load from db tickers: number, currency
    for row in datas:
        portfolio_ticker[row.ticker] = {
            'number': row.number,
            'currency': row.currency
        }

    # load new prices from api request
    if loadprice == True:
        for row in datas:
            res = apiprice(row.ticker)
            # TODO: check error messages

            if res is not None:
                portfolio_ticker[row.ticker].update(
                    {
                        'price': res['price'],
                        'fullPrice': res['price'] * row.number
                    })
            else:
                portfolio_ticker[row.ticker].update(
                    {
                        'price': None,
                        'fullPrice': None
                    })
                error_page('Could not load price')

    # load old prices from session for every tck, check the existence of such tck in session
    if loadprice == False:
        old_ticker_info = session.get('portfolio')

        for row in datas:
            if row.ticker in old_ticker_info:
                portfolio_ticker[row.ticker].update(
                {
                    'price': old_ticker_info[row.ticker]['price'],
                    'fullPrice': old_ticker_info[row.ticker]['price'] * row.number
                })
            else:
                # if there is no such ticker old version of portfolio
                portfolio_ticker[row.ticker].update({
                        'price': None,
                        'fullPrice': None
                    })

    print(f"ticker info is loaded and saved in dictionary, \n {portfolio_ticker}")
    return portfolio_ticker


def load_portfolio(userid, portfolio_db,cash_db,loadprice):
    # loading portfolio information from portfolio db and cash info from cash db
    # loading ticker price using api
    # loadprice = true - loading price, else: take price from session

    # clear portfolio, cash and total info in session
    session.pop('total', None)

    if loadprice == True:
        session.pop('portfolio', None)
        session.pop('datetime', None)
        session.pop('cash', None)

    else:
        # save prices in temp dict before deleting portfolio in session
        oldprice = {}
        tmpportfolio = session.get('portfolio')

        for key in tmpportfolio:
            oldprice[key] = {'price':tmpportfolio[key]['price']}

        session.pop('portfolio', None)

        # save old exchange prices before clear cash info in session
        oldexchange = {}
        oldexchange['rub'] = session.get('cash')['rub']["tousd"]
        oldexchange['euro'] = session.get('cash')['euro']["tousd"]

        session.pop('cash', None)


    # to load portfolio data from db and combine in with results of API query
    datas = portfolio_db.query.filter_by(userid=userid).all()

    print(f"Extracted from portfolio_db data is {datas}")

    # check new user
    if len(datas) == 0:
        return False

    # if user exists in database
    portfolio = {}
    total = 0 # for whole portfolio

    for row in datas:
        portfolio[row.ticker] = {
            'number': row.number,
            'fraction': row.fraction
        }

        # load new price
        if loadprice == True:
            res = apiprice(row.ticker)
            if res is not None:
                portfolio[row.ticker].update(
                    {
                    'price': res['price'],
                    'fullPrice' : res['price'] * row.number
                    })
            else:
                error_page('Could not load price')

        # use old price from session
        else:
            portfolio[row.ticker].update({
                'price': oldprice[row.ticker]['price'],
                'fullPrice': oldprice[row.ticker]['price'] * row.number
            })

        # use full price to calculate total sum
        total += portfolio[row.ticker]['fullPrice']

    print(f"total before cash {total}")

    # PREPARE CASH INFO
    # load exchange info: rub to USD and EURO to USD
    if loadprice == True:
        exchange = {
            "euro": apiexchange('EUR'),
            "rub" : apiexchange('RUB')
        }

        print(exchange)

        if exchange is None:
            error_page("Could not load exchange rates")

    else:
        exchange = oldexchange

    # load cash info from db
    cash_datas = cash_db.query.filter_by(userid=userid).all()
    print(f"Extracted from cash_db data is {cash_datas}")


    if len(cash_datas) == 0:
        return False

    cash = {}
    for cashres in cash_datas:
        # save cash and exchange info
        cash["rub"] = {
            "value":cashres.rub,
            "usdprice": exchange["rub"]*cashres.rub,
            "tousd": exchange["rub"],
            "symbol":"₽"
        }
        cash["usd"] = {
            "value": cashres.usd,
            "usdprice": cashres.usd,
            "tousd": 1,
            "symbol":"$"
        }
        cash["euro"] = {
            "value": cashres.euro,
            "usdprice": exchange["euro"]*cashres.euro,
            "tousd": exchange["euro"],
            "symbol":"€"
        }

        # CALCULATE TOTAL SUM AND FRACTION
        # add to total sum cash in usd
        total = total + cash["rub"]["usdprice"] + cash["euro"]["usdprice"] + cash["usd"]["usdprice"]

        # calculate fraction for cash
        for key in cash:
            cash[key]['realFraction'] = real_fraction_calc(cash[key]["usdprice"], total)

        # real fraction calculation
        for key in portfolio:
            portfolio[key]["realFraction"] = real_fraction_calc(portfolio[key]['fullPrice'], total)
            portfolio[key]["suggestion"] = rebalance_suggestion(portfolio[key]["number"],portfolio[key]["price"],portfolio[key]["fraction"],total)

    print(f"\nPortfolio saved in session is\n {portfolio}")
    print(f"\nCash saved in session is\n {cash}")
    print(f"\nTotal saved in session is\n {total}")

    # save results in session
    # TODO clear session after 12 hours
    session['portfolio'] = portfolio
    session['cash'] = cash
    session['total'] = total

    # case we reload prices
    if session.get('datetime') is None:
        session['datetime'] = time.strftime("%d-%m-%Y, %H:%M")
        #TODO make heroku set right time zone

    return True


def rebalance_suggestion(number, price, fraction, total):
    # calculate number for ticker based on desired fraction
    if price != 0:
        newnumber = round(total * fraction / 100 / price)
        res = newnumber - number
        return res
    else:
        return None


def real_fraction_calc(part, total):
    if total != 0:
        res = math.floor(100 * part / total)
        return res
    else:
        print("total is zero")
        return None