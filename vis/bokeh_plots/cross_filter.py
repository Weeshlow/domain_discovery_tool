from __future__ import division
from collections import Counter, defaultdict
from itertools import chain, combinations
import os
import pytz
from dateutil.tz import tzlocal

from bokeh.palettes import Spectral4
from bokeh.embed import components
from bokeh.io import VBox
from bokeh.models.widgets import DataTable, TableColumn
from bokeh.models import (ColumnDataSource, CustomJS, HoverTool, Range1d, Plot,
    LinearAxis, Rect, FactorRange, CategoricalAxis, DatetimeAxis, Line,
    DataRange1d, MultiLine, Text, Circle, WheelZoomTool, ResetTool, PanTool,
    DatetimeTickFormatter, DatetimeTicker)
import networkx as nx
import pandas as pd
from urlparse import urlparse

from .utils import (DATETIME_FORMAT, PLOT_FORMATS, AXIS_FORMATS, LINE_FORMATS,
    FONT_PROPS_SM, RED, BLUE, empty_plot_on_empty_df)

NX_COLOR = Spectral4[1]

MIN_BORDER=10
MAX_CIRCLE_SIZE = 0.1
MIN_CIRCLE_SIZE = 0.01
MAX_LINE_SIZE = 10
MIN_LINE_SIZE = 1

# refers to method in js/cross_filter.js
JS_CODE = "crossFilterUpdate()"

def normalize(seq, max_val, min_val):
    s = seq / seq.max() * max_val
    s[s < min_val] = min_val
    return s

def parse_es_response(response):
    df = pd.DataFrame(response, columns=['query', 'retrieved', 'url', 'tag'])
    df['retrieved'] = pd.DatetimeIndex(df.retrieved.apply(lambda x: x[0]), tz=pytz.timezone('UTC'))
    df['url'] = df.url.apply(lambda x: x[0])
    df['hostname'] = [urlparse(x).hostname.lstrip('www.') for x in df.url]
    df['tld'] = [x[x.rfind('.'):] for x in df.hostname]
    df['tag'] = df.tag.apply(lambda x: ["Untagged"] if isinstance(x, float) else x)

    df = duplicate_multi_rows(df, 'query')
    df = duplicate_multi_rows(df, 'tag')

    return df.set_index('retrieved').sort_index()

def calculate_graph_coords(df, groupby_column):
    df2 = df.groupby(groupby_column).count().sort_index()

    graph = nx.Graph()
    graph.add_nodes_from(df2.index)
    graph_coords = nx.circular_layout(graph, center=(0,0))

    return pd.concat([df2, pd.DataFrame(graph_coords, index=["x", "y"]).T], axis=1)

def calculate_query_correlation(df, groupby_column):
    key_combos = combinations(df[groupby_column].unique(), r=2)

    correlation = dict()

    for i in key_combos:
        k0 = df[df[groupby_column].isin([i[0]])]['url']
        k1 = df[df[groupby_column].isin([i[1]])]['url']
        num_shared_pages = len(set(k0).intersection(k1))
        if num_shared_pages > 0:
            correlation[i] = num_shared_pages

    if len(correlation) == 0 or max(correlation.values()) == 0:
        return correlation

    max_corr = max(correlation.values())
    return {k: v/max_corr for k,v in correlation.items()}

def duplicate_multi_rows(df, column_name):
    """
    Makes copy of row for each tag in multitag
    """
    return pd.DataFrame([row.copy().set_value(column_name, i)
                        for _, row in df.iterrows()
                        for i in row[column_name]])

@empty_plot_on_empty_df
def most_common_url_bar(df, plot_width=400, plot_height=250, top_n=None):
    bars = df[['hostname','url']].groupby('hostname').count().sort_values('url', ascending=False)
    bars['y'] = bars.url / 2.

    if top_n:
        bars = bars.nlargest(top_n, 'url')

    source = ColumnDataSource(bars)

    plot = Plot(title="Most Common Sites",
                plot_width=plot_width, plot_height=plot_height,
                x_range=Range1d(0,bars.url.max()),
                y_range=FactorRange(factors=bars.index.tolist()[::-1]),
                **PLOT_FORMATS)
    plot.add_glyph(
        source,
        Rect(x='y', y='hostname', height=0.8, width='url', fill_color=BLUE,
            fill_alpha=0.6, line_color=None)
    )
    plot.add_layout(LinearAxis(axis_label="Occurences", **AXIS_FORMATS), 'below')
    plot.add_layout(CategoricalAxis(**AXIS_FORMATS), 'left')

    return plot

