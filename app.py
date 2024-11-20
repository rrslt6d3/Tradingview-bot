import os
from flask import Flask, request, jsonify
import logging
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading

app = Flask(__name__)

# Configure Logging
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# Retrieve the secret token from environment variables
SECRET_TOKEN = os.getenv('SECRET_TOKEN', 'default_token_if_not_set')

# IBKR API Client
class IBApi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextOrderId = orderId
        logging.info(f"Next Valid Order ID: {self.nextOrderId}")

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                   permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice,
                           permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        logging.info(f"OrderStatus - ID: {orderId}, Status: {status}, Filled: {filled}, Remaining: {remaining}")

    def openOrder(self, orderId, contract, order, orderState):
        super().openOrder(orderId, contract, order, orderState)
        logging.info(f"OpenOrder - ID: {orderId}, Symbol: {contract.symbol}, Action: {order.action}, Quantity: {order.totalQuantity}")

    def execDetails(self, reqId, contract, execution):
        super().execDetails(reqId, contract, execution)
        logging.info(f"ExecDetails - ReqId: {reqId}, Symbol: {contract.symbol}, ExecId: {execution.execId}, Quantity: {execution.shares}, Price: {execution.price}")

ib_api = IBApi()

def run_ibapi():
    ib_api.connect('127.0.0.1', 4002, clientId=1)  # Ensure port matches IBeam configuration
    ib_api.run()

# Start IBKR API in a separate thread
ib_thread = threading.Thread(target=run_ibapi, daemon=True)
ib_thread.start()

@app.route('/webhook', methods=['POST'])
def webhook():
    # Authenticate the request
    token = request.headers.get('Authorization')
    if token != f"Bearer {SECRET_TOKEN}":
        logging.warning('Unauthorized access attempt.')
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    logging.info(f"Received webhook data: {data}")

    # Extract trading parameters from the webhook
    ticker = data.get('ticker')
    action = data.get('action')
    quantity = int(data.get('quantity', 0))

    if not ticker or not action or quantity <= 0:
        logging.error('Invalid trading data received.')
        return jsonify({'message': 'Invalid data'}), 400

    # Create IBKR Contract
    contract = Contract()
    contract.symbol = ticker
    contract.secType = 'STK'
    contract.exchange = 'SMART'
    contract.currency = 'USD'

    # Create IBKR Order
    order = Order()
    order.action = action
    order.orderType = 'MKT'
    order.totalQuantity = quantity

    # Place Order
    if ib_api.nextOrderId is None:
        logging.error('IBKR API not connected or nextOrderId not set.')
        return jsonify({'message': 'IBKR API not ready'}), 500

    try:
        ib_api.placeOrder(ib_api.nextOrderId, contract, order)
        logging.info(f"Placed order ID {ib_api.nextOrderId} for {action} {quantity} shares of {ticker}.")
        ib_api.nextOrderId += 1
        return jsonify({'message': 'Order placed successfully'}), 200
    except Exception as e:
        logging.error(f"Failed to place order: {e}")
        return jsonify({'message': 'Failed to place order'}), 500

@app.route('/')
def index():
    return "Automated Trading Flask App is Running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

