from Robinhood import Robinhood
import configparser
import time
import pyotp
import serial
import traceback
import datetime

# Read configuration.
config = configparser.ConfigParser()
config.read('config.ini')


def init_display(serial):
    serial.write(b'\xFE\x56\x01\xFE\x56')


def write_to_line(serial, line=1, left_text="", right_text=""):
    msg = "%s%s" % (left_text, right_text)
    spaces = ""
    if len(msg) < int(config['display']['WIDTH']):
        while len(msg) < int(config['display']['WIDTH']):
            spaces = spaces + " "
            msg = "%s%s%s" % (left_text, spaces, right_text)
    elif len(msg) > int(config['display']['WIDTH']):
        raise Exception("Message exceeds %d characters" % int(config['display']['WIDTH']))

    payload = b"".join([b'\xFE\x47\x01', chr(line).encode(), msg.encode()])
    print(payload)
    serial.write(payload)


def clear_display(serial):
    for row in range(1, 5):
        serial.write(b"".join([b'\xFE\x47\x01', chr(row).encode(), (" " * int(config['display']['WIDTH'])).encode()]))


# Initialize serial port
ser = serial.Serial(config['display']['COM_PORT'], baudrate=int(config['display']['BAUD']))
init_display(ser)
clear_display(ser)

# Generate a TOTP Interface using the provided secret.
totp = pyotp.TOTP(config['robinhood']['multi_factor_secret'])

# Hook Robinhood API.
robinhood_interface = Robinhood()

# Attempt to authenticate
while True:
    try:
        totp_code = str(totp.now())

        write_to_line(ser, 1, "Authenticating with")
        write_to_line(ser, 2, "Robinhood API...")
        write_to_line(ser, 4, "TOTP CODE: %s" % totp_code)

        time.sleep(3)

        robinhood_interface.login(
            username=config['robinhood']['username'],
            password=config['robinhood']['password'],
            mfa_code=totp_code
        )

        clear_display(ser)
        write_to_line(ser, 1, "Authentication OK")

        break
    except Exception as e:
        clear_display(ser)
        write_to_line(ser, 1, "Exception Occurred.")
        traceback.print_exc()

        for i in range(10, 0, -1):
            write_to_line(ser, 2, "Retrying in %d..." % i)
            time.sleep(1)

refresh_rate = 0
while True:
    # Portfolio payload.
    portfolio = robinhood_interface.portfolios()

    # Determine market and equity.
    if portfolio['extended_hours_portfolio_equity'] is None:
        write_to_line(ser, 1, "Market Status", "Open")
        equity = float(portfolio['equity'])
        refresh_rate = float(config['ticker']['market_open_refresh_rate'])
    else:
        write_to_line(ser, 1, "Market", "After Hours")
        equity = float(portfolio['extended_hours_portfolio_equity'])
        refresh_rate = float(config['ticker']['market_after_hours_refresh_rate'])

    # Write equity.
    write_to_line(ser, 2, "Equity", "${:0.2f}".format(equity))

    # Determine change
    change = equity - float(portfolio['adjusted_portfolio_equity_previous_close'])

    # Build change message
    if change == 0.0:
        write_to_line(ser, 3, "Change", "Not Trading")
        refresh_rate = float(config['ticker']['not_trading_refresh_rate'])
    else:
        motion = ("Gain", "Loss")[change < 0.0]
        write_to_line(ser, 3, "Daily %s" % motion, "${:0.2f}".format(change))

    write_to_line(ser, 4, "Updated", "%s" % datetime.datetime.now().time().strftime("%I:%M:%S %p"))
    time.sleep(refresh_rate)