@empty_plot_on_empty_df
def site_tld_bar(df, plot_width=325, plot_height=200):
    bars = df[['tld','url']].groupby('tld').count().sort_values('url', ascending=False)
    bars['y'] = bars.url / 2.

    source = ColumnDataSource(bars)

    plot = Plot(title="Most Common Top-level Domains",
                plot_width=plot_width, plot_height=plot_height,
                x_range=Range1d(0,bars.url.max()),
                y_range=FactorRange(factors=bars.index.tolist()[::-1]),
                **PLOT_FORMATS)
    plot.add_glyph(
        source,
        Rect(x='y', y='tld', height=0.8, width='url', fill_color=BLUE,
            fill_alpha=0.6, line_color=None)
    )
    plot.add_layout(LinearAxis(axis_label="Occurences", **AXIS_FORMATS), 'below')
    plot.add_layout(CategoricalAxis(**AXIS_FORMATS), 'left')

    return plot

@empty_plot_on_empty_df
def pages_queried_timeseries(df, plot_width=600, plot_height=200, rule='1T'):
    ts = df[['url']].resample(rule, how='count').cumsum()
    ts.index = ts.index.tz_convert(tzlocal())
    #Bokeh=0.10.0 misencodes timestamps, so we have to shift by
    ts.index = ts.index.shift(ts.index[0].utcoffset().total_seconds(), freq="S")
    ts = pd.concat([ts[:1], ts]) # prepend 0-value for Line chart compat
    ts.iloc[0]['url'] = 0

    formatter = DatetimeTickFormatter(formats=DATETIME_FORMAT)
    ticker = DatetimeTicker(desired_num_ticks=3)

    source = ColumnDataSource(ts)

    plot = Plot(plot_width=plot_width, plot_height=plot_height,
                x_range=DataRange1d(range_padding=0.1),
                y_range=DataRange1d(start=0),
                **PLOT_FORMATS)
    plot.add_glyph(
        source,
        Line(x='retrieved', y='url', **LINE_FORMATS)
    )
    plot.add_layout(
        DatetimeAxis(axis_label="Date Retrieved", formatter=formatter,
                     ticker=ticker, **AXIS_FORMATS),
        'below')
    plot.add_layout(LinearAxis(axis_label="Total Pages", **AXIS_FORMATS), 'left')

    return plot

@empty_plot_on_empty_df
def queries_plot(df, plot_width=400, plot_height=400):
    graph_df = calculate_graph_coords(df, 'query')
    graph_df["radius"] = normalize(graph_df.url, MAX_CIRCLE_SIZE, MIN_CIRCLE_SIZE)
    graph_df["label"] = graph_df.index.astype(str) + ' (' + graph_df.url.astype(str) + ')'
    graph_df["text_y"] = graph_df.y - graph_df.radius - 0.100 ## fudge factor

    source = ColumnDataSource(graph_df)

    line_coords = calculate_query_correlation(df, 'query')

    # Create connection lines.
    lines = defaultdict(list)
    for k, v in line_coords.items():
        lines['xs'].append([graph_df.loc[k[0]]['x'], graph_df.loc[k[1]]['x']])
        lines['ys'].append([graph_df.loc[k[0]]['y'], graph_df.loc[k[1]]['y']])
        lines['line_width'].append(v*MAX_LINE_SIZE)

    line_source = ColumnDataSource(lines)

    if len(df) == 1:
        x_range = Range1d(0.2, 1.8)
        y_range = Range1d(-1.25, 1.25)
    else:
        x_range = Range1d(-1.25, 1.25)
        y_range = Range1d(-1.25, 1.25)

    NETWORK_FORMATS = PLOT_FORMATS.copy()
    NETWORK_FORMATS['toolbar_location'] = 'right'

    plot = Plot(title="Queries Network",
                plot_width=plot_width, plot_height=plot_height,
                x_range=x_range, y_range=y_range,
                **NETWORK_FORMATS)
    plot.add_glyph(
        line_source,
        MultiLine(xs="xs", ys="ys", line_width="line_width", line_color=RED)
    )
    plot.add_glyph(
        source,
        Circle(x="x", y="y", radius="radius", fill_color=RED, line_color=RED)
    )
    plot.add_glyph(
        source,
        Text(x="x", y="text_y", text="label", text_baseline='middle',
            text_align="center", text_alpha=0.9, **FONT_PROPS_SM)
    )
    plot.add_tools(WheelZoomTool(), ResetTool(), PanTool())

    return plot

