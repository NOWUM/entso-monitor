#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 29 23:15:16 2020

@author: maurer
"""
from datetime import datetime
from typing import List
import pandas as pd

from entsog_data_manager import EntsogDataManager, Filter

import sqlite3
from contextlib import closing, contextmanager
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

checkPipeInPipe = "pipeinpipewithtsokey is NULL"


def timeFilter(filt):
    return f"'{filt.begin.strftime('%Y-%m-%d')}' < periodFrom and periodFrom < '{filt.end.strftime('%Y-%m-%d')}' "


physFlowTableName = 'physical_flow'


class EntsogSQLite(EntsogDataManager):
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

        if self.use_pg:
            self.checkDoubleReporting = "isdoublereporting is not TRUE"
        else:
            self.checkDoubleReporting = "not isdoublereporting"

    def groupTime(self, groupby, column):
        if self.use_pg:
            return f"to_char({column}::timestamp, '{ftime_pg[groupby]}')" # PostgreSQL
        else:
            return f'strftime("{ftime_sqlite[groupby]}", "{column}")' # SQLite
        

    def connectionpoints(self):
        selectString = 'tpMapX as lat, tpMapY as long, pointkey, pointlabel'

        with self.db_accessor() as conn:
            zones = pd.read_sql_query(
                f'select {selectString} from connectionpoints', conn)
        return zones

    def interconnections(self):
        '''
        interconnections which are in one of the balancingZones
        to be determined whats useful here (coming from, to or both)
        '''
        selectString = 'pointTpMapY as lat, pointTpMapX as lon, fromdirectionkey, '
        selectString += 'pointkey, pointlabel, fromOperatorKey, fromoperatorlabel, fromcountrykey, fromBzKey, frombzlabel, '
        selectString += 'toCountryKey, toOperatorKey,tooperatorlabel, toPointKey, topointlabel, toBzKey,toBzLabel'

        with self.db_accessor() as conn:
            interconnections = pd.read_sql_query(
                f'select {selectString} from Interconnections', conn)
        return interconnections

    def balancingzones(self):
        """also known as bidding zones"""
        selectString = 'tpMapY as lat, tpMapX as lon, bzLabel'

        with self.db_accessor() as conn:
            zones = pd.read_sql_query(
                f'select {selectString} from balancingzones', conn)
        return zones

    def operators(self, country: str = '', operatorType: str = ''):
        '''
        returns operators which have an interconnection in one of the balancingZones
        '''
        if operatorType != '' and country != '':
            whereString = f"where operatorTypeLabel='{operatorType}' and operatorCountryKey='{country}'"
        elif country != '':
            whereString = f"where operatorCountryKey='{country}'"
        elif operatorType != '':
            whereString = f'where operatorTypeLabel="{operatorType}"'
        else:
            whereString = ''

        selectString = 'operatorKey, operatorLabel, operatorCountryKey, operatorTypeLabel'

        with self.db_accessor() as conn:
            operators = pd.read_sql_query(
                f'select {selectString} from operators {whereString}', conn)
        return operators

    def operatorpointdirections(self):
        selectString = 'pointkey, pointlabel, operatorLabel, directionkey, '
        selectString += 'tpTsoItemLabel, tSOBalancingZone, tSOCountry, pipeinpipewithtsokey, isdoublereporting,'
        selectString += 'adjacentcountry, connectedOperators, adjacentOperatorKey, adjacentzones'

        with self.db_accessor() as conn:
            opd = pd.read_sql_query(
                f'select {selectString} from operatorpointdirections', conn)
        return opd

    def operationaldata(self, operatorKeys: List[str], filt: Filter, group_by: List[str] = ['directionkey'], table=physFlowTableName):
        whereString = timeFilter(filt)
        inJoinString = "','".join(operatorKeys)
        inString = f"('{inJoinString}')"
        whereString += f'and t.operatorkey in {inString} and {self.checkDoubleReporting}'
        joinString = ' left join (select distinct pointkey, isdoublereporting, operatorKey, pipeinpipewithtsokey from operatorpointdirections) opd on t.pointkey = opd.pointkey and t.operatorkey = opd.operatorKey'

        if table == physFlowTableName:
            whereString += f' and {checkPipeInPipe}'
        group_by = ', '.join(list(map(lambda x: 't.'+x, group_by)))
        selectString = f'{self.groupTime(filt.groupby, "periodfrom")} as time, '
        selectString += f'{group_by}, sum(value) as value'
        
        groupString = f'{self.groupTime(filt.groupby, "periodfrom")}, {group_by}'

        with self.db_accessor() as conn:
            query = f'select {selectString} from {table} t {joinString} where {whereString} group by {groupString}'
            flow = pd.read_sql_query(query, conn, index_col='time')
        return flow

    def operationaldataByPoints(self, points: List[str], filt: Filter, group_by: List[str] = ['directionkey'], table=physFlowTableName):
        whereString = timeFilter(filt)
        inJoinString = "','".join(points)
        inString = f"('{inJoinString}')"
        whereString += f'and pointkey in {inString}'
        selectString = f'{self.groupTime(filt.groupby, "periodfrom")} as time, '
        selectString += 'pointkey, pointlabel, operatorkey, operatorlabel, '
        selectString += 'directionkey, sum(value) as value, indicator, pipeinpipewithtsokey'
        joinString = ' left join (select distinct pointkey as pk, isdoublereporting, operatorKey as ok, pipeinpipewithtsokey from operatorpointdirections) opd on t.pointkey = opd.pk and t.operatorkey = opd.ok'

        group_by = ', '.join(group_by)
        groupString = f'{self.groupTime(filt.groupby, "periodfrom")}, {group_by}, pointkey, pointlabel, operatorkey, operatorlabel, indicator, pipeinpipewithtsokey'

        with self.db_accessor() as conn:
            query = f'select {selectString} from {table} t {joinString} where {whereString} group by {groupString}'
            flow = pd.read_sql_query(query, conn, index_col='time')
        return flow

    def operatorsByBZ(self, bz: str):
        with self.db_accessor() as conn:
            query = f"select distinct fromOperatorKey from Interconnections where frombzlabel='{bz}'"
            operatorKeys = pd.read_sql_query(query, conn).dropna()[
                'fromoperatorkey'].unique()
        return operatorKeys

    def bilanz(self, operatorKeys: List[str], filt: Filter, table=physFlowTableName):
        inJoinString = "','".join(operatorKeys)
        inString = f"('{inJoinString}')"

        whereString = timeFilter(filt)
        whereString += f' and o.operatorKey in {inString} and {self.checkDoubleReporting}'

        selectString = f'{self.groupTime(filt.groupby, "periodfrom")} as time, '
        # TODO if connectionpoints would not have missing data, remove this hack
        # this is using that the pointkeys first 3 chars are generelly indicating
        # the infrastructureKey
        selectString += 'coalesce(c.infrastructureKey, substr(o.pointkey,0,4)) as infra, directionkey, sum(value) as value'
        groupString = f'{self.groupTime(filt.groupby, "periodfrom")}, directionkey, infra'
        joinString = ' left join (select distinct pointkey, isdoublereporting, operatorKey, pipeinpipewithtsokey from operatorpointdirections) opd on o.pointkey = opd.pointkey and o.operatorKey = opd.operatorKey'
        if table == physFlowTableName:
            whereString += f' and {checkPipeInPipe}'

        with self.db_accessor() as conn:
            query = f'select {selectString} from {table} o {joinString} left join connectionpoints c on o.pointkey=c.pointkey where {whereString} group by {groupString}'
            bil = pd.read_sql_query(query, conn, index_col='time')
        bilanz = bil.pivot(columns=['infra', 'directionkey'])
        bilanz.columns = bilanz.columns.droplevel(None)
        return self._diffHelper(bilanz)

    def _diffHelper(self, df):
        '''
        gets difference for each pair of entry and exit direction index column
        '''
        l = []
        p = pd.DataFrame()
        df = df.fillna(value=0)
        for col in df.columns:
            if col[0] not in l:
                for col2 in df.columns:
                    if str(col[0]) == str(col2[0]) and col != col2:
                        # same category
                        l.append(str(col[0]))
                        if col[1] == 'entry':
                            p[str(col[0])] = df[col]-df[col2]
                        else:  # entry - exit
                            p[str(col[0])] = df[col2]-df[col]

                if str(col[0]) not in l:
                    if col[1] == 'entry':
                        p[str(col[0])] = df[col]
                    else:
                        p[str(col[0])] = -df[col]
        return p

    def crossborder(self, operatorKeys: List[str], filt: Filter, group_by: List[str] = ['t.directionkey', 'opd.adjacentcountry'], table=physFlowTableName):
        whereString = timeFilter(filt)
        inJoinString = "','".join(operatorKeys)
        inString = f"('{inJoinString}')"
        whereString += f'and t.operatorkey in {inString} and {self.checkDoubleReporting}'

        joinString = ' left join (select distinct pointkey, isdoublereporting, operatorKey, pipeinpipewithtsokey, adjacentzones, adjacentcountry from operatorpointdirections) opd on t.pointkey = opd.pointkey and t.operatorkey = opd.operatorKey'
        if table == physFlowTableName:
            whereString += f' and {checkPipeInPipe}'
        group_by = ', '.join(list(map(lambda x: ''+x, group_by)))

        selectString = f'{self.groupTime(filt.groupby, "periodfrom")} as time, '
        selectString += f'{group_by}, coalesce(opd.adjacentzones, substr(t.pointkey,0,4)) as adjacentzones, sum(value) as value'
        groupString = f'{self.groupTime(filt.groupby, "periodfrom")}, coalesce(opd.adjacentzones, substr(t.pointkey,0,4)), {group_by}'

        with self.db_accessor() as conn:
            query = f'select {selectString} from {table} t {joinString} where {whereString} group by {groupString}'
            flow = pd.read_sql_query(query, conn, index_col='time')

        flow['name'] = flow['adjacentcountry'].apply(lambda x: str(
            x) if x else '-')+':'+flow['adjacentzones'].apply(lambda x: str(x) if x else '-')
        del flow['adjacentcountry']
        del flow['adjacentzones']

        pivoted = flow.pivot(columns=['name', 'directionkey'], values='value')
        return self._diffHelper(pivoted)


if __name__ == "__main__":

    entsog = EntsogSQLite('data/entsog.db')
    operators = entsog.operators()

    start = datetime(2018, 7, 1)
    end = datetime(2018, 7, 22)
    group = 'hour'
    filt = Filter(start, end, group)
    balzones = entsog.balancingzones()
    intercon = entsog.interconnections()
    cpp = entsog.connectionpoints()
    #gen = generation.melt(var_name='kind', value_name='value',ignore_index=False)
    operatorKeys = ['DE-TSO-0004', 'DE-TSO-0007', 'DE-TSO-0005', 'DE-TSO-0006']

    phy = entsog.operationaldata(operatorKeys, filt, group_by=['directionkey'])
    piv = phy.pivot(columns=['operatorkey', 'directionkey'], values='value')
    piv.plot()

    point = entsog.operationaldataByPoints(
        ['ITP-00043', 'ITP-00111'], Filter(start, end, group), ['pointkey', 'directionkey'])
    point['point'] = point['pointlabel']+' ' + \
        point['directionkey']+' '+point['indicator']
    point['value'] = point['value']/1e6
    piv2 = point.pivot(columns=['point'], values='value')
    piv2.plot()

    end = datetime(2018, 7, 2)
    filt = Filter(start, end, 'hour')
    operatorKeys = entsog.operatorsByBZ('Italy')

    operatorKeys = entsog.operatorsByBZ('Portugal')
    bil = entsog.bilanz(operatorKeys, filt)
    bil.plot(rot=45)

    operatorKeys = entsog.operatorsByBZ('GASPOOL')
    c = entsog.crossborder(operatorKeys, filt)
    c.plot(rot=45)

    # 55 mrd Nm^3 sind 60 GWh
    # 55 000 000 000 = 60 000 000 000 Wh pro Jahr
    # taeglich circa 160 000 000 Wh also 160 MWh
    # tatsaechlich 1 131 141 436 kWh pro Tag?? laut entsog
