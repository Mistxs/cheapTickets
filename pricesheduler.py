from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler


import requests
import json
from tqdm import tqdm

import tgbot

headers = {
        'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJsdHBhVG9rZW4iOiJaS1RsVUM1RllBVWZ1NUtteVdOcHFjYkI4ZmovN29DdUUrbWc1MGdsdjVpWk4rTVVSOHIrK1NnaHQzd0o5dFZNa2xvc2ZOTW5URlZtQ1p1MURVZnR5bVU3aS9oOEp1NmhwZXV3czVEdkZoU1hNdDhtSFlVSzhyNkZwVjFoNWkvdUUxWjVWOVJ6cWMvTTVkdFFkMkowbUdRL2xKb0p3b3pTZXVFV0dMTzhVUTNmcjRucVVZWnE0Rm5tUnpJTmpUM0pRaE5kaUpyRVhLRWVRTWtFbjIwR2lqSEk0VHZwViswYWdFbzB1RVRDTER3RHZwb0xJMWhaMjdYMElycVFhaSs4Y2JaaFYyWFlTNWFCeUprT3UzZWtmWis5U1ZYbHJqVDlzWWFLdkJ6d0prRjBvZkU1UjJzYVhLc2U3aGdIemUrNkF4elFvU1ZIOEg1MU1oSTdDL1Z1bklxVExHV2pjcXRyVnpKYTc0ait5YXdCNGNzYldTUXpNOWhaaXFtY0hma1VyWVFlQ25YakgzelZRSUo2Z1R2cXo4Zng1dmpEQ0psZWFOYmdzNWxFMUlDcHFDQkpyWFU3bWp1VDlWa1hxT0FnWjRiSTBja2UvU2JKRkdYcjdHbDFmM2l1VEhZcWJjYmNMbUdoNjU2V29Dc05ONDRGc045U3ErdmQrdWQ1VFJja0pwK2pUMnBZOElkcVBBUUdERnFiTWloT2E4cktYOGNiYlhWM2R3Q0FmWDZPek1DUDV5cWtURmhWZGI0ZkdyUktRcXVCUWwrNExyTTJNcGdhV3MxcXBvSEwxcWFCMWpFSFNVYUphUFVpWnVjUFBpUW9UOTNHMDYzQkoxVTQwZzJXIiwibG9naW4iOiJmaWxpcHBvdmFuYXRvbGl5IiwiZW1haWwiOiJmaWxpcHBvdmFuYXRvbGl5QHlhLnJ1IiwidXNlcl9pZCI6MTEyMTg0MiwiYWN0aXZlIjp0cnVlLCJzZXNzaW9uS2V5IjoiQXV0aF9zdmMtZTA1NzJhMTQ0NWFlZGRlZDU4ZGVkYjU4ZGU3ZDRhZGU2NjMzY2M0NTQ1YzVhYTgyYTc2YjBmYTYwMWIyNThhNSIsImNvcnBvcmF0ZSI6ZmFsc2UsImZpbHRlcl9jYXJyaWVycyI6W10sImtzaWQiOiI4ZjJlMmNiNi0wZTYyLTRmYzYtOTk0Yi1jMTVhY2U1MjI1OTNfMSIsImlzcyI6InRpY2tldC5yemQucnUiLCJleHAiOjE3MjMwMzUxNjl9.Qr2yy-1vRq4Y9zYJPf3lh5lWpMgMBb6U4ULGXJGBxfc',
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'sentry-trace': '44ea49ae99184bb4b4492ba72bee2a44-aa32efb8bdcbf4df-1',
        'sec-ch-ua-platform': '"macOS"',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'host': 'ticket.rzd.ru',
        'Cookie': 'JSESSIONID=7BDA5CD4DEACF997AAD767BB1A0CC08F; session-cookie=17e922ccc3b22d908c49fa3318991a24ca71a347ac0def63c87a6c8ea923da3d20590687d1590afe265285f320c9f32d'
    }

