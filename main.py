from PyQt4 import QtCore, QtGui, QtWebKit, QtNetwork, QtSql
from obspy import read_inventory, read_events, UTCDateTime, Stream, read
import functools
import os
import shutil
import itertools
import re

import pandas as pd
import numpy as np
from query_input_yes_no import query_yes_no
import sys
from station_tree_widget import StationTreeWidget
from select_stacomp_dialog import Ui_SelectDialog

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, and_, or_
from sqlalchemy.orm import sessionmaker

STATION_VIEW_ITEM_TYPES = {
    "NETWORK": 0,
    "STATION": 1}

# Set up the sql waveform databases
Base = declarative_base()


class Waveforms(Base):
    __tablename__ = 'waveforms'
    # Here we define columns for the table
    starttime = Column(Integer)
    endtime = Column(Integer)
    orig_network = Column(String(2), nullable=False)
    new_network = Column(String(2), nullable=False)
    station = Column(String(5), nullable=False)
    component = Column(String(3), nullable=False)
    location = Column(String(2), nullable=False)
    waveform_basename = Column(String(40), nullable=False, primary_key=True)
    path = Column(String(100), nullable=False)
    ASDF_tag = Column(String(100), nullable=False)


class selectionDialog(QtGui.QDialog):
    '''
    Select all functionality is modified from Brendan Abel & dbc from their
    stackoverflow communication Feb 24th 2016:
    http://stackoverflow.com/questions/35611199/creating-a-toggling-check-all-checkbox-for-a-listview
    '''
    def __init__(self, parent=None, sta_list=None):
        QtGui.QDialog.__init__(self, parent)
        self.selui = Ui_SelectDialog()
        self.selui.setupUi(self)

        # Set all check box to checked
        self.selui.check_all.setChecked(True)
        self.selui.check_all.clicked.connect(self.selectAllCheckChanged)

        self.model = QtGui.QStandardItemModel(self.selui.StaListView)

        self.sta_list = sta_list
        for sta in self.sta_list:
            item = QtGui.QStandardItem(sta)
            item.setCheckable(True)

            self.model.appendRow(item)

        self.selui.StaListView.setModel(self.model)
        self.selui.StaListView.clicked.connect(self.listviewCheckChanged)

    def selectAllCheckChanged(self):
        ''' updates the listview based on select all checkbox '''
        model = self.selui.StaListView.model()
        for index in range(model.rowCount()):
            item = model.item(index)
            if item.isCheckable():
                if self.selui.check_all.isChecked():
                    item.setCheckState(QtCore.Qt.Checked)
                else:
                    item.setCheckState(QtCore.Qt.Unchecked)

    def listviewCheckChanged(self):
        ''' updates the select all checkbox based on the listview '''
        model = self.selui.StaListView.model()
        items = [model.item(index) for index in range(model.rowCount())]

        if all(item.checkState() == QtCore.Qt.Checked for item in items):
            self.selui.check_all.setTristate(False)
            self.selui.check_all.setCheckState(QtCore.Qt.Checked)
        elif any(item.checkState() == QtCore.Qt.Checked for item in items):
            self.selui.check_all.setTristate(True)
            self.selui.check_all.setCheckState(QtCore.Qt.PartiallyChecked)
        else:
            self.selui.check_all.setTristate(False)
            self.selui.check_all.setCheckState(QtCore.Qt.Unchecked)

    def getSelected(self):
        select_stations = []
        i = 0
        while self.model.item(i):
            if self.model.item(i).checkState():
                select_stations.append(str(self.model.item(i).text()))
            i += 1

        # Return Selected stations and checked components
        return(select_stations, [self.selui.zcomp.isChecked(),
               self.selui.ncomp.isChecked(),
               self.selui.ecomp.isChecked()])


