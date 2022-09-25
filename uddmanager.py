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
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QFileInfo
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsProject, Qgis, QgsLayerTreeLayer, QgsLayerTreeGroup, QgsVectorLayer, QgsAttributeEditorElement, QgsExpressionContextUtils
from qgis.gui import QgsGui
import json
import unicodedata
import webbrowser
import pysftp

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .uddmanager_dialog import UDDmanagerDialog
import os.path
from tempfile import gettempdir


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

        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.add_action(
            icon_path,
            text=self.tr(u'Parse Layers and save as JSON'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr(u'&UDD Manager'),
                action)
            self.iface.removeToolBarIcon(action)


    def show_online_file(self):
        host = self.dlg.inputHost.text()
        path = self.dlg.inputJSONpath.text()[len(self.JSONpathbase)-1:]
        webbrowser.open(host + path)


    def show_project(self):
        host = self.dlg.inputHost.text()
        path = self.dlg.inputProject.text()
        if path == 'ctbb':
            path += os.path.sep + 'index'
            if self.projectFilename != 'poum':
                path += '_' + self.projectFilename.replace('.qgs', '')
            path += '.php'
        webbrowser.open(host + os.path.sep + path)


    def show_packages(self):
        webbrowser.open(self.dlg.inputApiUrl.text() + '/3/action/package_list')


    def radioStateLocal(self, state):
        if state.isChecked() == True:
            self.dlg.radioProject.setEnabled(False)


    def radioStateUpload(self, state):
        if state.isChecked() == True:
            self.dlg.radioProject.setEnabled(True)


    def inputsFtpOk(self):
        if (len(self.dlg.inputHost.text()) == 0 or
            len(self.dlg.inputUser.text()) == 0 or
            len(self.dlg.inputPassword.text()) == 0):

            self.iface.messageBar().pushMessage(
                    "Warning", "You have to fill out fields Host, User and Password in order to use FTP",
                    level=Qgis.Warning, duration=3)
            return False
        else: 
            return True


    def connectToFtp(self, uploadFile=False, uploadPath=False):
        # print(uploadFile, uploadPath)

        try:
            sftp = pysftp.Connection(host=self.dlg.inputHost.text(), 
                username=self.dlg.inputUser.text(), 
                password=self.dlg.inputPassword.text())

            if (uploadFile and uploadPath):
                sftp.chdir(uploadPath)
                sftp.put(uploadFile)

                self.iface.messageBar().pushMessage(
                    "Success", "File UPLOADED to host " + self.dlg.inputHost.text(),
                    level=Qgis.Success, duration=3)
            else:
                self.iface.messageBar().pushMessage(
                    "Success", "FTP connection ESTABLISHED to host " + self.dlg.inputHost.text(),
                    level=Qgis.Success, duration=3)

            sftp.close()
        except:
            self.iface.messageBar().pushMessage(
                "Warning", "FTP connection FAILED to host " + self.dlg.inputHost.text(),
                level=Qgis.Warning, duration=3)


    def test_connection(self):
        if (self.inputsFtpOk()):
            self.connectToFtp()
 

    def replaceSpecialChar(self, text):
        chars = "!\"#$%&'()*+,./:;<=>?@[\\]^`{|}~¬·"
        for c in chars:
            text = text.replace(c, "")
        return text


    def stripAccents(self, str):
       return ''.join(c for c in unicodedata.normalize('NFD', str)
                      if unicodedata.category(c) != 'Mn')


    def getLayerTree(self, node, project_file):
        obj = {}

        if isinstance(node, QgsLayerTreeLayer):
            obj['name'] = node.name()
            obj['qgisname'] = node.name()   # internal qgis layer name with all special characters
            obj['mapproxy'] = project_file + "_layer_" + self.replaceSpecialChar(self.stripAccents(obj['name'].lower().replace(' ', '_')))
            obj['type'] = "layer"
            obj['indentifiable'] = node.layerId() not in QgsProject.instance().nonIdentifiableLayers()
            obj['visible'] = node.isVisible()
            obj['hidden'] = node.name().startswith("@") # hide layer from layertree
            if obj['hidden']:
                obj['visible'] = True   # hidden layers/groups have to be visible by default
            obj['showlegend'] = not node.name().startswith("~") and not node.name().startswith("¬") # don't show legend in layertree
            obj['fields'] = []
            obj['actions'] = []
            obj['external'] = node.name().startswith("¬")
            obj['package_name'] = QgsExpressionContextUtils.layerScope(node.layer()).variable("layer_package_name")
            obj['package_format'] = QgsExpressionContextUtils.layerScope(node.layer()).variable("layer_package_format")

            # remove first character
            if not obj['showlegend']:
                obj['name'] = node.name()[1:]

            # fetch layer directly from external server (not from QGIS nor mapproxy)
            if obj['external']:
                obj['name'] = node.name()[1:]
                src = QgsProject.instance().mapLayer(node.layerId()).source()
                
                # wms url
                istart = src.index("url=")+4
                try:
                    iend = src.index("&", istart)
                except ValueError:
                    iend = len(src)
                obj['wmsUrl'] = src[istart:iend]
                
                # wms layers
                istart = src.index("layers=")+7
                try:
                    iend = src.index("&", istart)
                except ValueError:
                    iend = len(src)
                obj['wmsLayers'] = src[istart:iend]
                
                # wms srs
                istart = src.index("crs=")+4
                try:
                    iend = src.index("&", istart)
                except ValueError:
                    iend = len(src)
                obj['wmsProjection'] = src[istart:iend]

            #print("- layer: ", node.name())

            layer = QgsProject.instance().mapLayer(node.layerId())

            if obj['indentifiable'] and isinstance(layer, QgsVectorLayer):

                fields = []

                # get all fields like arranged using the Drag and drop designer
                edit_form_config = layer.editFormConfig()
                root_container = edit_form_config.invisibleRootContainer()
                for field_editor in root_container.findElements(QgsAttributeEditorElement.AeTypeField):
                    i = field_editor.idx()
                    if i >= 0 and layer.editorWidgetSetup(i).type() != 'Hidden':
                        #print(i, field_editor.name(), layer.fields()[i].name(), layer.attributeDisplayName(i))

                        f = {}
                        f['name'] = layer.attributeDisplayName(i)
                        obj['fields'].append(f)

                for action in QgsGui.instance().mapLayerActionRegistry().mapLayerActions(layer):
                    a = {}
                    a['name'] = action.name()
                    a['action'] = action.action()
                    obj['actions'].append(a)

            return obj

        elif isinstance(node, QgsLayerTreeGroup):
            obj['name'] = node.name()
            obj['qgisname'] = node.name()   # internal qgis layer name with all special characters
            obj['mapproxy'] = project_file + "_group_" + self.replaceSpecialChar(self.stripAccents(obj['name'].lower().replace(' ', '_')))
            obj['type'] = "group"
            obj['visible'] = node.isVisible()
            obj['hidden'] = node.name().startswith("@")
            if obj['hidden']:
                obj['visible'] = True   # hidden layers/groups have to be visible by default
            obj['showlegend'] = not node.name().startswith("~") # don't show legend in layertree
            obj['children'] = []
            #print("- group: ", node.name())
            #print(node.children())

            # remove first character
            if not obj['showlegend']:
                obj['name'] = node.name()[1:]

            for child in node.children():
                obj['children'].append(self.getLayerTree(child, project_file))

        return obj


    def update_path(self):
        self.dlg.inputJSONpath.clear()
        self.JSONpath = self.JSONpathbase + self.dlg.inputProject.text()+'/js/data/'
        self.JSONpathfile = self.JSONpath + self.projectFilename + '.json'
        self.dlg.inputJSONpath.setText(self.JSONpathfile)
        
        self.dlg.inputQGSpath.clear()
        self.QGSpath = self.QGSpathbase + self.dlg.inputProject.text() + os.path.sep
        self.QGSpathfile = self.QGSpath + self.projectFilename
        self.dlg.inputQGSpath.setText(self.QGSpathfile)


    def update_settings(self):
        QSettings().setValue('/UDDmanager/ActiveHost', self.dlg.inputHost.text())
        QSettings().setValue('/UDDmanager/ActiveUser', self.dlg.inputUser.text())
        QSettings().setValue('/UDDmanager/ActivePassword', self.dlg.inputPassword.text())


    def run(self):
        """Run method that performs all the real work"""

        if (QgsProject.instance().fileName() == ""):
            self.iface.messageBar().pushMessage(
                  "Warning", "Please open a project file in order to use this plugin",
                  level=Qgis.Warning, duration=3)

        else:
            # define global varialbes
            self.projectFilename = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_filename")
            self.projectFolder = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_folder")
            self.JSONpathbase = '/var/www/'
            self.JSONpath = self.JSONpathbase
            self.JSONpathfile = ''
            self.QGSpathbase = '/home/ubuntu/'
            self.QGSpath = self.QGSpathbase
            self.QGSpathfile = ''

            # Create the dialog with elements (after translation) and keep reference
            # Only create GUI ONCE in callback, so that it will only load when the plugin is started
            if self.first_start == True:
                self.first_start = False
                self.dlg = UDDmanagerDialog()

                ### CAPTURE SETTINGS ###
                self.dlg.inputHost.setText(QSettings().value('/UDDmanager/ActiveHost', ''))
                self.dlg.inputUser.setText(QSettings().value('/UDDmanager/ActiveUser', ''))
                self.dlg.inputPassword.setText(QSettings().value('/UDDmanager/ActivePassword', ''))
                
                self.dlg.radioLocal.toggled.connect(lambda:self.radioStateLocal(self.dlg.radioLocal))
                self.dlg.radioUpload.toggled.connect(lambda:self.radioStateUpload(self.dlg.radioUpload))
                self.dlg.buttonTest.clicked.connect(self.test_connection)
                self.dlg.buttonShow.clicked.connect(self.show_online_file)
                self.dlg.buttonShowProject.clicked.connect(self.show_project)
                self.dlg.buttonShowPackages.clicked.connect(self.show_packages)
                self.dlg.inputHost.textChanged.connect(self.update_settings)
                self.dlg.inputUser.textChanged.connect(self.update_settings)
                self.dlg.inputPassword.textChanged.connect(self.update_settings)

            # set Project list
            self.dlg.inputProject.clear()
            self.dlg.inputProject.setText('uddmanager')

            # set JSON file path
            self.dlg.inputJSONpath.clear()
            self.JSONpath = self.JSONpathbase + self.dlg.inputProject.text() + '/js/data/'
            self.JSONpathfile = self.JSONpath + self.projectFilename + '.json'
            self.dlg.inputJSONpath.setText(self.JSONpathfile)

            # set QGS file path
            self.dlg.inputQGSpath.clear()
            self.QGSpath = self.QGSpathbase + self.dlg.inputProject.text() + os.path.sep
            self.QGSpathfile = self.QGSpath + self.projectFilename
            self.dlg.inputQGSpath.setText(self.QGSpathfile)

            # show the dialog
            self.dlg.show()
            # Run the dialog event loop
            result = self.dlg.exec_()
            # See if OK was pressed
            if result:

                # check which tab is selected
                if self.dlg.tabWidget.currentIndex() == 0:

                    # IMPORT

                    # check mode
                    #self.dlg.radioImportAll.isChecked()
                    #self.dlg.radioImportGroup.isChecked()
                    #self.dlg.radioImportLayer.isChecked()

                elif self.dlg.tabWidget.currentIndex() == 1:

                    # EXPORT

                    # check mode
                    if ((self.dlg.radioUpload.isChecked() and self.inputsFtpOk()) 
                        or self.dlg.radioLocal.isChecked()):

                        # prepare file names
                        project_file = self.projectFilename.replace('.qgs', '')

                        # parse QGS file to JSON
                        info=[]
                        for group in QgsProject.instance().layerTreeRoot().children():
                            obj = self.getLayerTree(group, project_file)
                            info.append(obj)

                        # write JSON to temporary file and show in browser
                        #filenameJSON = gettempdir() + os.path.sep + self.projectFilename + '.json'
                        filenameJSON = self.projectFolder + os.path.sep + self.projectFilename + '.json'
                        file = open(filenameJSON, 'w')
                        file.write(json.dumps(info))
                        file.close()

                        if (self.dlg.radioUpload.isChecked() and self.inputsFtpOk()):
                            # upload JSON file to server by FTP
                            self.connectToFtp(filenameJSON, self.JSONpath)
                            filenameJSON = self.dlg.inputJSONpath.text()
                            
                            # upload QGS file to server by FTP
                            self.connectToFtp(self.projectFolder + '/' + self.projectFilename, self.QGSpath)
                            self.iface.messageBar().pushMessage(
                              "Success", "QGS file " + self.projectFilename + " published at " + self.QGSpath,
                              level=Qgis.Success, duration=3)                    
                        
                        if self.dlg.radioProject.isChecked():
                            self.show_project()
                        elif self.dlg.radioJson.isChecked():
                            if self.dlg.radioUpload.isChecked():
                                self.show_online_file()
                            else:
                                webbrowser.open(filenameJSON)

                        # message to user
                        self.iface.messageBar().pushMessage(
                          "Success", "JSON file published at " + filenameJSON,
                          level=Qgis.Success, duration=3)