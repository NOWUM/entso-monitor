#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 29 14:58:52 2020

@author: maurer
"""

from entsoe_data_manager import EntsoeDataManager, EntsoePlantDataManager, Filter, revReplaceStr

import sqlite3 as sql
from contextlib import closing, contextmanager

from datetime import datetime, date
import pandas as pd
from typing import List

ftime_sqlite = {'day': '%Y-%m-%d',
                'month': '%Y-%m-01',
                'year': '%Y-01-01',
                'hour': '%Y-%m-%d %H:00:00',
                'minute': '%Y-%m-%d %H:%M:00'}

ftime_pg = {'day': 'YYYY-MM-DD',
            'month': 'YYYY-MM-01',
            'year': 'YYYY-01-01',
            'hour': 'YYYY-MM-DD %H:00:00',
            'minute': 'YYYY-MM-DD HH24:MI:00'}

def groupTime(groupby, column):
    #return f'strftime("{ftime_sqlite[groupby]}", "{column}")' # SQLite
    return f"to_char('{column}', '{ftime_pg[groupby]}')" # PostgreSQL


class EntsoeSQLite(EntsoeDataManager):
    def __init__(self, database: str):
        if database:
            if database.startswith('postgresql'):
                from sqlalchemy import create_engine
                self.engine = create_engine(database)
                @contextmanager
                def access_db():
                    yield self.engine

                self.db_accessor = access_db
            else:
                self.db_accessor = lambda: closing(sql.connect(database))
        else:
            self.db_accessor = None

    def capacity(self, country: str):
        with self.db_accessor() as conn:
            query = f'select distinct * from query_installed_generation_capacity where country="{country}"'
            cap = pd.read_sql_query(query, conn, index_col='index')
        cap.columns = cap.columns.map(revReplaceStr)
        return cap

    def load(self, country: str, filt: Filter):
        # average is correct here as some countries have quarter hour data and others
        whereString = f'country="{country}" and "{filt.begin.strftime("%Y-%m-%d")}" < "index" and "index" < "{filt.end.strftime("%Y-%m-%d")}"'
        selectString = f'{groupTime(filt.groupby, "index")} as time, avg("0") as value'
        groupString = groupTime(filt.groupby, "time")
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_load where {whereString} group by {groupString}"
            load = pd.read_sql_query(query, conn, index_col='time')
        return load

    def generation(self, country: str, filt: Filter):
        whereString = f'country="{country}" and "{filt.begin.strftime("%Y-%m-%d")}" < "index" and "index" < "{filt.end.strftime("%Y-%m-%d")}"'
        selectString = f'{groupTime(filt.groupby, "index")} as time'
        groupString = groupTime(filt.groupby, "time")
        with self.db_accessor() as conn:
            columns = list(pd.read_sql_query(
                'select * from query_generation where 1=0', conn).columns)
            columns.remove('country')
            columns.remove('index')
            colNames = ','.join(
                [f'avg("{column}") as "{column}"' for column in columns])+', country '

            query = f"select {selectString},{colNames} from query_generation where {whereString} group by {groupString}"
            gen = pd.read_sql_query(query, conn, index_col='time')
        gen.columns = gen.columns.map(''.join).map(revReplaceStr)
        return gen

    def _selectBuilder(self, neighbours):
        res = ''
        for x in neighbours:
            fr = x.split('-')[0]
            to = x.split('-')[1]
            # export - import
            res += f'avg("{fr}-{to}"-"{to}-{fr}") as diff_{to}'
            res += ','
        return res

    def _neighbours(self, fromC):
        with self.db_accessor() as conn:
            query = 'select * from query_crossborder_flows where 0=1'
            columns = pd.read_sql_query(query, conn).columns
        nei = []
        for x in columns:
            sp = x.split('-')
            if sp[0] == fromC:
                nei.append(x)
                # nei.append(sp[1]+'.'+sp[0])
        return nei

    def crossborderFlows(self, country: str, filt: Filter):
        whereString = f'"{filt.begin.strftime("%Y-%m-%d")}" < "index" and "index" < "{filt.end.strftime("%Y-%m-%d")}"'

        nei = self._neighbours(country)
        selectString = f'{self._selectBuilder(nei)} {groupTime(filt.groupby, "index")} as time'

        groupString = groupTime(filt.groupby, "time")
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_crossborder_flows where {whereString} group by {groupString}"
            cross = pd.read_sql_query(query, conn, index_col='time')
        return cross
        # relList= map(lambda x: x.split('.'),crossborder.columns)
        # filteredRelations=filter(lambda x: x.count(country)>0,relList)
        # columns=list(map(lambda x: '{}.{}'.format(x[0],x[1]), filteredRelations))
        # columns.append('group')

        # return crossborder.select(columns).groupby(['group']).sum().toPandas()

    def countries(self):
        with self.db_accessor() as conn:
            df = pd.read_sql(
                'select name, value, meaning from areas', conn)
        return df

    def climateImpact(self):
        climate = pd.read_csv(
            'CO2_factors_energy_carrier.CSV', sep=';', index_col=0)
        return climate


class EntsoePlantSQLite(EntsoePlantDataManager):
    def __init__(self, plantdatabase: str):
        if plantdatabase:
            if plantdatabase.startswith('postgresql'):
                from sqlalchemy import create_engine
                self.engine = create_engine(plantdatabase)
                @contextmanager
                def access_db():
                    yield self.engine

                self.db_accessor = access_db
            else:
                self.db_accessor = lambda: closing(sql.connect(database))
        else:
            self.db_accessor = None

    def plantGen(self, names: List[str], filt: Filter):
        # average is correct here as some countries have quarter hour data and others
        inString = '("'+'","'.join(names)+'")'
        whereString = f'name in {inString} and "{filt.begin.strftime("%Y-%m-%d")}" < "index" and "index" < "{filt.end.strftime("%Y-%m-%d")}"'
        selectString = f'{groupTime(filt.groupby, "index")} as time, avg("value") as value, country, type, name'
        groupString = f'{groupTime(filt.groupby, "time")}, name, type'
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_per_plant where {whereString} group by {groupString}"
            generation = pd.read_sql_query(query, conn, index_col='time')
        return generation

    def getNames(self):
        with self.db_accessor() as conn:
            # TODO add type
            query = "select distinct name,country from plant_names"
            names = pd.read_sql_query(query, conn)
        return names

    def capacityPerPlant(self, country=''):
        selectString = 'Name,country,"Installed_Capacity_[MW]" as capacity,Production_Type'
        if country == '':
            whereString = ''
        else:
            whereString = f'where country="{country}"'
        with self.db_accessor() as conn:
            query = f'select distinct {selectString} from query_installed_generation_capacity_per_unit {whereString}'
            df = pd.read_sql(query, conn)
        return df

    def powersystems(self, country=''):
        selectString = 'eic_code,p.name,q.name as entsoe_name, company,p.country,q.country as area,lat,lon,capacity,Production_Type'
        if country == '':
            whereString = ''
        else:
            whereString = f'where p.country="{country}"'
        with self.db_accessor() as conn:
            df = pd.read_sql(
                f'select {selectString} from powersystemdata p join query_installed_generation_capacity_per_unit q on q."index" = p.eic_code {whereString}', conn)
        return df


if __name__ == "__main__":
    country = 'NL'
    par = EntsoeSQLite('data/entsoe.db')
    filt = Filter(datetime(2020, 9, 1), datetime(2020, 9, 2), 'hour')
    neighbours = par.crossborderFlows(country, filt)
    cap = par.capacity(country)
    countries = par.countries()
    country = countries['name'][0]

    df2 = par.powersystems()
    filt = Filter(datetime(2020, 2, 1), datetime(2020, 2, 2), 'hour')
    load = par.load(country, filt)
    generation = par.generation(country, filt)
    del generation['country']
    generation = generation/1000
    gen = generation.melt(
        var_name='kind', value_name='value', ignore_index=False)
    climate = par.climateImpact()
    generation.fillna(0, inplace=True)
    nox = generation*climate['Summe NOX']

    g = generation
    g.fillna(0, inplace=True)
    g = g.loc[:, (g != 0).any(axis=0)]
    # from entsoe_data_manager import EntsoeDataManager
    # issubclass(par.__class__,EntsoeDataManager)

    #     data.to_sql('query_crossborder_flows',conn)
    #     columns = pd.read_sql_query(f'select * from DE_query_generation where 1=0',conn).columns
    #         query = "select * from DE_query_generation"
    #         gen = pd.read_sql_query(query,conn)
    filt = Filter(datetime(2018, 2, 1), datetime(2019, 2, 2), 'hour')
    ep = EntsoePlantSQLite('data/entsoe.db')
    names = ep.getNames()
    nossener = ep.plantGen(['GTHKW Nossener Bruecke'], filt)
    doel2 = ep.plantGen(['DOEL 2'], filt)

    # oft falsch, nuklear richtig
    aa = par.capacityPerPlant('FR')
    aa['capacity'] = aa['capacity'].astype(float)
    aaa = aa.groupby('Production_Type').sum()['capacity']