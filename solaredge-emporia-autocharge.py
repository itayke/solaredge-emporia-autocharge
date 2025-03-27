#!/usr/bin/python

# SolarEdge/Emporia EV Solar Charging Maximizer
# Copyright (C) 2025 Itay Keren

# This script connects to SolarEdge's and Emporia's global APIs through the user's preset login credentials located at .env, 
# continuously maximizing EV charging throughput with available solar power, reducing electric grid input to the minimum.
# Note that this script will never stop charging and a minimum charge of 6 amps will be used instead. (I may fix this in the future.)

import time
from datetime import datetime
import sys
import numbers
import json
import pyemvue
from pyemvue.enums import Scale, Unit
import requests
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve SolarEdge credentials from environment variables
SOLAREDGE_SITE = os.getenv('SOLAREDGE_SITE')
SOLAREDGE_KEY = os.getenv('SOLAREDGE_KEY')
SOLAREDGE_BASE_URL = os.getenv('SOLAREDGE_BASE_URL', 'https://monitoringapi.solaredge.com')

# Emporia Vue credentials
EMPORIA_ACCESS_FILE = 'emporia-access.json'

MIN_AMPS = 6
MAX_AMPS = 40

def parse_args():
    args_dict = {}
    for arg in sys.argv[1:]:
        keyval = arg.lstrip('-')
        if '=' in keyval:
            key, value = keyval.split('=', 1)
            args_dict[key] = value
        else:
            args_dict[keyval] = True
    return args_dict

# Default values
update_freq = 60
smooth = 5
min_amps = MIN_AMPS
max_amps = MAX_AMPS
offset_amps = 0
verbose = False

args = parse_args()
if 'help' in args or 'h' in args or '?' in args:
    print(f'Usage: {sys.argv[0]}\n' +
        f'      freq=<update frequency in seconds, default {update_freq}\n' +
        f'      smooth=<smooth size, default {smooth}>\n' +
        f'      min_amps=<minimum charge, default {min_amps}>\n' +
        f'      max_amps=<maximum charge, default {max_amps}>\n' +
        f'      offset_amps=<amp offset, default {offset_amps}>\n' +
        f'      verbose=<print extra info, default false>')
    exit(0)

if 'freq' in args:
    update_freq = int(args['freq'])

if 'smooth' in args:
    smooth = int(args['smooth'])

if 'min_amps' in args:
    min_amps = max(int(args['min_amps']), MIN_AMPS)

if 'max_amps' in args:
    max_amps = min(int(args['max_amps']), MAX_AMPS)

if 'offset_amps' in args:
    offset_amps = int(args['offset_amps'])
    
if 'verbose' in args:
    verbose_str = args['verbose']
    verbose = ((verbose_str.isnumeric() and int(verbose_str) != 0) or verbose_str.lower() == "true")

def solaredge_get_power_details(site_id, start_time, end_time):
    if not site_id or not start_time or not end_time:
        return {}

    api_endpoint = '/site/%s/powerDetails' % site_id
    full_api_url = SOLAREDGE_BASE_URL + api_endpoint

    parameters = {
        'startTime': start_time,
        'endTime': end_time,
        'api_key': SOLAREDGE_KEY,
        'meters': 'PRODUCTION,CONSUMPTION'
    }

    response = requests.get(full_api_url, params=parameters)
    return response.json()

def solaredge_get_site_power_flow(site_id):
    if not site_id:
        return {}

    api_endpoint = '/site/%s/currentPowerFlow' % site_id
    full_api_url = SOLAREDGE_BASE_URL + api_endpoint

    parameters = {
        'api_key': SOLAREDGE_KEY
    }

    response = requests.get(full_api_url, params=parameters)
    if verbose:
        print(f"code {response.status_code} content {response.content}");
    if response.status_code != 200:
        raise response.status_code
    return response.json()    

def vue_calc_usage_recursive(usage_dict, depth=0) -> float:
    usage = 0
    for gid, device in usage_dict.items():
        for channelnum, channel in device.channels.items():
            if verbose:
                print('-'*depth, f'{gid} {channelnum} {channel.name} {channel.usage} kwh')
            if isinstance(channel.usage, numbers.Number):
                usage += channel.usage
            if channel.nested_devices:
                usage += vue_calc_usage_recursive(channel.nested_devices, depth + 1)
    return usage

# Create a new Emporia Vue object
vue = pyemvue.PyEmVue()

# Login to Emporia
if os.path.exists(EMPORIA_ACCESS_FILE):
    with open(EMPORIA_ACCESS_FILE, 'r') as f:
        em_login_data = json.load(f)
else:
    em_login_data = None