class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """

    def __init__(self, data, cat_nm=None, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = np.array(data.values)
        self._cols = data.columns
        self.r, self.c = np.shape(self._data)

        self.cat_nm = cat_nm

        # Column headers for tables
        self.cat_col_header = ['Event ID', 'Time (UTC Timestamp)', 'Lat (dd)', 'Lon  (dd)',
                               'Depth (km)', 'Mag', 'Time (UTC)', 'Julian Day']

    def rowCount(self, parent=None):
        return self.r

    def columnCount(self, parent=None):
        return self.c

    def data(self, index, role=QtCore.Qt.DisplayRole):

        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                return self._data[index.row(), index.column()]
        return None

    def headerData(self, p_int, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                if not self.cat_nm == None:
                    return self.cat_col_header[p_int]
                elif not self.pick_nm == None:
                    return self.pick_col_header[p_int]
            elif orientation == QtCore.Qt.Vertical:
                return p_int
        return None


class TableDialog(QtGui.QDialog):
    """
    Class to create a separate child window to display the event catalogue and picks
    """

    def __init__(self, parent=None, cat_df=None):
        super(TableDialog, self).__init__(parent)

        self.cat_df = cat_df

        self.initUI()

    def initUI(self):
        self.layout = QtGui.QVBoxLayout(self)

        self.cat_event_table_view = QtGui.QTableView()

        self.cat_event_table_view.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)

        self.layout.addWidget(self.cat_event_table_view)

        self.setLayout(self.layout)

        # Populate the tables using the custom Pandas table class
        self.cat_model = PandasModel(self.cat_df, cat_nm=True)

        self.cat_event_table_view.setModel(self.cat_model)

        self.setWindowTitle('Tables')
        self.show()


class MainWindow(QtGui.QWidget):
    """
    Main Window for metadata map GUI
    """

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi()
        self.show()
        self.raise_()

    def setupUi(self):
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        buttons_hbox = QtGui.QHBoxLayout()

        self.open_SQL_button = QtGui.QPushButton('Open SQL file for Network')
        openSQL = functools.partial(self.open_SQL_file)
        self.open_SQL_button.released.connect(openSQL)
        buttons_hbox.addWidget(self.open_SQL_button)

        self.open_cat_button = QtGui.QPushButton('Open Earthquake Catalogue')
        openCat = functools.partial(self.open_cat_file)
        self.open_cat_button.released.connect(openCat)
        buttons_hbox.addWidget(self.open_cat_button)

        self.open_xml_button = QtGui.QPushButton('Open StationXML')
        openXml = functools.partial(self.open_xml_file)
        self.open_xml_button.released.connect(openXml)
        buttons_hbox.addWidget(self.open_xml_button)

        vbox.addLayout(buttons_hbox)

        main_grid_lay = QtGui.QGridLayout()

        self.station_view = StationTreeWidget()
        self.station_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.station_view.setAnimated(False)
        self.station_view.setHeaderHidden(True)
        self.station_view.setObjectName("station_view")
        self.station_view.headerItem().setText(0, "1")
        self.station_view.itemClicked.connect(self.station_view_itemClicked)

        main_grid_lay.addWidget(self.station_view, 0, 0, 1, 1)

        # self.SQL_view = QtGui.QTableView()
        # self.SQL_view.setModel(QtSql.QSqlTableModel)
        # self.SQL_view.setWindowTitle("Waveforms SQLite")
        #
        # main_grid_lay.addWidget(self.SQL_view)

        view = self.view = QtWebKit.QWebView()
        cache = QtNetwork.QNetworkDiskCache()
        cache.setCacheDirectory("cache")
        view.page().networkAccessManager().setCache(cache)
        view.page().networkAccessManager()

        view.page().mainFrame().addToJavaScriptWindowObject("MainWindow", self)
        view.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        view.load(QtCore.QUrl('map.html'))
        view.loadFinished.connect(self.onLoadFinished)
        view.linkClicked.connect(QtGui.QDesktopServices.openUrl)

        main_grid_lay.addWidget(view, 0, 1, 1, 5)

        vbox.addLayout(main_grid_lay)

    def onLoadFinished(self):
        with open('map.js', 'r') as f:
            frame = self.view.page().mainFrame()
            frame.evaluateJavaScript(f.read())

    @QtCore.pyqtSlot(float, float, str, str, int)
    def onMap_marker_selected(self, lat, lng, event_id, df_id, row_index):
        self.table_view_highlight(self.tbl_view_dict[str(df_id)], row_index)

    @QtCore.pyqtSlot(int)
    def onMap_stn_marker_selected(self, station):
        self.station_view.setCurrentItem(self.station_view.topLevelItem(0))

    def changed_widget_focus(self):
        try:
            if not QtGui.QApplication.focusWidget() == self.graph_view:
                self.scatter_point_deselect()
        except AttributeError:
            pass

    def open_SQL_file(self):
        self.SQL_filename = str(QtGui.QFileDialog.getOpenFileName(
            parent=self, caption="Choose SQLite Database File",
            directory=os.path.expanduser("~"),
            filter="SQLite Files (*.db)"))
        if not self.SQL_filename:
            return

        print('')
        print("Initializing SQLite Database..")

        # Open and create the SQL file
        # Create an engine that stores data
        self.engine = create_engine('sqlite:////' + self.SQL_filename)

        # Initiate a session with the SQL database so that we can add data to it
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        print("SQLite Initializing Done!")

    def open_cat_file(self):
        self.cat_filename = str(QtGui.QFileDialog.getOpenFileName(
            parent=self, caption="Choose Earthquake Catalogue QuakeML File",
            directory=os.path.expanduser("~"),
            filter="XML Files (*.xml)"))
        if not self.cat_filename:
            return

        self.cat = read_events(self.cat_filename)

        # create empty data frame
        self.cat_df = pd.DataFrame(data=None, columns=['event_id', 'qtime', 'lat', 'lon', 'depth', 'mag'])

        # iterate through the events
        for _i, event in enumerate(self.cat):
            # Get quake origin info
            origin_info = event.preferred_origin() or event.origins[0]

            try:
                mag_info = event.preferred_magnitude() or event.magnitudes[0]
                magnitude = mag_info.mag
            except IndexError:
                # No magnitude for event
                magnitude = None

            self.cat_df.loc[_i] = [str(event.resource_id.id).split('=')[1], int(origin_info.time.timestamp),
                                   origin_info.latitude, origin_info.longitude,
                                   origin_info.depth/1000, magnitude]

        self.cat_df.reset_index(drop=True, inplace=True)

        print('------------')
        print(self.cat_df)
        self.build_tables()
        self.plot_events()

    def open_xml_file(self):
        self.stn_filename = str(QtGui.QFileDialog.getOpenFileName(
            parent=self, caption="Choose StationXML Metadata File",
            directory=os.path.expanduser("~"),
            filter="XML Files (*.xml)"))
        if not self.stn_filename:
            return

        self.inv = read_inventory(self.stn_filename)
        self.plot_inv()

        self.build_station_view_list()

    def build_station_view_list(self):
        self.station_view.clear()

        items = []

        item = QtGui.QTreeWidgetItem(
            [self.inv[0].code], type=STATION_VIEW_ITEM_TYPES["NETWORK"])

        # Add all children stations.
        self.station_list = []
        children = [] #pyqt QtreeWidget items

        for i, station in enumerate(self.inv[0]):
            self.station_list.append(str(station.code))
            children.append(
                QtGui.QTreeWidgetItem(
                    [station.code], type=STATION_VIEW_ITEM_TYPES["STATION"]))
        item.addChildren(children)

        items.append(item)

        self.station_view.insertTopLevelItems(0, items)

    def station_view_itemClicked(self, item):
        t = item.type()

        def get_station(item):
            station = item.text(0)
            if "." not in station:
                station = item.parent().text(0) + "." + station
            return station

        if t == STATION_VIEW_ITEM_TYPES["NETWORK"]:
            pass
        elif t == STATION_VIEW_ITEM_TYPES["STATION"]:
            station = get_station(item)


            # Highlight the station marker on the map
            js_call = "highlightStation('{station}');".format(station=station.split('.')[1])
            self.view.page().mainFrame().evaluateJavaScript(js_call)
        else:
            pass

    def tbl_view_popup(self):
        focus_widget = QtGui.QApplication.focusWidget()
        # get the selected row number
        row_number = focus_widget.selectionModel().selectedRows()[0].row()
        row_index = self.table_accessor[focus_widget][1][row_number]

        self.selected_row = self.cat_df.loc[row_index]

        self.rc_menu = QtGui.QMenu(self)
        self.rc_menu.addAction('Open Earthquake with SG2K', functools.partial(
            self.create_SG2K_initiate, self.selected_row['event_id'], self.selected_row))

        self.rc_menu.popup(QtGui.QCursor.pos())

    def build_tables(self):

        self.table_accessor = None

        dropped_cat_df = self.cat_df

        # make UTC string from earthquake cat and add julian day column
        def mk_cat_UTC_str(row):
            return (pd.Series([UTCDateTime(row['qtime']).ctime(), UTCDateTime(row['qtime']).julday]))

        dropped_cat_df[['Q_time_str', 'julday']] = dropped_cat_df.apply(mk_cat_UTC_str, axis=1)

        self.tbld = TableDialog(parent=self, cat_df=dropped_cat_df)

        self.tbld.cat_event_table_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tbld.cat_event_table_view.customContextMenuRequested.connect(self.tbl_view_popup)

        # Lookup Dictionary for table views
        self.tbl_view_dict = {"cat": self.tbld.cat_event_table_view}

        # Create a new table_accessor dictionary for this class
        self.table_accessor = {self.tbld.cat_event_table_view: [dropped_cat_df, range(0, len(dropped_cat_df))]}

        self.tbld.cat_event_table_view.clicked.connect(self.table_view_clicked)

        # If headers are clicked then sort
        self.tbld.cat_event_table_view.horizontalHeader().sectionClicked.connect(self.headerClicked)

    def headerClicked(self, logicalIndex):
        focus_widget = QtGui.QApplication.focusWidget()
        table_df = self.table_accessor[focus_widget][0]

        header = focus_widget.horizontalHeader()

        self.order = header.sortIndicatorOrder()
        table_df.sort_values(by=table_df.columns[logicalIndex],
                             ascending=self.order, inplace=True)

        self.table_accessor[focus_widget][1] = table_df.index.tolist()

        if focus_widget == self.tbld.cat_event_table_view:
            self.model = PandasModel(table_df, cat_nm=True)

        focus_widget.setModel(self.model)
        focus_widget.update()

    def table_view_clicked(self):
        focus_widget = QtGui.QApplication.focusWidget()
        row_number = focus_widget.selectionModel().selectedRows()[0].row()
        row_index = self.table_accessor[focus_widget][1][row_number]
        # Highlight/Select the current row in the table
        self.table_view_highlight(focus_widget, row_index)

    def table_view_highlight(self, focus_widget, row_index):

        if focus_widget == self.tbld.cat_event_table_view:
            self.selected_row = self.cat_df.loc[row_index]

            # Find the row_number of this index
            cat_row_number = self.table_accessor[focus_widget][1].index(row_index)
            focus_widget.selectRow(cat_row_number)

            # Highlight the marker on the map
            js_call = "highlightEvent('{event_id}');".format(event_id=self.selected_row['event_id'])
            self.view.page().mainFrame().evaluateJavaScript(js_call)

    def plot_events(self):
        # Plot the events
        for row_index, row in self.cat_df.iterrows():
            js_call = "addEvent('{event_id}', '{df_id}', {row_index}, " \
                      "{latitude}, {longitude}, '{a_color}', '{p_color}');" \
                .format(event_id=row['event_id'], df_id="cat", row_index=int(row_index), latitude=row['lat'],
                        longitude=row['lon'], a_color="Red",
                        p_color="#008000")
            self.view.page().mainFrame().evaluateJavaScript(js_call)

    def plot_inv(self):
        # plot the stations
        print(self.inv)
        for i, station in enumerate(self.inv[0]):
            js_call = "addStation('{station_id}', {latitude}, {longitude});" \
                .format(station_id=station.code, latitude=station.latitude,
                        longitude=station.longitude)
            self.view.page().mainFrame().evaluateJavaScript(js_call)

    def create_SG2K_initiate(self, event, quake_df):

        comp_list = ['__Z', '__N', '__E']

        # Launch the custom station/component selection dialog
        sel_dlg = selectionDialog(parent=self, sta_list=self.station_list)
        if sel_dlg.exec_():
            select_sta, bool_comp = sel_dlg.getSelected()
            query_comp = list(itertools.compress(comp_list, bool_comp))

            # specify output directory for miniSEED files
            temp_seed_out = os.path.join(os.path.dirname(self.cat_filename), event)

            # create directory
            if os.path.exists(temp_seed_out):
                shutil.rmtree(temp_seed_out)
            os.mkdir(temp_seed_out)

            query_time = UTCDateTime(quake_df['qtime'] - (10*60)).timestamp

            # Create a Stream object to put data into
            st = Stream()

            print('---------------------------------------')
            print('Finding Data for Earthquake: '+event)
            for matched_entry in self.session.query(Waveforms). \
                    filter(or_(and_(Waveforms.starttime <= query_time, query_time < Waveforms.endtime),
                               and_(query_time <= Waveforms.starttime, Waveforms.starttime < query_time + 20*60)),
                           Waveforms.station.in_(select_sta),
                           or_(*[Waveforms.component.like(comp) for comp in query_comp])):

                print(matched_entry.ASDF_tag)

                # read in the data to obspy
                temp_st = read(os.path.join(matched_entry.path, matched_entry.waveform_basename))

                # modify network header
                temp_tr = temp_st[0]
                temp_tr.stats.network = matched_entry.new_network

                st.append(temp_tr)

            if st.__nonzero__():

                # Attempt to merge all traces with matching ID'S in place
                st.merge()

                # now trim the st object to 5 mins
                # before query time and 15 minutes afterwards
                trace_starttime = UTCDateTime(query_time - (5*60))
                trace_endtime = UTCDateTime(query_time + (15*60))

                st.trim(starttime=trace_starttime, endtime=trace_endtime, pad=True, fill_value=0)

                try:
                    # write traces into temporary directory
                    for tr in st:
                        tr.write(os.path.join(temp_seed_out, tr.id + ".MSEED"), format="MSEED")
                    print("Wrote Temporary MiniSEED data to: " + temp_seed_out)
                    print('')
                except:
                    print("Something Went Wrong!")

            else:
                print("No Data for Earthquake!")




if __name__ == '__main__':
    proxy_queary = query_yes_no("Input Proxy Settings?")

    if proxy_queary == 'yes':
        print('')
        proxy = raw_input("Proxy:")
        port = raw_input("Proxy Port:")
        try:
            networkProxy = QtNetwork.QNetworkProxy(QtNetwork.QNetworkProxy.HttpProxy, proxy, int(port))
            QtNetwork.QNetworkProxy.setApplicationProxy(networkProxy)
        except ValueError:
            print('No proxy settings supplied..')
            sys.exit()

    app = QtGui.QApplication([])
    w = MainWindow()
    w.raise_()
    app.exec_()