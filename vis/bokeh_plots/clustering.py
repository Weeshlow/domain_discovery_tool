import json
from functools import partial

from bokeh.io import vform
from bokeh.plotting import figure, show, output_file, save
from bokeh.plotting import ColumnDataSource
from bokeh.models import HoverTool, Circle, CustomJS, LassoSelectTool
from bokeh.models.widgets import RadioButtonGroup, Button
from bokeh.embed import components


FIGURE_WIDTH=1000
FIGURE_HEIGHT=375
NEUTRAL_COLOR = "#7F7F7F"
POSITIVE_COLOR = "blue"
NEGATIVE_COLOR = "crimson"
CIRCLE_SIZE=10


def colormap(key):
    color = {
        "Irrelevant": NEGATIVE_COLOR,
        "Relevant": POSITIVE_COLOR,
    }.get(key, NEUTRAL_COLOR)
    return color


def selection_plot(response):
    # Let's move these into a settings file somewhere?
    # height/width could potentially be driven by the request?


    # Include color data in the ColumnDataSource to allow for changing the color on
    # the client side.
    urls = [x[0] for x in response["pages"]]
    xdata = [x[1] for x in response["pages"]]
    ydata = [x[2] for x in response["pages"]]
    tags = [x[3] for x in response["pages"]]
    color = [colormap(x[0]) if x else colormap(None) for x in tags]

    source = ColumnDataSource(
        data=dict(
            x=xdata,
            y=ydata,
            urls=urls,
            tags=tags,
            color=color,
        )
    )
    # Callback code for CDS.
    source.callback = CustomJS(code="""
        var inds = cb_obj.get('selected')["1d"].indices;
        var data = cb_obj.get('data');
        BokehPlots.showPages(inds);
    """)


    # Create the figure with FIGURE_WIDTH and FIGURE_HEIGHT
    p = figure(tools="hover", width=FIGURE_WIDTH,
            toolbar_location=None, responsive=True)

    # Ensure that the lasso only selects with mouseup, not mousemove.
    p.add_tools(LassoSelectTool(select_every_mousemove=False))

    # These turn off the x/y axis ticks
    p.axis.visible = None

    # These turn the major grid off
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    # Plot non-selected circles with a particular style using CIRCLE_SIZE and
    # 'color' list
    p.circle("x", "y", size=13, line_width=2, line_alpha=1,
            line_color=None, fill_alpha=1, color='color', source=source,
            name="urls")
    nonselected_circle = Circle(fill_alpha=0.1, line_alpha=0.1, fill_color='color',
            line_color='color')
    renderer = p.select(name="urls")
    renderer.nonselection_glyph = nonselected_circle


    # Create buttons and their callbacks, use button_code string for callbacks.
    button_code = """
        event.preventDefault();
        var inds = source.get('selected')["1d"].indices;
        var data = source.get('data');
        var selected = [];
        tag = "%s";
        for(var i = 0; i < inds.length; i++){
            selected.push({
                x: data.x[inds[i]],
                y: data.y[inds[i]],
                url: data.urls[inds[i]],
                tags: data.tags[inds[i]],
                selected: true,
                possible: false,
            });
            data["color"][inds[i]] = "%s";
        }
        BokehPlots.updateTags(selected, tag, inds);
        source.trigger("change");
    """

    # Supply color with print formatting.
    button1 = Button(label="Relevant", type="success")
    button1.callback = CustomJS(args=dict(source=source),
            code=button_code % ("Relevant", POSITIVE_COLOR))

    button2 = Button(label="Irrelevant", type="success")
    button2.callback = CustomJS(args=dict(source=source),
            code=button_code % ("Irrelevant", NEGATIVE_COLOR))

    button3 = Button(label="Neutral", type="success")
    button3.callback = CustomJS(args=dict(source=source),
            code=button_code % ("Neutral", NEUTRAL_COLOR))


    # Adjust what attributes are displayed by the HoverTool
    hover = p.select(dict(type=HoverTool))
    hover.tooltips = [
        ("urls", "@urls"),
    ]
    layout = vform(p, button1, button2, button3)

    # Combine script and div into a single string.
    plot_code = components(layout)
    return plot_code[0] + plot_code[1]


def empty_plot():
    p = figure(tools="hover", height=FIGURE_HEIGHT,
            toolbar_location=None, responsive=True)

    # Ensure that the lasso only selects with mouseup, not mousemove.
    p.add_tools(LassoSelectTool(select_every_mousemove=False))

    # These turn off the x/y axis ticks
    p.axis.visible = None

    # These turn the major grid off
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    # Plot non-selected circles with a particular style using CIRCLE_SIZE and
    # 'color' list
    button1 = Button(label="Relevant", type="success")
    button2 = Button(label="Irrelevant", type="success")
    button3 = Button(label="Neutral", type="success")
    layout = vform(p, button1, button2, button3)

    # Combine script and div into a single string.
    plot_code = components(layout)
    return plot_code[0] + plot_code[1]