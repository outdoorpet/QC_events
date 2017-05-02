from PyQt4 import QtCore, QtGui, QtWebKit, QtNetwork, uic
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

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, and_, or_
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func

# load in Qt Designer UI files
qc_events_ui = "qc_events.ui"
select_stacomp_dialog_ui = "select_stacomp_dialog.ui"

Ui_MainWindow, QtBaseClass = uic.loadUiType(qc_events_ui)
Ui_SelectDialog, QtBaseClass = uic.loadUiType(select_stacomp_dialog_ui)

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
    def __init__(self, parent=None, sta_list=None, chan_list=None):
        QtGui.QDialog.__init__(self, parent)
        self.selui = Ui_SelectDialog()
        self.selui.setupUi(self)
        self.setWindowTitle('Selection Dialog')

        # Set all check box to checked
        self.selui.check_all.setChecked(True)
        self.selui.check_all.clicked.connect(self.selectAllCheckChanged)

        # add stations to station select items
        self.sta_model = QtGui.QStandardItemModel(self.selui.StaListView)

        self.sta_list = sta_list
        for sta in self.sta_list:
            item = QtGui.QStandardItem(sta)
            item.setCheckable(True)

            self.sta_model.appendRow(item)

        self.selui.StaListView.setModel(self.sta_model)
        # connect to method to update stae of select all checkbox
        self.selui.StaListView.clicked.connect(self.listviewCheckChanged)

        # add channels to channel select items
        self.chan_model = QtGui.QStandardItemModel(self.selui.ChanListView)

        self.chan_list = chan_list
        for chan in self.chan_list:
            item = QtGui.QStandardItem(chan)
            item.setCheckable(True)

            self.chan_model.appendRow(item)

        self.selui.ChanListView.setModel(self.chan_model)



    def selectAllCheckChanged(self):
        ''' updates the listview based on select all checkbox '''
        sta_model = self.selui.StaListView.model()
        for index in range(sta_model.rowCount()):
            item = sta_model.item(index)
            if item.isCheckable():
                if self.selui.check_all.isChecked():
                    item.setCheckState(QtCore.Qt.Checked)
                else:
                    item.setCheckState(QtCore.Qt.Unchecked)

    def listviewCheckChanged(self):
        ''' updates the select all checkbox based on the listview '''
        sta_model = self.selui.StaListView.model()
        items = [sta_model.item(index) for index in range(sta_model.rowCount())]

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
        select_channels = []
        i = 0
        while self.sta_model.item(i):
            if self.sta_model.item(i).checkState():
                select_stations.append(str(self.sta_model.item(i).text()))
            i += 1
        i = 0
        while self.chan_model.item(i):
            if self.chan_model.item(i).checkState():
                select_channels.append(str(self.chan_model.item(i).text()))
            i += 1

        # Return Selected stations and selected channels
        return(select_stations, select_channels)


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
    Class to create a separate child window to display the event catalogue
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

        self.setWindowTitle('EQ Catalogue')
        self.show()