@empty_plot_on_empty_df
def tags_plot(df, plot_width=400, plot_height=400):
    graph_df = calculate_graph_coords(df, 'tag')
    graph_df["radius"] = normalize(graph_df.url, MAX_CIRCLE_SIZE, MIN_CIRCLE_SIZE)
    graph_df["label"] = graph_df.index.astype(str) + ' (' + graph_df.url.astype(str) + ')'
    graph_df["text_y"] = graph_df.y - graph_df.radius - 0.100 ## fudge factor

    source = ColumnDataSource(graph_df)

    line_coords = calculate_query_correlation(df, 'tag')

    # Create connection lines.
    lines = defaultdict(list)
    for k, v in line_coords.items():
        lines['xs'].append([graph_df.loc[k[0]]['x'], graph_df.loc[k[1]]['x']])
        lines['ys'].append([graph_df.loc[k[0]]['y'], graph_df.loc[k[1]]['y']])
        lines['line_width'].append(v*MAX_LINE_SIZE)

    line_source = ColumnDataSource(lines)

    if len(df) == 1:
        x_range = Range1d(0.2, 1.8)
        y_range = Range1d(-1.25, 1.25)
    else:
        x_range = Range1d(-1.25, 1.25)
        y_range = Range1d(-1.25, 1.25)

    NETWORK_FORMATS = PLOT_FORMATS.copy()
    NETWORK_FORMATS['toolbar_location'] = 'right'

    plot = Plot(title="Tags Network",
                plot_width=plot_width, plot_height=plot_height,
                x_range=x_range, y_range=y_range,
                **NETWORK_FORMATS)
    plot.add_glyph(
        line_source,
        MultiLine(xs="xs", ys="ys", line_width="line_width", line_color=Spectral4[1])
    )
    plot.add_glyph(
        source,
        Circle(x="x", y="y", radius="radius", fill_color=Spectral4[1], line_color=Spectral4[1])
    )
    plot.add_glyph(
        source,
        Text(x="x", y="text_y", text="label", text_baseline='middle',
            text_align="center", text_alpha=0.9, **FONT_PROPS_SM)
    )
    plot.add_tools(WheelZoomTool(), ResetTool(), PanTool())

    return plot

def most_common_url_table(df):
    source = ColumnDataSource(df.groupby('hostname')
                                .count()
                                .sort_values('url',ascending=False)
                                .reset_index(),
                              callback=CustomJS(code=JS_CODE))
    columns = [TableColumn(field="hostname", title="Site Name"),
               TableColumn(field="url", title="Count")]
    t = DataTable(source=source, columns=columns,
                  row_headers=False, width=400, height=250)
    return VBox(t)

def site_tld_table(df):
    source = ColumnDataSource(df.groupby('tld')
                                .count()
                                .sort_values('url', ascending=False)
                                .reset_index(),
                              callback=CustomJS(code=JS_CODE))
    columns = [TableColumn(field="tld", title="Ending"),
               TableColumn(field="url", title="Count")]
    t = DataTable(source=source, columns=columns,
                  row_headers=False, width=400, height=200)
    return VBox(t)

def tags_table(df):
    source = ColumnDataSource(df.groupby('tag')
                                .count()
                                .sort_values('url', ascending=False)
                                .reset_index(),
                              callback=CustomJS(code=JS_CODE))

    columns = [TableColumn(field='tag', title="Tags"),
               TableColumn(field='url', title="Count"),
               ]

    t = DataTable(source=source, columns=columns, row_headers=False,
                  width=400, height=400)
    return VBox(t)

def queries_table(df):
    source = ColumnDataSource(df.groupby(by='query')
                                .count()
                                .sort_values('url', ascending=False)
                                .reset_index(),
                              callback=CustomJS(code=JS_CODE))

    columns = [TableColumn(field="query", title="Query"),
               TableColumn(field="url", title="Pages")
               ]

    t = DataTable(source=source, columns=columns, row_headers=False,
                  width=400, height=400)
    return VBox(t)

def create_plot_components(df, **kwargs):
    hostnames = most_common_url_bar(df, **kwargs)
    tlds = site_tld_bar(df)
    ts = pages_queried_timeseries(df)
    queries = queries_plot(df)
    tags = tags_plot(df)
    return components(dict(hostnames=hostnames, tlds=tlds, ts=ts, queries=queries, tags=tags))

def create_table_components(df):
    urls = most_common_url_table(df)
    tlds = site_tld_table(df)
    tags = tags_table(df)
    queries = queries_table(df)
    return components(dict(urls=urls, tlds=tlds, tags=tags, queries=queries))
