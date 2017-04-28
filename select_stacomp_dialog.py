# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/g/data1/ha3/axc547/PycharmProjects/asdf_sextant/select_stacomp_dialog.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

class Ui_SelectDialog(object):
    def setupUi(self, SelectDialog):
        SelectDialog.setObjectName(_fromUtf8("SelectDialog"))
        SelectDialog.resize(194, 535)
        self.gridLayout = QtGui.QGridLayout(SelectDialog)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.check_all = QtGui.QCheckBox(SelectDialog)
        self.check_all.setObjectName(_fromUtf8("check_all"))
        self.gridLayout.addWidget(self.check_all, 0, 0, 1, 1)
        self.StaListView = QtGui.QListView(SelectDialog)
        self.StaListView.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        self.StaListView.setObjectName(_fromUtf8("StaListView"))
        self.gridLayout.addWidget(self.StaListView, 1, 0, 1, 1)
        self.zcomp = QtGui.QCheckBox(SelectDialog)
        self.zcomp.setChecked(True)
        self.zcomp.setObjectName(_fromUtf8("zcomp"))
        self.gridLayout.addWidget(self.zcomp, 2, 0, 1, 1)
        self.ncomp = QtGui.QCheckBox(SelectDialog)
        self.ncomp.setObjectName(_fromUtf8("ncomp"))
        self.gridLayout.addWidget(self.ncomp, 3, 0, 1, 1)
        self.ecomp = QtGui.QCheckBox(SelectDialog)
        self.ecomp.setAutoExclusive(False)
        self.ecomp.setObjectName(_fromUtf8("ecomp"))
        self.gridLayout.addWidget(self.ecomp, 4, 0, 1, 1)
        self.buttonBox = QtGui.QDialogButtonBox(SelectDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName(_fromUtf8("buttonBox"))
        self.gridLayout.addWidget(self.buttonBox, 5, 0, 1, 1)

        self.retranslateUi(SelectDialog)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("accepted()")), SelectDialog.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("rejected()")), SelectDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(SelectDialog)

    def retranslateUi(self, SelectDialog):
        SelectDialog.setWindowTitle(_translate("SelectDialog", "Dialog", None))
        self.check_all.setText(_translate("SelectDialog", "Select All", None))
        self.zcomp.setText(_translate("SelectDialog", "Z Component", None))
        self.ncomp.setText(_translate("SelectDialog", "N Component", None))
        self.ecomp.setText(_translate("SelectDialog", "E Component", None))

