#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 29 14:58:52 2020

@author: maurer
"""

from entsoe_data_manager import EntsoeDataManager, EntsoePlantDataManager, Filter, revReplaceStr

import sqlite3
from contextlib import closing, contextmanager

from datetime import datetime, date
import pandas as pd
from typing import List
from sqlalchemy import create_engine

ftime_sqlite = {'day': '%Y-%m-%d',
                'month': '%Y-%m-01',
                'year': '%Y-01-01',
                'hour': '%Y-%m-%d %H:00:00',
                'minute': '%Y-%m-%d %H:%M:00'}

ftime_pg = {'day': 'YYYY-MM-DD',
            'month': 'YYYY-MM-01',
            'year': 'YYYY-01-01',
            'hour': 'YYYY-MM-DD hh24:00:00',
            'minute': 'YYYY-MM-DD hh24:mi:00'}

class EntsoeSQLite(EntsoeDataManager):
    def __init__(self, database: str):
        self.use_pg = database.startswith('postgresql')
        if self.use_pg:
            self.engine = create_engine(database)
            @contextmanager
            def access_db():
                with self.engine.connect() as conn, conn.begin():
                    yield conn

            self.db_accessor = access_db
        else:
            self.db_accessor = lambda: closing(sqlite3.connect(database))

    def groupTime(self, groupby, column):
        if self.use_pg:
            return f"to_char({column}, '{ftime_pg[groupby]}')" # PostgreSQL
        else:
            return f'strftime("{ftime_sqlite[groupby]}", "{column}")' # SQLite

    def capacity(self, country: str):
        with self.db_accessor() as conn:
            query = f"select distinct * from query_installed_generation_capacity where country='{country}'"
            cap = pd.read_sql_query(query, conn, index_col='index')
        cap.columns = cap.columns.map(revReplaceStr)
        return cap

    def load(self, country: str, filt: Filter):
        # average is correct here as some countries have quarter hour data and others
        whereString = f"country='{country}' and '{filt.begin.strftime('%Y-%m-%d')}' < index and index < '{filt.end.strftime('%Y-%m-%d')}'"
        selectString = f'{self.groupTime(filt.groupby, "index")} as time, avg("actual_load") as value'
        groupString = f'{self.groupTime(filt.groupby, "index")}'
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_load where {whereString} group by {groupString}  order by time desc"
            load = pd.read_sql_query(query, conn, index_col='time')
        return load

    def generation(self, country: str, filt: Filter):
        whereString = f"country='{country}' and '{filt.begin.strftime('%Y-%m-%d')}' < index and index < '{filt.end.strftime('%Y-%m-%d')}'"
        selectString = f'{self.groupTime(filt.groupby, "index")} as time'
        groupString = f'{self.groupTime(filt.groupby, "index")}, country'
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
        '''
        builds the select statement for the difference of import and export
        '''
        res = ''
        for x in neighbours:
            fr = x.split('-')[0]
            to = x.split('-')[1]
            # export - import
            res += f'avg("{fr}-{to}"-"{to}-{fr}") as diff_{to}'
            res += ','
        return res

    def _neighbours(self, fromC):
        '''
        finds all neighbours of a country by looking at the columns of query_crossborder_flows
        '''
        with self.db_accessor() as conn:
            query = 'select * from query_crossborder_flows where 0=1'
            columns = pd.read_sql_query(query, conn).columns
        nei = []
        for columnname in columns:
            # some columns are meaningless and only one direction exists
            if columnname in ['fr-it_nord_fr', 'ch-it_nord_ch', 'de_at_lu-it_nord_at', 'pl-ua']:
                continue
            sp = columnname.split('-')
            if sp[0] == fromC:
                nei.append(columnname)
                # nei.append(sp[1]+'.'+sp[0])
        return nei

    def crossborderFlows(self, country: str, filt: Filter):
        whereString = f"'{filt.begin.strftime('%Y-%m-%d')}' < index and index < '{filt.end.strftime('%Y-%m-%d')}'"

        nei = self._neighbours(country.lower())
        selectString = f'{self._selectBuilder(nei)} {self.groupTime(filt.groupby, "index")} as time'

        groupString = f'{self.groupTime(filt.groupby, "index")}'
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_crossborder_flows where {whereString} group by {groupString}"
            cross = pd.read_sql_query(query, conn, index_col='time')
        return cross.sort_index()
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
        self.use_pg = plantdatabase.startswith('postgresql')
        if self.use_pg:
            self.engine = create_engine(plantdatabase)
            @contextmanager
            def access_db():
                with self.engine.connect() as conn, conn.begin():
                    yield conn

            self.db_accessor = access_db
        else:
            self.db_accessor = lambda: closing(sqlite3.connect(plantdatabase))

    def groupTime(self, groupby, column):
        if self.use_pg:
            return f"to_char({column}, '{ftime_pg[groupby]}')" # PostgreSQL
        else:
            return f'strftime("{ftime_sqlite[groupby]}", "{column}")' # SQLite

    def plantGen(self, names: List[str], filt: Filter):
        # average is correct here as some countries have quarter hour data and others
        inJoinString = "','".join(names)
        inString = f"('{inJoinString}')"
        whereString = f"name in {inString} and '{filt.begin.strftime('%Y-%m-%d')}' < index and index < '{filt.end.strftime('%Y-%m-%d')}'"
        selectString = f'{self.groupTime(filt.groupby, "index")} as time, avg("value") as value, country, type, name'
        groupString = f'{self.groupTime(filt.groupby, "index")}, name, type, country'
        with self.db_accessor() as conn:
            query = f"select {selectString} from query_per_plant where {whereString} group by {groupString}"
            generation = pd.read_sql_query(query, conn, index_col='time')
        return generation.sort_index()

    def getNames(self):
        '''
        returns a list of plant names and countries with existing generation data
        '''
        with self.db_accessor() as conn:
            # TODO add type
            query = "select distinct name,country from plant_names"
            names = pd.read_sql_query(query, conn)
        return names

    def capacityPerPlant(self, country=''):
        selectString = 'Name,country,"Installed_Capacity_[MW]" as capacity,production_type'
        if country == '':
            whereString = ''
        else:
            whereString = f"where country='{country}'"
        with self.db_accessor() as conn:
            query = f'select distinct {selectString} from query_installed_generation_capacity_per_unit {whereString}'
            df = pd.read_sql(query, conn)
        return df

    def powersystems(self, country=''):
        '''
        returns a list of all power systems which exist in ENTSO-E and OPSD (open-power-system-data) - joined on the eic_code
        '''
        selectString = 'eic_code,p.name,q.name as entsoe_name, company,p.country,q.country as area,lat,lon,capacity,production_type'
        if country == '':
            whereString = ''
        else:
            whereString = f"where p.country='{country}'"
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
    generation = generation.fillna(value=0)
    nox = generation*climate['Summe NOX']

    g = generation
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
    aaa = aa.groupby('production_type').sum()['capacity']
