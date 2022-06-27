#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Oct 18 15:35:12 2021

@author: maurer
"""

from entsoe import EntsoePandasClient
import pandas as pd

from entsoe_vis.entsoe_crawler import EntsoeCrawler
from entsog.entsog_crawler import EntsogCrawler


def updateEntsoe(db, api_key, first=False):
    client = EntsoePandasClient(api_key=api_key)
    crawler = EntsoeCrawler(database=db)

    if first:
        start = pd.Timestamp('20150101', tz='Europe/Berlin')
        delta = pd.Timestamp.now(tz='Europe/Berlin')-start
        c = ['DE_AT_LU']
        crawler.createDatabase(client, start, delta, countries=c)
    else:
        crawler.updateDatabase(client)


def updateEntsog(db, first=False):
    crawler = EntsogCrawler(db, sparkfolder=None)

    names = ['cmpUnsuccessfulRequests',
             # 'operationaldata',
             # 'cmpUnavailables',
             # 'cmpAuctions',
             # 'AggregatedData', # operationaldata aggregated for each zone
             # 'tariffssimulations',
             # 'tariffsfulls',
             # 'urgentmarketmessages',
             'connectionpoints',
             'operators',
             'balancingzones',
             'operatorpointdirections',
             'Interconnections',
             'aggregateInterconnections']
    if first:
        crawler.pullData(names)

    indicators = ['Physical Flow', 'Allocation', 'Firm Technical']
    crawler.pullOperationalData(indicators)


if __name__ == '__main__':
    # updateEntsoe('data/entsoe.db',first=False)
    # updateEntsog('data/entsog.db',first=False)
    db = os.getenv('DATABASE_URI','postgresql://entso:entso@10.13.10.41:5432')
    from sqlalchemy import create_engine

    t = create_engine(f'{db}/entsoe')

    import os
    api_key = os.getenv('ENTSOE_API_KEY', 'ae2ed060-c25c-4eea-8ae4-007712f95375')
    updateEntsoe(f'{db}/entsoe', api_key, first=True)
    #updateEntsog(f'{db}/entsog', first=True)
