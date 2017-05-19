#!/usr/bin/python
# -*- coding: utf-8 -*-

import pandas as pd

GOOD_SYMBOLS = [
    u'ё', u' ', u'+', u'.'
]


def idiotic_unicode(text):
    '''
    Return string reencoded with strange unicode, that is used on http://mos-sud.ru

    Only last names are supported for now
    '''
    text = text.lower().replace(u' ', u'+')

    if any(not l in GOOD_SYMBOLS and (l < u'а' or l > u'я') for l in text):
        raise ValueError('Text contains wrong symbols')

    chars = [224 + (ord(c) - ord(u'а')) if c not in GOOD_SYMBOLS else c for c in text]
    encoded = "".join("%%%x" % c if c not in GOOD_SYMBOLS else c for c in chars).upper()
    return encoded


def make_url(court='mos-sud', court_num='110', defendant=None, plaintiff=u'жилсервис'):
    if court == 'mos-sud':
        url = u'http://mos-sud.ru/ms/{court_num}/consideration/cs/?year=2017&sf0=&sf1=&sf2=&sf2_d=&sf3=&sf4=&sf13={plaintiff}&sf14={defendant}'
        url = url.format(
            defendant=idiotic_unicode(defendant) if defendant else '',
            plaintiff=idiotic_unicode(plaintiff) if plaintiff else '',
            court_num=str(court_num),
        )
        return url
    elif court == 'mos-sud-claim':
        url = u'http://mos-sud.ru/ms/{court_num}/consideration/pd/?sf0=&sf1=&sf2=&sf2_d=&sf3=&sf4=&sf6=&sf9={plaintiff}&sf10={defendant}'
        url = url.format(
            defendant=idiotic_unicode(defendant) if defendant else '',
            plaintiff=idiotic_unicode(plaintiff) if plaintiff else '',
            court_num=str(court_num),
        )
        return url
    else:
        raise NotImplementedError('This court is not supported')


def get_magistrate_court(court='mos-sud', court_num=110, defendant=None, plaintiff=u'жилсервис'):
    try:
        url = make_url(court=court, court_num=court_num, defendant=defendant, plaintiff=plaintiff)
        print url
        df = pd.read_html(url, attrs={'class': 'decision_table'}, header=0)[0]
        return df
    except ValueError, e:
        if str(e) == 'No tables found':
            return None
        else:
            raise
