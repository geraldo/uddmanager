# -*- coding: utf-8 -*-
"""
/***************************************************************************
 UDDmanager
                                 A QGIS plugin
 Parse QGIS 3 project files and write a JSON config file with layer information.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-07-05
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Gerald Kogler/PSIG
        email                : geraldo@servus.at
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QFileInfo, QUrl
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication

from qgis.core import QgsProject, Qgis, QgsLayerTreeLayer, QgsLayerTreeGroup, QgsVectorLayer, QgsAttributeEditorElement, QgsExpressionContextUtils
from qgis.gui import QgsGui
import json
import os
import requests
import unicodedata
import webbrowser
import paramiko
import urllib.parse

# Import the code for the dialog
from .uddmanager_dialog_update import UDDmanagerDialogUpdate
import os.path
from tempfile import gettempdir
import layertree2json
from qgis.utils import plugins


class UDDmanager:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'UDDmanager_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&UDD Manager')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None
        self.first_start_layertree = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('UDDmanager', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToWebMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        self.add_action(
            os.path.join(os.path.dirname(__file__), "icon.png"),
            text=self.tr(u'Update Open Data layers'),
            callback=self.run,
            parent=self.iface.mainWindow())
        self.add_action(
            os.path.join(os.path.dirname(__file__), "layertree2json.png"),
            text=self.tr(u'Publish to web map viewer'),
            callback=self.run_layertree2json,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False)
        self.add_action(
            os.path.join(os.path.dirname(__file__), "help.svg"),
            text=self.tr(u'Help'),
            callback=self.help,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False)

        # will be set False in run()
        self.first_start = True
        self.first_start_layertree = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr(u'&UDD Manager'),
                action)
            self.iface.removeToolBarIcon(action)


    ####################################################
    # UPDATE
    ####################################################
    def getUrlFromJson(self, jsonUrl: str, format: str):
        apiData = json.loads(requests.get(jsonUrl).text)

        for resource in apiData["result"]["resources"]:
            # probably also should check with resource["name"]
            if resource["format"] == format:
                return {
                    "name": resource["name"],
                    "url": resource["url"]
                }


    def download(self, url: str, layerId: id, dest_folder: str, filename: str = ""):
        # dest_folder is not securly evaluated, see https://gis.stackexchange.com/questions/447073/getting-source-path-of-layer-file-in-pyqgis
        #dest_folder = self.getDataProviderURL(layerId)

        #if not os.path.exists(dest_folder):
        #    os.makedirs(dest_folder)

        if (filename == ""):
            filename = url.split('/')[-1].replace(" ", "_")
        file_path = os.path.join(self.projectFolder + dest_folder, filename)

        r = requests.get(url, stream=True)
        if r.ok:
            # self.dlg.logOutput.appendPlainText("      -> saving to " + os.path.abspath(file_path))
            if not self.dlg.testMode.isChecked():
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 8):
                        if chunk:
                            f.write(chunk)
                            f.flush()
                            os.fsync(f.fileno())
        else:  # HTTP status code 4XX/5XX
            self.dlg.logOutput.appendPlainText("Download failed: status code {}\n{}".format(r.status_code, r.text))


    def getDataProviderURL(self, layerId):
        layer = QgsProject.instance().mapLayer(layerId)
        print(layer.source())
        return
        
        uri = layer.dataProvider().dataSourceUri().split("|layername=")
        if len(uri) == 1:
            uri = uri[0].split("?")

        print(uri[0])
        if os.path.isfile(uri[0]):
            print(self.projectFolder)
            return uri[0]


    def isSelectedLayer(self, nodeName):
        for layer in self.iface.layerTreeView().selectedLayers():
            if layer.name() == nodeName:
                return True
        return False


    def isLayerInSelectedGroup(self, layerId):
        for lyrId in self.activeGroup().findLayerIds():
            if (lyrId == layerId):
                return True
        return False


    def isGroupInSelectedGroup(self, groupName):
        if self.activeGroup().name()==groupName:
            return True
        for group in self.activeGroup().findGroups(True):
            if (group.name() == groupName):
                return True
        return False


    def updateNode(self, node: object, level: int = 0, parentNodeName: str = ""):
        levelStr = ""

        for i in range(level):
            levelStr += "  "

        if (node["type"] == "group"):

            if self.dlg.radioImportAll.isChecked() or (self.dlg.radioImportGroups.isChecked() and self.isGroupInSelectedGroup(node["name"])):
                    self.dlg.logOutput.appendPlainText(levelStr + node["name"])

            if (len(node["children"]) > 0):
                for child in node["children"]:
                    nextlevel = level + 1
                    self.updateNode(child, nextlevel, parentNodeName + "/" + node["name"])

        elif (node["type"] == "layer"):

            if self.dlg.radioImportAll.isChecked() or (self.dlg.radioImportGroups.isChecked() and self.isLayerInSelectedGroup(node["id"])) or (self.dlg.radioImportLayers.isChecked() and self.isSelectedLayer(node["name"])):

                printStr = levelStr + "- " + node["name"]

                testMode = "TEST" if self.dlg.testMode.isChecked() else "DOWNLOAD"

                if "package_name" in node and node["package_name"] is not None and "package_format" in node and node["package_format"] is not None:

                    self.dlg.logOutput.appendPlainText(printStr + ": " + testMode + " '" + node["package_name"] + "' (" + node["package_format"] + ")")

                    # load file from CKAN API
                    resource = self.getUrlFromJson("https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show?id="+node["package_name"], node["package_format"])
                    #self.dlg.logOutput.appendPlainText("get file " + resource["name"] + " from " + resource["url"])

                    if resource != None:
                        self.download(resource["url"], node["id"], parentNodeName, resource["name"])
                        QApplication.processEvents()
                    else:
                        self.dlg.logOutput.appendPlainText(printStr + ": " + testMode + " FAILED: resource not defined for "+node["package_name"]+"/"+node["package_format"])

                else:
                    self.dlg.logOutput.appendPlainText(printStr + ": " + testMode + " FAILED: 'package_name' or 'package_format' not defined")

                #self.dlg.logOutput.appendPlainText(printStr)


    def activeGroup(self):
        tree_view = self.iface.layerTreeView()
        
        # retrieve current selected index in the layer tree
        current_index = tree_view.selectionModel().currentIndex()
        # check if index is valid (could be invalid e.g. if layer tree is empty)
        if not current_index.isValid():
            return
        # convert the index to a node object
        node = tree_view.index2node(current_index)
        
        # check if selected node is a group
        if isinstance(node, QgsLayerTreeGroup):
            return node


    def show_packages(self):
        webbrowser.open(self.dlg.inputApiUrl.text() + '/3/action/package_list')


    ####################################################
    # GLOBAL
    ####################################################

    def init_layertree2json(self):
        self.checkDependency()

        if self.first_start_layertree == True:
            self.first_start_layertree = False
            self.layertree2json = plugins['layertree2json']
        
    def run_layertree2json(self):
        self.init_layertree2json()
        self.layertree2json.run()

    def help(self):
        url = QUrl.fromLocalFile(os.path.dirname(__file__) + "/docs/index.html").toString()
        webbrowser.open(url, new=2)

    def checkDependency(self):
        # Let the user know that plugin layertree2json is required
        if 'layertree2json' not in plugins:
            self.iface.messageBar().pushMessage("Warning", "In order to use UDDManager you have to install plugin LayerTree2JSON", level=Qgis.Critical, duration=3)
            return

    def clearLog(self):
        self.dlg.logOutput.clear()


    def run(self):
        """Run method that performs all the real work"""
        self.checkDependency()

        if (QgsProject.instance().fileName() == ""):
            self.iface.messageBar().pushMessage("Warning", "Please open a project file in order to use this plugin", level=Qgis.Warning, duration=3)

        else:
            # define global varialbes

            # Create the dialog with elements (after translation) and keep reference
            # Only create GUI ONCE in callback, so that it will only load when the plugin is started
            if self.first_start == True:
                self.first_start = False
                self.dlg = UDDmanagerDialogUpdate()

                self.dlg.buttonShowPackages.clicked.connect(self.show_packages)
                self.dlg.buttonClearLog.clicked.connect(self.clearLog)
                self.dlg.buttonBox.helpRequested.connect(self.help)
                self.dlg.buttonBox.accepted.disconnect()
                self.dlg.buttonBox.accepted.connect(self.runwithoutclose)

            # show the dialog
            self.dlg.show()
            # Run the dialog event loop
            result = self.dlg.exec_()
            # See if OK was pressed
            #if result:


    def runwithoutclose(self):

        # IMPORT

        if self.dlg.radioImportGroups.isChecked() and self.activeGroup() == None:
            #self.dlg.logOutput.appendPlainText("Please select a GROUP to proceed!")
            self.iface.messageBar().pushMessage("Warning", "Please select a GROUP to proceed!", level=Qgis.Warning, duration=3)

        elif self.dlg.radioImportLayers.isChecked() and len(self.iface.layerTreeView().selectedLayers()) == 0:
            #self.dlg.logOutput.appendPlainText("Please select a LAYER to proceed!")
            self.iface.messageBar().pushMessage("Warning", "Please select a LAYER to proceed!", level=Qgis.Warning, duration=3)

        else:
            self.init_layertree2json()

            # define global variables
            self.projectFilename = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_filename")
            self.projectFolder = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_folder")
            project_file = self.projectFilename.replace('.qgs', '')

            # parse QGS file to JSON
            info=[]
            for group in QgsProject.instance().layerTreeRoot().children():
                if not group.name().startswith("¡"):
                    info.append(self.layertree2json.getLayerTree(group))

            # write JSON to temporary file and show in browser
            filenameJSON = self.projectFolder + os.path.sep + self.projectFilename + '.json'
            file = open(filenameJSON, 'w')
            file.write(json.dumps(info))
            file.close()

            self.dlg.logOutput.appendPlainText("------------------------")

            f = open(filenameJSON)
            data = json.load(f)

            for node in data:
                self.updateNode(node)

            f.close()

            # message to user
            self.iface.messageBar().pushMessage("Success", "Update of Open Data layers successfull!", level=Qgis.Success, duration=3)