class MainWindow(QtGui.QMainWindow, Ui_MainWindow):
    """
    Main Window for metadata map GUI
    """

    def __init__(self):
        super(MainWindow, self).__init__()
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        self.open_SQL_button.released.connect(self.open_SQL_file)
        self.open_cat_button.released.connect(self.open_cat_file)
        self.open_xml_button.released.connect(self.open_xml_file)

        self.action_upd_xml_sql.triggered.connect(self.upd_xml_sql)
        self.action_get_gaps_sql.triggered.connect(self.get_gaps_sql)

        self.station_view.itemClicked.connect(self.station_view_itemClicked)

        cache = QtNetwork.QNetworkDiskCache()
        cache.setCacheDirectory("cache")
        self.web_view.page().networkAccessManager().setCache(cache)
        self.web_view.page().networkAccessManager()

        self.web_view.page().mainFrame().addToJavaScriptWindowObject("MainWindow", self)
        self.web_view.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
        self.web_view.load(QtCore.QUrl('map.html'))
        self.web_view.loadFinished.connect(self.onLoadFinished)
        self.web_view.linkClicked.connect(QtGui.QDesktopServices.openUrl)


        self.show()
        self.raise_()

    def onLoadFinished(self):
        with open('map.js', 'r') as f:
            frame = self.web_view.page().mainFrame()
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

        print('')
        print(self.inv)

        self.channel_codes = []
        # get the channel names for dataset
        for _j, chan in enumerate(self.inv[0][0]):
            self.channel_codes.append(self.inv[0][0][_j].code)

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
            self.web_view.page().mainFrame().evaluateJavaScript(js_call)

    def plot_events(self):
        # Plot the events
        for row_index, row in self.cat_df.iterrows():
            js_call = "addEvent('{event_id}', '{df_id}', {row_index}, " \
                      "{latitude}, {longitude}, '{a_color}', '{p_color}');" \
                .format(event_id=row['event_id'], df_id="cat", row_index=int(row_index), latitude=row['lat'],
                        longitude=row['lon'], a_color="Red",
                        p_color="#008000")
            self.web_view.page().mainFrame().evaluateJavaScript(js_call)

    def plot_inv(self):
        # plot the stations
        for i, station in enumerate(self.inv[0]):
            js_call = "addStation('{station_id}', {latitude}, {longitude});" \
                .format(station_id=station.code, latitude=station.latitude,
                        longitude=station.longitude)
            self.web_view.page().mainFrame().evaluateJavaScript(js_call)

    def create_SG2K_initiate(self, event, quake_df):

        # Launch the custom station/component selection dialog
        sel_dlg = selectionDialog(parent=self, sta_list=self.station_list, chan_list=self.channel_codes)
        if sel_dlg.exec_():
            select_sta, select_comp = sel_dlg.getSelected()

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
                               and_(query_time <= Waveforms.starttime, Waveforms.starttime < query_time + 30*60)),
                           Waveforms.station.in_(select_sta),
                           Waveforms.component.in_(select_comp)):

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
                trace_starttime = UTCDateTime(quake_df['qtime'] - (5*60))
                trace_endtime = UTCDateTime(quake_df['qtime'] + (15*60))

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

    def upd_xml_sql(self):
        # Look at the SQL database and create dictionary for start and end dates for each station
        #iterate through stations
        for i, station_obj in enumerate(self.inv[0]):
            station = station_obj.code


            print("\nQuerying SQLite database for start/end dates for each station")
            print("This may take a while.......")

            for min_max in self.session.query(func.min(Waveforms.starttime), func.max(Waveforms.endtime)). \
                    filter(Waveforms.station == station, Waveforms.component.like('__Z')):

                print("\nRecording interval for: " + station)
                print("\tStart Date: " + UTCDateTime(min_max[0]).ctime())
                print("\tEnd Date:   " + UTCDateTime(min_max[1]).ctime())


                #fix the station inventory
                self.inv[0][i].start_date = UTCDateTime(min_max[0])
                self.inv[0][i].end_date = UTCDateTime(min_max[1])

                # Fix the channel
                for _j, chan in enumerate(self.inv[0][i]):
                    self.inv[0][i][_j].start_date = UTCDateTime(min_max[0])
                    self.inv[0][i][_j].end_date = UTCDateTime(min_max[0])

        # Overwrite the origional station XML file
        self.inv.write(self.stn_filename, format="STATIONXML")
        print("\nFinished Updating StationXML file: " + self.stn_filename)

    def get_gaps_sql(self):
        # go through SQL entries and find all gaps
        # iterate through stations
        for station in self.station_list:
            print('_______________')
            print(station)

            #store for previous end time for a particular component in dictionary


            for entry in (self.session.query(Waveforms)
                                  .filter(Waveforms.station == station)
                                  .order_by(Waveforms.starttime)):

                print(entry.ASDF_tag)


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