traindata = []

def trainOnDay(date, cityfrom, cityto):
    url = "https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/TrainPricing?service_provider=B2B_RZD"

    payload = json.dumps({
        "Origin": cityfrom,
        "Destination": cityto,
        "DepartureDate": date,
        "TimeFrom": 0,
        "TimeTo": 24,
        "CarGrouping": "DontGroup",
        "GetByLocalTime": True,
        "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons"
    })


    response = requests.request("POST", url, headers=headers, data=payload).json()

    return response
def parsetraindata(traindata):
    reformattraindata = []
    for item in tqdm(traindata["Trains"], desc="Parsing"):
        vagon = item["CarGroups"]
        for _ in vagon:
            train = item["DisplayTrainNumber"]
            depstation = item["OriginName"]
            arrstation = item["DestinationName"]
            arrival = item["ArrivalDateTime"]
            departure = item["DepartureDateTime"]
            price = _['MinPrice']
            vagon_type = _['CarTypeName']
            disabledpersonflag = _["HasPlacesForDisabledPersons"]
            if vagon_type in ["КУПЭ", "ПЛАЦ"]:
                datas = {
                    "train": train,
                    "vagon_type": vagon_type,
                    "departure": departure,
                    "arrival": arrival,
                    "depstation": depstation,
                    "arrstation": arrstation,
                    "price": price
                }
                reformattraindata.append(datas)
    return reformattraindata
def getPlaces(cityfrom, cityto, departure, train):
    url = "https://ticket.rzd.ru/api/v1/railway/carpricing/lite"

    payload = json.dumps({
        "OriginCode": cityfrom,
        "DestinationCode": cityto,
        "Provider": "P1",
        "DepartureDate": departure,
        "TrainNumber": train,
        "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons",
        "OnlyFpkBranded": False
    })

    response = requests.request("POST", url, headers=headers, data=payload).json()

    return response


cityfrom = 2064150
cityto = 2000000
DepartureDate = "2024-10-14T00:00:00"

def retprettydata(tickets):
    formatted = []
    for ticket in tqdm(tickets,desc="prettied data"):
        for place in ticket["places"]:
            if place["CarPlaceType"] == "Lower" and place['CarType'] == "ReservedSeat":
                quantity = place["PlaceQuantity"]
                price = place["MinPrice"]
                formatted.append({
                    'train': ticket['train'],
                    'type': ticket['vagon_type'],
                    'departure': ticket['departure'],
                    'prices': {
                        'lower': {
                            'Quantity': quantity,
                            'Price': price
                        }
                    }
                })
    return formatted

def startfind(date):
    trains = trainOnDay(date, cityfrom, cityto)
    traindata = parsetraindata(trains)
    goodtickets = []
    for train in tqdm(traindata, desc="find places"):
        places = getPlaces(cityfrom, cityto, train['departure'], train['train'])
        for place in places:
            if place['CarPlaceType'] == 'Lower' and place['CarType'] == "ReservedSeat":
                goodtickets.append(train)
        train['places'] = places
    lowertickets = retprettydata(goodtickets)
    if lowertickets:
        print("ЕСТЬ БИЛЕТЫ")
        tgbot.check_tickets(lowertickets)


def run():
    start_date = "2024-09-15T00:00:00"
    end_date = "2024-09-17T00:00:00"

    # start_date = "2024-10-10T00:00:00"
    # end_date = "2024-10-15T00:00:00"

    start_date = datetime.fromisoformat(start_date)
    end_date = datetime.fromisoformat(end_date)

    current_date = start_date

    while current_date <= end_date:
        date = current_date.strftime("%Y-%m-%dT%H:%M:%S")
        startfind(date)
        current_date += timedelta(days=1)


scheduler = BlockingScheduler()
scheduler.add_job(run, 'interval', minutes=15)

try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    pass



