import time
import json
import asyncio
import logging
import requests
from binance import Client, AsyncClient, BinanceSocketManager
from binance.helpers import round_step_size

logging.basicConfig(level=logging.INFO)

def get_notice_list():
    response = requests.get('https://api-manager.upbit.com/api/v1/notices?page=1&per_page=20&thread_name=general')
    data = json.loads(response.text)['data']['list']
    return data

def get_add_market_list(title):
    # [거래] KRW, BTC 마켓 디지털 자산 추가 (SHIB, GAL)
    if '마켓 디지털 자산 추가' in title and '[거래]' in title:
        assets = []
        try:
            plain = title.split('(')[1].split(')')[0]
            assets = plain.split(', ')
        except:
            pass
        return assets

    return []

BINANCE_API_KEY = ''
BINANCE_SECRET_KEY = ''

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

def get_precision(symbol):
    info = client.get_exchange_info()
    for x in info['symbols']:
        if x['symbol'] == symbol:
            for y in x['filters']:
                if y['filterType'] == 'LOT_SIZE':
                    return y['stepSize']
    return None

def buy_binance(asset):
    # 1시간전 비해서 20% 올랐으면 안사기
    symbol = '{0}USDT'.format(asset)
    buy_price = -1
    try:
        logging.info('start')
        klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, "1 hour ago UTC")
        open_price = float(klines[0][1])
        close_price = float(klines[0][4])
        if close_price > open_price * 1.2:
            logging.info('skip..')
            return -1

        balance = float(client.get_asset_balance(asset='USDT')['free'])
        logging.info('order start..')
        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quoteOrderQty=balance
        )
        logging.info('order end..')

        # 평단가 계산
        s = 0
        cnt = 0
        for fill in order['fills']:
            s += float(fill['price'])
            cnt += 1
        # print(order)
        return s / cnt
    except:
        return -1
    
def sell_binance(assets, buy_price):
    if len(assets) == 0:
        return False

    buy_price_map = {}
    for i in range(len(assets)):
        buy_price_map[assets[i]] = buy_price[i]
    
    wait_sell_count = 0
    for price in buy_price:
        if price != -1:
            wait_sell_count += 1
    
    sell_count = 0

    start_time = time.time()

    async def main():
        nonlocal sell_count
        client = await AsyncClient.create()
        bm = BinanceSocketManager(client)
        streams = []
        for asset in assets:
            streams.append(asset.lower()+'usdt@bookTicker')
        ms = bm.multiplex_socket(streams)

        async with ms as tscm:
            while sell_count < wait_sell_count:
                res = await tscm.recv()
                handle_socket_message(res)

        await client.close_connection()
    
    def handle_socket_message(msg):
        nonlocal sell_count
        for asset in assets:
            symbol = asset + 'USDT'
            if symbol == msg['data']['s']:
                if buy_price_map[asset] == -1:
                    return
                price = float(msg['data']['a'])
                if price >= buy_price_map[asset] * 1.2 or price <= buy_price_map[asset] * 0.9 or time.time() >= start_time + 3600:
                    balance = float(client.get_asset_balance(asset=asset)['free'])
                    print(balance)
                    step_sz = float(get_precision(symbol))
                    quantity = round_step_size(balance, step_sz) - step_sz
                    client.create_order(
                        symbol=symbol,
                        side=Client.SIDE_SELL,
                        type=Client.ORDER_TYPE_MARKET,
                        quantity=quantity
                    )
                    sell_count += 1
                    logging.info('sell sell_count: {}'.format(sell_count))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    return True
    
if __name__ == '__main__':
    # initialize
    notices = get_notice_list()
    newest_id = int(notices[0]['id'])

    count = 0

    logging.info('start')

    while True:
        time.sleep(1)
        if count % 10000 == 0:
            logging.info(count)
        count += 1
        try:
            notices = get_notice_list()
        except:
            logging.info('error #1')
            continue
        new_notices = []
        for notice in notices:
            id = int(notice['id'])
            if id > newest_id:
                new_notices.append(notice)
            else:
                break

        if len(new_notices) == 0:
            continue

        for new_notice in new_notices:
            title = new_notice['title']
            assets = get_add_market_list(title)

            if len(assets) == 0:
                continue

            bn_assets = []

            for asset in assets:
                symbol = '{0}USDT'.format(asset)
                try:
                    info = client.get_ticker(symbol=symbol)
                    bn_assets.append(asset)
                except:
                    pass
            
            if len(bn_assets) == 0:
                continue

            buy_price = [] 
            for asset in bn_assets:
                logging.info(f'{asset}')
                price = buy_binance(asset)
                logging.info(price)
                buy_price.append(price)
            sell_binance(bn_assets, buy_price)

        newest_id = int(new_notices[0]['id'])