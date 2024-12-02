###################################################################
# **** IMPORT SECTION **** #
###################################################################
import sys
import os
import linuxcnc
import hal, hal_glib
import time

from PyQt5 import QtCore, QtWidgets

from qtvcp.widgets.mdi_line import MDILine as MDI_WIDGET
from qtvcp.widgets.gcode_editor import GcodeEditor as GCODE
from qtvcp.widgets.stylesheeteditor import  StyleSheetEditor as SSE 
from qtvcp.lib.gcodes import GCodes
from qtvcp.lib.toolbar_actions import ToolBarActions
from qtvcp.core import Status, Action, Info, Tool

# Set up config parser so we can look in the .ini file 
#from ConfigParser import ConfigParser

# Set up logging
from qtvcp import logger
LOG = logger.getLogger(__name__)

# Set the log level for this module
# One of DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG.setLevel(logger.DEBUG)

###################################################################
# **** instantiate libraries section **** #
###################################################################
# NO Keybinding 
#KEYBIND = Keylookup()
STATUS = Status()
ACTION = Action()
INFO = Info()
TOOL = Tool()
TOOLBAR = ToolBarActions()
STYLEEDITOR = SSE()
#GCODES = GCodes()

###################################################################
# **** HANDLER CLASS SECTION **** #
###################################################################