# If no login data, use environment variables
if not em_login_data:
    em_login_data = {
        'username': os.getenv('EMPORIA_USER'),
        'password': os.getenv('EMPORIA_PASSWORD')
    }
    with open(EMPORIA_ACCESS_FILE, 'w') as f:
        json.dump(em_login_data, f)

# Login to Emporia, either using the stored tokens or the username/password
if em_login_data and 'id_token' in em_login_data and 'access_token' in em_login_data and 'refresh_token' in em_login_data:
    login_resp = vue.login(id_token=em_login_data['id_token'],
                           access_token=em_login_data['access_token'],
                           refresh_token=em_login_data['refresh_token'],
                           token_storage_file=EMPORIA_ACCESS_FILE)
else:
    login_resp = vue.login(username=em_login_data['username'],
                           password=em_login_data['password'],
                           token_storage_file=EMPORIA_ACCESS_FILE)

# Identify the charger
charger_device = None
devices = vue.get_devices()
outlets, chargers = vue.get_devices_status()
for device in devices:
    if verbose:
        print(device.device_gid, device.manufacturer_id, device.model, device.firmware)
    if device.ev_charger:
        if verbose:
            print(f'EV Charger! On={device.ev_charger.charger_on} Charge rate: {device.ev_charger.charging_rate}A/{device.ev_charger.max_charging_rate}A')
        charger_device = device
        break

if charger_device is None:
    print("No charger device found, exiting")
    exit(1)

# Sliding average of a certain length
def sliding_average(num, list_size):
    # Access the list stored in the function's closure
    if not hasattr(sliding_average, "values"):
        sliding_average.values = []

    # Add the new value to the list
    sliding_average.values.append(num)

    # Limit the list size
    if len(sliding_average.values) > list_size:
        sliding_average.values = sliding_average.values[-list_size:]

    # Calculate and return the average
    return sum(sliding_average.values) / len(sliding_average.values)

# Main service function: get site usage and current charge rate and update charge rate accordingly
def update_charge_amp_by_solaredge_data (): 
    # Get site current power data
    try:
        overview = solaredge_get_site_power_flow(SOLAREDGE_SITE)
    except:
        print("Error getting response from SolarEdge")
        return
    # {'siteCurrentPowerFlow': 
    #   {'updateRefreshRate': 3, 'unit': 'kW', 'connections': 
    #       [{'from': 'LOAD', 'to': 'Grid'}, {'from': 'PV', 'to': 'Load'}], 
    #       'GRID': {'status': 'Active', 'currentPower': 0.93}, 
    #       'LOAD': {'status': 'Active', 'currentPower': 0.88}, 
    #       'PV': {'status': 'Active', 'currentPower': 1.81}, 
    #       'STORAGE': {'status': 'Idle', 'currentPower': 0.0, 'chargeLevel': 100, 'critical': False}}}
    if verbose:
        print("Power Flow Data:", overview)
    
    prod_kw = float(overview['siteCurrentPowerFlow']['PV']['currentPower']);
    cons_kw = float(overview['siteCurrentPowerFlow']['LOAD']['currentPower'])
    print("Production Total", prod_kw)
    print("Consumption Total", cons_kw)
    prod_min_cons_kw = round(prod_kw - cons_kw, 2)
    print("Available Total", prod_min_cons_kw)
    
    # Get current charger output to subtract from consumption
    device_usage_dict = vue.get_device_list_usage(deviceGids=charger_device.device_gid, instant=None, scale=Scale.MINUTE.value, unit=Unit.KWH.value)
    cur_charger_usage_kw = round(vue_calc_usage_recursive(device_usage_dict) * 60.0, 2)
    print("Charger Consumption", cur_charger_usage_kw)
    available_for_charger_kw = round(prod_min_cons_kw + cur_charger_usage_kw, 2)
    print("Available for Charger", available_for_charger_kw)
    
    average_kw = round(sliding_average(available_for_charger_kw, smooth), 2)
    print("Smoothed value", average_kw, "Smooth size", smooth)
    
    amps_from_kw = int(average_kw * 1000 / 240) 
    amps = amps_from_kw + offset_amps
    final_amps = max(min(amps, max_amps), min_amps)
    
    offset_str = f'+{offset_amps}={amps}' if offset_amps > 0 else f'{offset_amps}={amps}' if offset_amps < 0 else ''
    print(f'Desired Amp {amps_from_kw}{offset_str} Range {min_amps}..{max_amps}')
    
    charger = charger_device.ev_charger
    pre_change = charger.charging_rate
    if pre_change == final_amps:
        print("No change -->", pre_change)
    else:
        charger.charging_rate = final_amps;
        charger = vue.update_charger(charger)
        print("Amp changed", pre_change, "-->", charger.charging_rate)

# 
#   Service
#

while True:
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    print("=========", dt_string, "=========")
    update_charge_amp_by_solaredge_data()
    time.sleep(update_freq)

