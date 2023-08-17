import pprint
from datetime import datetime, timedelta

import requests
import json


def rzdfind(date):
  url = "https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/TrainPricing?service_provider=B2B_RZD"

  payload = json.dumps({
    "Origin": "2000000",
    "Destination": "2004000",
    "DepartureDate": date,
    "TimeFrom": 0,
    "TimeTo": 24,
    "CarGrouping": "DontGroup",
    "GetByLocalTime": True,
    "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons"
  })
  headers = {
    'sec-ch-ua': '"Not/A)Brand";v="99", "Google Chrome";v="115", "Chromium";v="115"',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'sec-ch-ua-mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'sentry-trace': 'a77deacef2644df4a2669794039f9a4e-87b5ea91c660179e-1',
    'sec-ch-ua-platform': '"macOS"',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'host': 'ticket.rzd.ru',
    'Cookie': 'session-cookie=177670e7b0b2a17dbd64334d6940ac72715fcb65feb24b902687c9746d324c6084e21755e85917975c092188951a8ad2'
  }

  response = requests.request("POST", url, headers=headers, data=payload).json()
  return response

# def getprice(data,current_date_str):
#     min_prices = {}
#     for item in data["Trains"]:
#       vagon = item["CarGroups"]
#       for _ in vagon:
#         if _['CarTypeName'] == "ПЛАЦ":
#           date = current_date_str
#           train = item["DisplayTrainNumber"]
#           arrival = item["ArrivalDateTime"]
#           departure = item["DepartureDateTime"]
#           price = _['MinPrice']
#
#           if date in min_prices:
#             if price < min_prices[date]["price"]:
#               min_prices[date] = {
#                 "date": date,
#                 "train": train,
#                 "Arrival": arrival,
#                 "Departure": departure,
#                 "price": price
#               }
#           else:
#             min_prices[date] = {
#               "date": date,
#               "train": train,
#               "Arrival": arrival,
#               "Departure": departure,
#               "price": price
#             }
#     return min_prices

def getprice(data, current_date_str):
    min_prices = {}
    for item in data["Trains"]:
      vagon = item["CarGroups"]
      for _ in vagon:
        date = current_date_str
        train = item["DisplayTrainNumber"]
        arrival = item["ArrivalDateTime"]
        departure = item["DepartureDateTime"]
        price = _['MinPrice']
        vagon_type = _['CarTypeName']
        disabledpersonflag = _["HasPlacesForDisabledPersons"]

        if date not in min_prices:
          min_prices[date] = {}

        if vagon_type not in min_prices[date]:
          min_prices[date][vagon_type] = {}


        if not disabledpersonflag and ("price" not in min_prices[date][vagon_type] or price < min_prices[date][vagon_type]["price"]):
          min_prices[date][vagon_type] = {
            "train": train,
            "departure" : departure,
            "arrival": arrival,
            "price": price

          }

    return min_prices

def startfind():
  start_date = datetime.strptime("2023-10-10", "%Y-%m-%d")
  end_date = datetime.strptime("2023-10-12", "%Y-%m-%d")

  a = []
  min_prices_cal = {}

  current_date = start_date

  while current_date <= end_date:
    current_date_str = current_date.strftime("%Y-%m-%dT%H:%M:%S")
    data = rzdfind(current_date_str)
    min_prices_cal.update(getprice(data,current_date_str))
    current_date += timedelta(days=1)
    print(current_date_str)

  print(min_prices_cal)
  # a = list(min_prices_cal.values())
  #
  # filtered_data = [d for d in a if d['price'] < 1800]
  #
  # for item in filtered_data:
  #   print(item)



startfind()