class HandlerClass:

    ########################
    # **** INITIALIZE **** #
    ########################
    # widgets allows access to  widgets from the qtvcp files
    # at this point the widgets and hal pins are not instantiated
    def __init__(self, halcomp,widgets,paths):
        
        self.cmd = linuxcnc.command()
        self.stat = linuxcnc.stat()
        #self.gstat = GStat()
        self.hal = halcomp
        self.w = widgets
        self.PATHS = paths
        
        # Lathe specific jog increments           
        # Location of the ini file to populate the combobox with increments
        self.ini_file = INFO.INI
        # Variables used to set the jog increments
        self.is_metric_mode = 0
        self.previous_mode = None
        self.is_diameter_mode = 0
        self.previous_dia_mode = None
        self.increments = []
        self.metric_inc = []
        self.imperial_inc = []
        self.jog_inc_x = 0
        self.jog_inc = 0
        self.active_joint = 0
        self.active_jog_flag = 0
        
        # Variables for the turret
        self.index_tool_num = 0
        
        # Variables for pan and zoom distance
        self._pan_inc = 0
        self.lr_pan_inc = 0
        
        
        # Global Variables
        self.run_time = 0
        self.time_tenths = 0
        self.timerOn = False
        self.last_loaded_program = ""
        
        self.cmd = linuxcnc.command()
        self.stat = linuxcnc.stat()
    
        # Connect STATUS Signals 
        # Update the machine mode periodically  
        STATUS.connect('periodic', lambda w: self.update_machine_mode())
        
        
    # The g-code editor is not great for touch screens. So we want to 
    # patch in our own methods and buttons
    def class_patch__(self): 
        GCODE.editMode = self.gcode_editMode
        GCODE.readOnlyMode = self.gcode_readOnlyMode
        #pass
    
    
    # at this point:
    # the widgets are instantiated.
    # the HAL pins are built but HAL is not set ready
    def initialized__(self):
        self.init_pins()
        self.init_preferences()
        self.init_widgets()
        self.init_jog_inc()
        self.init_turret_tools()
        # Uncomment to print out a list of available qtvcp objects for 
        # Linuxnc 2.8.4 
        self.init_library()
    #############################
    # SPECIAL FUNCTIONS SECTION #
    #############################
    # Method to print out available library objects for LinuxCNC 2.8.4 
    #"""
    def init_library(self):
        print("Available ACTION objects")
        for attr in dir(ACTION):
            if not attr.startswith("_"):
                print attr
        print("Available STATUS objects")
        for attr in dir(STATUS):
            if not attr.startswith("_"):
                print attr    
        print("Available INFO objects")
        for attr in dir(INFO):
            if not attr.startswith("_"):
                print attr
        print("Available TOOL objects")
        for attr in dir(TOOL):
            if not attr.startswith("_"):
                print attr  
        print("Available GCODE Editor objects")
        for attr in dir(GCODE):
            if not attr.startswith("_"):
                print attr  
        print("Available GCODE objects")
        for attr in dir(GCodes):
            if not attr.startswith("_"):
                print attr             
    #"""
        
    # Define any new pins here
    def init_pins(self):
        # Create pins for lathe jogging via the MPG or Joystick/Buttons
        # Connect these later in the postgui.hal file
        pin = self.hal.newpin("joint0-jog-enable-out", hal.HAL_BIT, hal.HAL_OUT)
        pin = self.hal.newpin("joint1-jog-enable-out", hal.HAL_BIT, hal.HAL_OUT)
        pin = self.hal.newpin("joint0-jog-inc-out", hal.HAL_FLOAT, hal.HAL_OUT)
        pin = self.hal.newpin("joint1-jog-inc-out", hal.HAL_FLOAT, hal.HAL_OUT)
        pin = self.hal.newpin("mpg-active", hal.HAL_BIT, hal.HAL_OUT)
            
    # Set widget preferences here
    def init_preferences(self):
        pass
    
    # Set the initial state of widgets 
    def init_widgets(self):
        # Hide columns in the tool offsets view widget 
        self.w.tool_offsetview.hideColumn(0) # Select
        self.w.tool_offsetview.hideColumn(2) # Pocket
        self.w.tool_offsetview.hideColumn(4) # X Wear
        self.w.tool_offsetview.hideColumn(8) # Z Wear
        #self.resize_columns()
        
        # Hide the Gcode editor top and bottom Menus so that we can use our 
        # own buttons
        self.w.gcode_editor.topMenu.hide()
        self.w.gcode_editor.bottomMenu.hide()
    

    # Special Function: Lathe Jog Increments
    # Populate the increments combobox with the increments specified 
    # in the ini file. Default to Continuous Jogging, inc = 0 
    def init_jog_inc(self):
        # Machine is metric
        # Load the increments for both imperial and metric
        self.increments = self.load_increments_from_ini(metric=True)
        self.increments = self.load_increments_from_ini(metric=False)
        
        # Update the machine mode periodically  
        #STATUS.connect('periodic', lambda w: self.update_machine_mode())
        
        # Check the state of the machine 
        self.update_machine_mode()

        # Poupulate the Combobox with the appropriate increments
        self.populate_lathe_inc()
        
        # Set the jog increments accordingly
        self.set_jog_increments()
    
    # Special Function: Turret Tools
    # Populate the turret combobox with the number of tools specified
    # in the ini file. Default to tool 1  
    def init_turret_tools(self):
        # Look in the INI file for how many tools the turret has 
        turret_num_tools = INFO.INI.find('DISPLAY', 'TURRET_NO_TOOLS')
        num_tools = int(turret_num_tools)
        
        # Clear the comboBox
        self.w.index_tool_select.clear()
        
        # Add the items to the list
        for i in range(1, num_tools + 1):
            tool_num = "{}".format(i)    
            self.w.index_tool_select.addItem(tool_num)
        
        # Set the default to tool 1 (index 0)
        # This will call def on_index_tool_num_changed()
        self.w.index_tool_select.setCurrentIndex(0)
    
    # Methods for special functions        
    # Method to find the jog increments from the ini file using the INFO library
    def load_increments_from_ini(self, metric=True):
        
        jog_increments = INFO.INI.find('DISPLAY', 'JOG_INCREMENTS')
        
        if jog_increments:
            increment_list = jog_increments.split(',')
            for increment in increment_list:
                increment = increment.strip()
                if metric and 'mm' in increment:
                    self.metric_inc.append(float(increment.replace('mm', '').strip()))
                    # Optional: Debug print to verify metric increments 
                    #print ('metric increments %s' % self.metric_inc)
                
                elif not metric and 'inch' in increment:
                    self.imperial_inc.append(float(increment.replace('inch', '').strip()))
                    # Optional: Debug print to verify imperial increments
                    # print ('imperial increments %s' % self.imperial_inc)
        return self.metric_inc, self.imperial_inc

    # Method to populate the ComboBox based on the current mode. Either G20 (Imperial) 
    # or G21 (Metric)    
    def populate_lathe_inc(self):
        # Clear the ComboBox
        self.w.lathe_jog_inc.clear()
 
        # For continuious jogging, we need to add a jog increment = 0, Text = Continuious
        # and make it the default
        self.w.lathe_jog_inc.addItem("CONTINUIOUS", 0)
        
        # Determine which increments to use based on the machine mode
        if self.is_metric_mode:
            self.increments = self.metric_inc           
        else:
            self.increments = self.imperial_inc
            
        # Add the increments to the ComboBox
        for increment in self.increments:
            self.w.lathe_jog_inc.addItem(str(increment), increment)
        
        # Optional: Debug print to verify the increments being added
        # print("Populated ComboBox with increments:", [self.w.lathe_jog_inc.itemText(i) for i in range(self.w.lathe_jog_inc.count())])     
    
    # Method to update the machine mode based on the current active G-codes G2/G21 and G7/G8 
    def update_machine_mode(self):
        self.update_metric_mode()
        self.update_diameter_mode()
        
    def update_metric_mode(self):    
        self.is_metric_mode = STATUS.is_metric_mode()
        
        # First time initialization
        if self.previous_mode is None:
            self.previous_mode = self.is_metric_mode
            print(" First time initialization, previous_mode set to %d") % self.is_metric_mode
            self.populate_lathe_inc()
        
        elif self.previous_mode != self.is_metric_mode:
            self.populate_lathe_inc()
            self.set_jog_increments()
        # Update the previous mode state
        self.previous_mode = self.is_metric_mode  
    
    def update_diameter_mode(self):
        current_gcodes = STATUS.stat.gcodes
        # Optional: Debug print statements
        #for index, gcode in enumerate(current_gcodes):
        #    print("G-code at index %d: %s (Type: %s)" % (index, gcode, type(gcode)))
        
        # Check for G7 (diameter mode) and G8 (radius mode) 
        # Note; G7 = 70, G8 = 80 
        self.is_diameter_mode = 70 in current_gcodes
        #self.is_radius_mode = 'G8' in converted_gcodes

        # Debug print statements to track mode changes
        #print("Is Diameter Mode (G7): %d" % self.is_diameter_mode)
            
        # Use the same logic to keep track of G7/G8 so that we can scale the x jog increments
        if self.previous_dia_mode is None:
            self.previous_dia_mode = self.is_diameter_mode
            print(" First time initialization, previous_dia_mode set to %d") % self.is_diameter_mode
            
        elif self.previous_dia_mode != self.is_diameter_mode:
            # Change the  jog increments
            self.set_jog_increments()
        self.previous_dia_mode = self.is_diameter_mode
        
    # Method to capture the change of the ComboBox lathe_jog_increment     
    def on_jog_inc_changed(self, index):
        if index >=0:
            self.set_jog_increments()
            
    # Method to set the jog increments based on G20/G21 and G7/G8
    # If G7 (Diameter mode) is acive we want to jog the X axis so that 
    # the diameter changes by the selected increment. 
    # Jog inc = selected jog inc/2
    # If G8 (Radius mode) is active we want to jog the X axis so that  
    # the radius changes by the selected increment.
    # jog inc = selected jog inc 
    # Machine is metric
    # Jog increments need to be set in machine units.
    # Calculations: Mode = Metric
    #               Increment = 0.1mm
    #               Z axis = 0.1 mmm 
    #               X axis = 0.1mm (G8) or 0.5mm (G7)
    #
    #               Mode = Imperial
    #               Increment = 0.1 inch = 0.1 inch * 25.4 mm / 1 inch
    #                         = 2.54 mm 
    #               Z axis = 2.54 mm
    #               X axis = 2.54 mm (G8) or  1.27 mm (G7)
    #
    
    def set_jog_increments(self):        
        index = self.w.lathe_jog_inc.currentIndex()
        if index >= 0:
            increment_selected = self.w.lathe_jog_inc.itemData(index)
            print("Selected Jog Increment:", increment_selected)
            
            # Set the increments G21
            if self.is_metric_mode:
                # Z axis increment
                self.jog_inc = increment_selected
                self.jog_inc_z = self.jog_inc
                self.hal['joint1-jog-inc-out'] = self.jog_inc_z
                
                # X axis increment
                if self.is_diameter_mode:
                    self.jog_inc_x = self.jog_inc / 2.0
                    self.hal['joint0-jog-inc-out'] = self.jog_inc_x
                    print ("Increments adjused for diameter mode")
                else:
                    self.jog_inc_x = self.jog_inc
                    self.hal['joint0-jog-inc-out'] = self.jog_inc_x
                    
            # Set the increments G20 
            else:
                # Z axis increment
                self.jog_inc = increment_selected * 25.4
                self.jog_inc_z = self.jog_inc
                self.hal['joint1-jog-inc-out'] = self.jog_inc_z
                
                # X axis increment
                if self.is_diameter_mode:
                    self.jog_inc_x = self.jog_inc / 2.0
                    self.hal['joint0-jog-inc-out'] = self.jog_inc_x
                    print ("Increments adjused for diameter mode")
                else:
                    self.jog_inc_x = self.jog_inc
                    self.hal['joint0-jog-inc-out'] = self.jog_inc_x
                    
        print("Jog increments set: X-axis = %.4fmm, Z-axis = %.4fmm" % (self.jog_inc_x, self.jog_inc))
                
    ########################
    # CALLBACKS FROM STATUS #
    ########################


        



    #######################
    # callbacks from form #
    #######################
    def on_index_tool_num_changed(self, index):
        index = self.w.index_tool_select.currentIndex()
        if index >= 0:
            self.index_tool_num = self.w.index_tool_select.currentText()
            print("Tool selected: %s" % self.index_tool_num)
         
    # In the 2.8 Version of qtvcp there is no object in the ACTION library 
    # to set the mode to teleop mode (lathe jogging) so we need to create 
    # our own 
    def on_btn_jog_active_toggled(self, checked):
        if checked:
            self.cmd.teleop_enable(1)
            self.cmd.wait_complete()
            STATUS.stat.poll()
        else:
            self.cmd.teleop_enable(0)
            self.cmd.wait_complete()
            STATUS.stat.poll()
            
        print("Teleop mode toggled", self.stat)
        print("Selected Joint", STATUS.get_selected_joint())
    
    def on_btn_select_x_axis_toggled(self,checked):
        self.active_joint = 0
        ACTION.SET_SELECTED_JOINT(0)
        # ... probably best to use either the ACTION library OR global variables 
        # but not both. 
    def on_btn_select_z_axis_toggled(self,checked):
        self.active_joint = 1
        ACTION.SET_SELECTED_JOINT(1) 

    def on_btn_edit_gcode_clicked(self, state):
        if state:
            self.w.gcode_editor.editMode()
            self.w.gcode_editor.topMenu.hide()
            self.w.gcode_editor.bottomMenu.show()
            
        else:
            self.w.gcode_editor.readOnlyMode()
            self.w.gcode_editor.topMenu.hide()
            self.w.gcode_editor.bottomMenu.hide()
            

    # Tool Table Buttons
    def on_btn_tool_add_clicked(self):
        
        print("Add Tool button clicked")
        #TOOL.ADD_TOOL()
        
        
    
    def on_btn_tool_delete_clicked(self):
        print("Delete Tool button clicked")
        """
        tool_info = TOOL.GET_TOOL_ARRAY()
        for tool in tool_info:
            print("Tool Number: {}". format(tool[0]))
        
        view = self.w.tool_offsetview
        model = view.model()
        # List to store the tool numbers we want to delete
        tools_to_delete = []
        for row in reversed (range(model.rowCount(QtCore.QModelIndex()))):
            index = model.index(row,0)
            item = model.data(index, QtCore.Qt.CheckStateRole)
            
            if item == QtCore.Qt.Checked:
                tool = model.index(row,1).data()
                tools_to_delete.append(int(tool))
                
            if tools_to_delete:
                TOOL.DELETE_TOOLS(tools_to_delete)
                print("Deleted Tools:{}".format(tools_to_delete)) 
                #TOOL.GET_TOOL_MODELS()
        """
                
    def on_btn_tool_reload_clicked(self):
        TOOL.GET_TOOL_MODELS()

    
    def on_btn_tool_apply_clicked(self):
        print("Apply Tool button clicked")
        #TOOL.SAVE_TOOLFILE()
    
    # Method to show only the tool number, and X and Z wear offset columns when
    # checked 
    def on_btn_show_wear_offsets_toggled(self, checked):
        # Hide the columns we don't want to see
        if checked:
            #self.w.tool_offsetview.hideColumn(0) # Select
            #self.w.tool_offsetview.hideColumn(2) # Pocket #
            self.w.tool_offsetview.hideColumn(3) # X Offset
            self.w.tool_offsetview.hideColumn(7) # Z Offset
            self.w.tool_offsetview.hideColumn(15) # Diameter
            self.w.tool_offsetview.hideColumn(16) # Front Angle
            self.w.tool_offsetview.hideColumn(17) # Back Angle
            self.w.tool_offsetview.hideColumn(18) # Orientation
            self.w.tool_offsetview.showColumn(4)
            self.w.tool_offsetview.showColumn(8)
            #self.w.tool_offsetview.hideColumn(19) # Comments
            #self.resize_columns()            

 
        else:
            print("Show Wear Offsets toggled OFF")
            #self.w.tool_offsetview.showColumn(0)
            #self.w.tool_offsetview.showColumn(2)
            self.w.tool_offsetview.showColumn(3)
            self.w.tool_offsetview.showColumn(7)
            self.w.tool_offsetview.showColumn(15)
            self.w.tool_offsetview.showColumn(16)
            self.w.tool_offsetview.showColumn(17)
            self.w.tool_offsetview.showColumn(18)
            self.w.tool_offsetview.hideColumn(4)
            self.w.tool_offsetview.hideColumn(8)
            #self.w.tool_offsetview.showColumn(19)
            #self.resize_columns()
        
    def resize_columns(self):
            # Set the column width
            #self.w.tool_offsetview.setColumnWidth(1, 50)
            #self.w.tool_offsetview.setColumnWidth(4, 200)
            #self.w.tool_offsetview.setColumnWidth(8, 200)
            view = self.w.tool_offsetview
            model = view.model()
            view.setColumnWidth(1, 60)
            #for col in range(view.model().columnCount(QtCore.QModelIndex())):
            #    view.setColumnWidth(col, 120)
            for col in range(2,9):
                view.setColumnWidth(col, 120)
            for col in range(10, 17):
                view.setColumnWidth(col, 150)
            self.w.tool_offsetview.update()

    # Method to set the active line in
    def set_current_line(self, line):
        self.w.lbl_start_line.setText(line)
    
    ###########################################################################
    # Preview Buttons
    ###########################################################################

    ## Not working very well, move on for now...
    # TODO
    def on_btn_pan_down_clicked(self):
        self._pan_inc += 1
        print ('view increment = %d' % self._pan_inc)
        #self.w.gcodegraphics.panView(0,self._pan_inc)
        #self.w.gcodegraphics.panView(0,self.pan_inc)
        ACTION.ADJUST_GRAPHICS_PAN(0,self._pan_inc)
        #ACTION.SET_GRAPHICS_VIEW('pan-down')
                    
    def on_btn_pan_up_clicked(self):
        self._pan_inc -= 1
        print ('view increment = %d' % self._pan_inc)
        ACTION.ADJUST_GRAPHICS_PAN(0,self._pan_inc)
                
    def on_btn_pan_left_clicked(self):
        self.lr_pan_inc += 1
        print ('L/R Rview increment = %d' % self.lr_pan_inc)
        ACTION.ADJUST_GRAPHICS_PAN(self.lr_pan_inc,0)
        
    def on_btn_pan_right_clicked(self):
        self.lr_pan_inc -= 1
        print ('L/R view increment = %d' % self.lr_pan_inc)
        ACTION.ADJUST_GRAPHICS_PAN(self.lr_pan_inc,0)
            
    def on_btn_show_dro_toggled(self, checked):   
        if checked:
            self.w.gcodegraphics.setProperty('_dro', True)
            self.w.gcodegraphics.setProperty('overlay', True)
            print ('_dro = %s' % self.w.gcodegraphics.property('_dro'))
            self.w.gcodegraphics.redraw()
        else:
            self.w.gcodegraphics.setProperty('_dro', False)
            print ('_dro = %s' % self.w.gcodegraphics.property('_dro'))  
        
    #####################
    # general functions #
    #####################
    def gcode_editMode(self):
        print("Edit G Code File")
    
    def gcode_readOnlyMode(self):
        print("Saving G Code File")


    #####################
    # KEY BINDING CALLS #
    #####################
    # None

    ###########################
    # **** closing event **** #
    ###########################

    ##############################
    # required class boiler code #
    ##############################

    def __getitem__(self, item):
        return getattr(self, item)
    def __setitem__(self, item, value):
        return setattr(self, item, value)

################################
# required handler boiler code #
################################

def get_handlers(halcomp,widgets,paths):
     return [HandlerClass(halcomp,widgets,paths)]
