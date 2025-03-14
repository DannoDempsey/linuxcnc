###################################################################
# **** IMPORT SECTION **** #
###################################################################
import sys
import os
import linuxcnc
import hal, hal_glib
import time
import math
import subprocess

from PyQt5 import QtCore, QtWidgets, QtGui

from qtvcp.widgets.mdi_line import MDILine as MDI_WIDGET
from qtvcp.widgets.gcode_editor import GcodeEditor as GCODE
from qtvcp.widgets.stylesheeteditor import  StyleSheetEditor as SSE 
from qtvcp.lib.gcodes import GCodes
from qtvcp.lib.toolbar_actions import ToolBarActions
from qtvcp.core import Status, Action, Info, Tool, Path, Qhal
from qt5_graphics import Lcnc_3dGraphics as DRO

# Set up config parser so we can look in the .ini file 
#from ConfigParser import ConfigParser

# Set up logging
from qtvcp import logger

#from lib.python.qtvcp.widgets import calculator
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

# Types for add status message
DEFAULT = 0
WARNING = 1
CRITICAL = 2

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
        self.gcodes = GCodes()
        #self.PATHS = paths
        
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
        self.jog_inc_z = 0
        self.jog_inc = 0
        self.active_joint = 0
        self.jog_flag = 0
        
        # Lathe DRO variables
        self.css_mode = 0
        self.show_dtg = False
        self.show_velocity = False
        self.show_offsets = False

        # Variables for the turret.
        self.current_tool_num = 0
        self.request_tool_num = 0
        self.reload_tool = 0

        # G-Code
        self.active_gcodes = []
        self.g43 = False
        self.current_line = 0 
        
        # Override Variables for Dryrun button.
        self.min_spindle_override = INFO.MIN_SPINDLE_OVERRIDE
        self.max_spindle_override = INFO.MAX_SPINDLE_OVERRIDE
        self.min_spindle_rpm = INFO.MIN_SPINDLE_SPEED
        self.max_spindle_rpm = INFO.MAX_SPINDLE_SPEED

        # Variables for physical buttons
        self.user_pgm_run = 0
        self.user_pgm_pause = 0
        self.user_ext_step = 0 
        
        # Variables for run time clock
        self.run_time = 0
        self.time_tenths = 0
        self.timer_on = False
        
        self.last_loaded_program = ""
        
        self.cmd = linuxcnc.command()
        self.stat = linuxcnc.stat()
    
        # Connect STATUS Signals 
        # Update the machine mode periodically  
        STATUS.connect('periodic', lambda w: self.periodic_update())
        
        # Connect status to return value/messages from various dialogs
        STATUS.connect('general', self.return_value)

        # Connect Status to sensitize the program step button.
        STATUS.connect('program-pause-changed', lambda w, state: self.sensitize_pgm_step(state))
     
    def class_patch__(self): 
        self.gcode_editor_patch()

    def gcode_editor_patch(self):    
        GCODE.editMode = self.gcode_editMode
        GCODE.readOnlyMode = self.gcode_readOnlyMode

    # At this point:
    # - the widgets are instantiated.
    # - the HAL pins are built but HAL is not set ready
    def initialized__(self):
        self.init_pins()
        self.init_preferences()
        self.init_widgets()
        self.init_jog_inc()
        self.init_turret_tools()
        self.class_patch__()
        # Uncomment to print out a list of available qtvcp objects
        #self.init_library()
        
    #############################
    # SPECIAL FUNCTIONS SECTION #
    #############################
    # Method to print out available library objects for LinuxCNC 2.8.4 
    #"""
    def init_library(self):
        print("Available ACTION objects")
        for attr in dir(ACTION):
            if not attr.startswith("_"):
                print (attr)
        print("Available STATUS objects")
        for attr in dir(STATUS):
            if not attr.startswith("_"):
                print (attr)    
        print("Available INFO objects")
        for attr in dir(INFO):
            if not attr.startswith("_"):
                print (attr)
        print("Available TOOL objects")
        for attr in dir(TOOL):
            if not attr.startswith("_"):
                print (attr)  
        print("Available GCODE Editor objects")
        for attr in dir(GCODE):
            if not attr.startswith("_"):
                print (attr)  
        print("Available GCODE objects")
        for attr in dir(GCodes):
            if not attr.startswith("_"):
                print (attr)             
    #"""
        
    # Define any new pins here
    def init_pins(self):
        # Jog enable pins
        pin = self.hal.newpin("joint0-jog-enable", hal.HAL_BIT, hal.HAL_OUT)
        pin = self.hal.newpin("joint1-jog-enable", hal.HAL_BIT, hal.HAL_OUT)
        
        # Jog increment pins
        pin = self.hal.newpin("joint0-jog-inc", hal.HAL_FLOAT, hal.HAL_OUT)
        pin = self.hal.newpin("joint1-jog-inc", hal.HAL_FLOAT, hal.HAL_OUT)
        
        # MPG pin for physical led beside MPG wheel
        pin = self.hal.newpin("mpg", hal.HAL_BIT, hal.HAL_OUT)
        
        # Turret Unclamp pin
        pin = self.hal.newpin("unclamp-turret", hal.HAL_BIT, hal.HAL_OUT)

        # Create pins for physical button inputs and connect them to our custom
        # methods.
        pin = self.hal.newpin("pgm-run-in", hal.HAL_BIT, hal.HAL_IN)
        pin.value_changed.connect(self.on_ext_pgm_run_changed)

        pin = self.hal.newpin("pgm-pause-in", hal.HAL_BIT, hal.HAL_IN)
        pin.value_changed.connect(self.on_ext_pgm_pause_changed)

        # Create pins to monitor the gear position
        pin = self.hal.newpin("gear-low", hal.HAL_BIT, hal.HAL_IN)
        pin = self.hal.newpin("gear-high", hal.HAL_BIT, hal.HAL_IN)
        pin = self.hal.newpin("gear-neutal", hal.HAL_BIT, hal.HAL_IN)


    # Set widget preferences here
    def init_preferences(self):
        pass
    
    # Set the initial state of widgets 
    def init_widgets(self):
        # Hide columns in the tool offsets view widget 
        self.w.tool_offsetview.hideColumn(2) # Pocket

        # Hide the Gcode editor top and bottom Menus so that we can use our 
        # own buttons
        self.w.gcode_editor.topMenu.hide()
        self.w.gcode_editor.bottomMenu.hide()

        # Hide the run from line frame
        self.w.frame_run_from.hide()

        # Set the runtime clock
        self.w.lbl_runtime.setText("00:00:00")

        #Set the x-axis as the default axis to jog
        self.w.btn_select_x_axis.setChecked(True)
        
        # Retrieve the current S code 
        self.update_scode_lbl()

        # Set the inital state of the program buttons
        self.w.btn_pgm_pause.setChecked(False)

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
        #self.update_lathe_status()

    # Used by the function lathe_dro_format() to 
    def update_lathe_status(self):
        current_gcodes = STATUS.stat.gcodes
        self.is_diameter_mode = 70 in current_gcodes
        self.css_mode = 960 in current_gcodes

        
    def update_metric_mode(self):    
        self.is_metric_mode = STATUS.is_metric_mode()
        
        # First time initialization
        if self.previous_mode is None:
            self.previous_mode = self.is_metric_mode
            #print(" First time initialization, previous_mode set to %d") % self.is_metric_mode
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
        self.css_mode = 960 in current_gcodes
       
        # Debug print statements to track mode changes
        #print("Is Diameter Mode (G7): %d" % self.is_diameter_mode)
            
        # Use the same logic to keep track of G7/G8 so that we can scale the x jog increments
        if self.previous_dia_mode is None:
            self.previous_dia_mode = self.is_diameter_mode
            #print(" First time initialization, previous_dia_mode set to %d") % self.is_diameter_mode
            
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
                self.hal['joint1-jog-inc'] = self.jog_inc_z
                
                # X axis increment
                if self.is_diameter_mode:
                    self.jog_inc_x = self.jog_inc / 2.0
                    self.hal['joint0-jog-inc'] = self.jog_inc_x
                    print ("Increments adjused for diameter mode")
                else:
                    self.jog_inc_x = self.jog_inc
                    self.hal['joint0-jog-inc'] = self.jog_inc_x
                    
            # Set the increments G20 
            else:
                # Z axis increment
                self.jog_inc = increment_selected * 25.4
                self.jog_inc_z = self.jog_inc
                self.hal['joint1-jog-inc'] = self.jog_inc_z
                
                # X axis increment
                if self.is_diameter_mode:
                    self.jog_inc_x = self.jog_inc / 2.0
                    self.hal['joint0-jog-inc'] = self.jog_inc_x
                    print ("Increments adjused for diameter mode")
                else:
                    self.jog_inc_x = self.jog_inc
                    self.hal['joint0-jog-inc'] = self.jog_inc_x
                    
        print("Jog increments set: X-axis = %.4fmm, Z-axis = %.4fmm" % (self.jog_inc_x, self.jog_inc))
    
    # Method to switch to Teleop mode for jogging.
    def on_btn_jog_enable_toggled(self, checked):
        if checked:
            ACTION.SET_MOTION_TELEOP(1)
            self.jog_flag = 1 
        else:
            ACTION.SET_MOTION_TELEOP(0)
            self.jog_flag = 0

    # Method to select the joint we want to MPG jog (uses radio buttons).
    def on_btn_select_x_axis_toggled(self,checked):
        self.active_joint = 0
        ACTION.SET_SELECTED_JOINT(0)

    def on_btn_select_z_axis_toggled(self,checked):
        self.active_joint = 1
        ACTION.SET_SELECTED_JOINT(1) 

    # Method for continuous jogging
    def continuious_jog(self, axis, direction):
        jog_active =  self.w.btn_jog_enable.isChecked()
        if jog_active and self.jog_inc == 0.0:
            ACTION.DO_JOG(axis, direction)
        else:
            # Do nothing
            return

    # If button is pressed direction = +/- 1. If button is released direction = 0
    def on_btn_jog_x_minus_pressed(self):
        self.continuious_jog(0,-1)

    def on_btn_jog_x_minus_released(self):
        self.continuious_jog(0,0)

    def on_btn_jog_x_plus_pressed(self):
        self.continuious_jog(0,1)

    def on_btn_jog_x_plus_released(self):
        self.continuious_jog(0,0)

    def on_btn_jog_z_minus_pressed(self):
        self.continuious_jog(2,-1)

    def on_btn_jog_z_minus_released(self):
        self.continuious_jog(2,0)

    def on_btn_jog_z_plus_pressed(self):
        self.continuious_jog(2,1)

    def on_btn_jog_z_plus_released(self):
        self.continuious_jog(2,0)

    # Special method required when using the internal homing routine of the 
    # servo amps 
    def on_btn_home_x_clicked(self):
        self.jog_disable()
        self.turn_off_compensation()
        # TODO: Use either M-Codes or .comp file to switch modes
        # MDI_WAIT function was not available in previous versions
        # ACTION.CALL_MDI_WAIT('M204',5)
        # or turn pin on to request mode switch
        # 
        ACTION.SET_MANUAL_MODE()
        ACTION.SET_MOTION_TELEOP(0)
        ACTION.SET_MACHINE_HOMING(0)

    def on_btn_home_z_clicked(self):
        # The X axis must be homed before the Z axis, otherwise the turret 
        # will hit the tailstock
        if not STATUS.is_joint_homed(0):
            mess = {'NAME':'MESSAGE',
                    'ID':'_HOMING',
                    'TITLE':'HOMING ERROR',
                    'MESSAGE':'X Axis must be homed first',
                    'TYPE':'OK',
                    'ICON':'WARNING'
                    }
            ACTION.CALL_DIALOG(mess)
            return
        
        self.jog_disable()
        self.turn_off_compensation()
        ACTION.SET_MANUAL_MODE()
        ACTION.SET_MOTION_TELEOP(0)
        ACTION.SET_MACHINE_HOMING(1)

    def jog_disable(self):
        self.w.btn_jog_enable.setChecked(False)

    def turn_off_compensation(self):
        # Cancel cutter compensation
        ACTION.CALL_MDI('G40')
        # Cancel tool length compensation
        ACTION.CALL_MDI('G49')

    ########################################################################
    # CALLBACKS FROM STATUS, DIALOG RETURN #
    ########################################################################
    # Method to return data from various dialogs.
    def return_value(self, w, message):
        num = message.get('RETURN')
        name = message.get('NAME')
        x_offset = bool(message.get('ID') == '_XOFFSET')
        z_offset = bool(message.get('ID') == '_ZOFFSET')
        set_rpm  = bool(message.get('ID') == '_SETRPM')
        get_line = bool(message.get('ID') == '_LINESELECT')
        run_from_line = bool(message.get('ID') == '_RUNFROMLINE')

        if x_offset and name == 'CALCULATOR' and not num is None:
            print('Entry return value from {} dialog = {}'.format(x_offset, num))
            axis = 0
            self.set_x_offset(axis, num)

        if z_offset and name == 'CALCULATOR' and not num is None:
            print('Entry return value from {} dialog = {}'.format(z_offset, num))
            axis = 2
            self.set_z_offset(axis, num)

        if set_rpm and name == 'ENTRY' and not num is None:
            print('Entry return value from {} dialog = {}'.format(set_rpm, abs(int((num))))) 
            rpm = abs(int(num))
            ACTION.CALL_MDI("G97 S%d" % rpm)
            ACTION.SET_MANUAL_MODE()

        if get_line and name =='ENTRY' and not num is None:
            print('Entry return value from {} dialog = {}'.format(get_line, abs(int((num)))))
            
            #Line 1 is indexed to 0 so we need to correect the returned value
            line_num = abs(int(num)) - 1
            self.set_line(line_num)

        if run_from_line and name == 'MESSAGE' and not num is None:
            print('Entry return value from {} dialog = {}'.format(run_from_line, num))
            
            # If dialog returned True, we want to run the program from the specified line
            # and hide the frame 
            if num:
                ACTION.RUN(self.current_line)
                self.w.frame_run_from.hide()
            # else do nothing
            else:
                return

    # Method to add a message to the machine log
    def add_status(self, message, alertLevel = DEFAULT, noLog = False):
        STATUS.emit('update-machine-log', message, 'TIME')

    # Method to combine the physical buttons pgm run/step and pgm pause
    # with the gui's buttons.

    def on_btn_pgm_step_clicked(self):
        ACTION.STEP()

    def on_btn_pgm_run_clicked(self):
        ACTION.RUN()
    
    def on_btn_pgm_pause_toggled(self,state):
        if state:
            ACTION.PAUSE()
        else:
            ACTION.RESUME()

    def on_btn_pgm_stop_clicked(self):
        ACTION.ABORT()
        self.w.btn_pgm_pause.setChecked(False)

    # ACTION buttons don't seem to sensitize correctly when the interpreter 
    # transitions from paused => resume. Step button should only be shown 
    # when the interpreter is paused.
    def sensitize_pgm_step(self, state):
        #print("sensitizing btn_pgm_step", state)
        if state:
            self.w.btn_pgm_step.setEnabled(True)
        else:
            self.w.btn_pgm_step.setEnabled(False)
    
    # Run button is only shown when the interp is idle, depending on what 
    # state the the interp is in will determine the functionality of the 
    # physical run button. 
    def on_ext_pgm_run_changed(self,state):
        if STATUS.is_auto_mode:
            if STATUS.is_interp_idle and state:
                self.on_btn_pgm_run_clicked()
            
            elif STATUS.is_interp_paused() and state:
                self.on_btn_pgm_step_clicked()
            else:
                # Do Nothing if the interp is not in one of these two states
                pass
        else:
            # Do nothing if we're not in auto mode
            pass
    
    # Toggle the button from False => True or from True => False when the 
    # external button is pressed, i.e. flip flop on ext button press only
    def on_ext_pgm_pause_changed(self,state):
        if STATUS.is_auto_running and state:
            new_state = not self.w.btn_pgm_pause.isChecked()
            self.w.btn_pgm_pause.setChecked(new_state)
        else:
            # Do nothing 
            pass

    ###########################################################################
    # PERIODIC UPDATES
    # #########################################################################        
    
    # Function to call methods that require periodic updates.
    def periodic_update(self):
        self.update_metric_mode()
        self.update_diameter_mode()
        self.update_run_timer()
        self.update_mpg()
        self.update_scode_lbl()

    def update_scode_lbl(self):
        scode = int(STATUS.stat.settings[2])
        #print(f"Commanded Spindle Speed: {scode}")
        self.w.lbl_scode.setText(str(scode))
        

    def update_mpg(self):
        if STATUS.is_man_mode():
            if self.jog_flag and self.jog_inc != 0:
                # Turn on the LED
                self.hal['mpg'] = True
                # Enable the joint selected by the radio buttons
                if self.active_joint == 0:
                    self.hal['joint0-jog-enable'] = True
                    self.hal['joint1-jog-enable'] = False
                
                if self.active_joint == 1:
                    self.hal['joint0-jog-enable'] = False
                    self.hal['joint1-jog-enable'] = True
            else:
                self.hal['mpg'] = False
                self.hal['joint0-jog-enable'] = False
                self.hal['joint1-jog-enable'] = False

        else:
            # Do nothing
            pass
        

    # Program Run Timer
    # Method to track the state of STATUS.is_auto_running and start/stop the timer
    def update_run_timer(self):
        current_state = STATUS.is_auto_running()
        # If the program is paused, do nothing
        if STATUS.is_auto_paused():
            return
        
        # If STATUS.is_auto_running transitions from False to True
        if current_state and not self.timer_on:
            self.start_run_timer()

        # If STATUS.is_auto_running transitions from True to False
        elif not current_state and self.timer_on:
            self.stop_run_timer()

        # If the timer is running, update it. Tic Toc ...
        elif self.timer_on:
            tick = time.time()
            elapsed_time = tick - self.timer_tick
            self.run_time += elapsed_time
            self.timer_tick = tick

            # Calculate the time, so that the label displays in HRS:MIN:SEC
            hours, remainder = divmod(int(self.run_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.w.lbl_runtime.setText("{:02d}:{:02d}:{:02d}" .format(hours, minutes, seconds))


    def start_run_timer(self):
        self.run_time = 0
        self.w.lbl_runtime.setText("00:00:00")
        self.timer_on = True
        self.timer_tick = time.time()

    def stop_run_timer(self):
        self.timer_on = False
        # Send a status message
        self.add_status("Run timer stopped at {}".format(self.w.lbl_runtime.text()))

    ###########################################################################
    # PROGRAM OPTIONS 
    ###########################################################################
    def on_btn_optional_stop_toggled(self, state):
        if state:
            ACTION.SET_OPTIONAL_STOP_ON()
        else:
            ACTION.SET_OPTIONAL_STOP_OFF()
    
    def on_btn_block_delete_toggled(self, state):
        if state:
            ACTION.SET_BLOCK_DELETE_ON()
        else:
            ACTION.SET_BLOCK_DELETE_OFF()

    # Convienece button to set the feed rate override and rapid override to 
    # 10%. Spindle override set to 50% 
    def on_btn_dry_run_toggled(self, state):
        if state:
            ACTION.SET_SPINDLE_RATE(50)
            ACTION.SET_RAPID_RATE(10)
            ACTION.SET_FEED_RATE(10)
        else:
            # Return overrides to 100%
            ACTION.SET_SPINDLE_RATE(100)
            ACTION.SET_RAPID_RATE(100)
            ACTION.SET_FEED_RATE(100)

    ###########################################################################
    # Manual Spindle Buttons
    ###########################################################################
    # Ideally we would check if the spindle is in gear but, for now just get 
    # things working

    def on_btn_spindle_fwd_clicked(self):
        if not STATUS.is_spindle_on():
            ACTION.CALL_MDI("M03")
            ACTION.SET_MANUAL_MODE()
        else:
            print("Spindle is already running. Stop Spindle before Changing Direction")
    
    def on_btn_spindle_rev_clicked(self):
        if not STATUS.is_spindle_on():
            ACTION.CALL_MDI("M04")
            ACTION.SET_MANUAL_MODE()
        else:
            print("Spindle is already running. Stop Spindle before Changing Direction")
    
    def on_btn_spindle_stop_clicked(self):
        if STATUS.is_spindle_on():
            ACTION.CALL_MDI("M05")
            ACTION.SET_MANUAL_MODE()
        else:
            # Do nothing
            pass

    #######################################################################
    # Turrret/Tool Section 
    # 10 Position Turret controlled via Classic Ladder
    #######################################################################
   
    def on_index_tool_num_changed(self, index):
        # Tool 1 is at the 0 index position, Tool 10 is at the 9 index position 
        index = int(abs(self.w.index_tool_select.currentIndex())) 
        self.request_tool_num =  index + 1
        
        # Debug
        #print("Requested Tool: %d \n" % self.request_tool_num)

    # If we are manually requesting a tool we don't want to apply the offsets 
    def on_btn_index_tool_clicked(self):
        current_tool = TOOL.current_tool_num
        request_tool = self.request_tool_num * 100

        # Debug
        print ("Current Tool # %d \n" % current_tool)
        print ("Requested Tool # %d \n" % request_tool)

        if request_tool != current_tool:
            # Tool Changes need to be done in MDI mode with the spindle off
            if STATUS.is_interp_idle() and STATUS.is_mdi_mode():
                # Stop the spindle if it is on
                if STATUS.is_spindle_on():
                    # Debug
                    print ("Stopping Spindle")
                    ACTION.CALL_MDI("M5")
                
                # Cancel any offsets that maybe active
                ACTION.CALL_MDI("G49")
                
                # Call the tool change
                ACTION.CALL_MDI("M6 T%d" % request_tool) # Call Tool Change 
        
            else:
                # Throw up an error dialog 
                print ("Must be in MDI mode to TOOL Change")

    def on_btn_touch_x_clicked(self):
        if TOOL.current_tool_num != 0:
            mess = {'NAME':'CALCULATOR', 'TITLE':'X Offset', 'ID':'_XOFFSET' }
            ACTION.CALL_DIALOG(mess)

    def on_btn_touch_z_clicked(self):
        if TOOL.current_tool_num != 0:
            mess = {'NAME':'CALCULATOR', 'TITLE':'Z Offset', 'ID':'_ZOFFSET' }
            ACTION.CALL_DIALOG(mess) 

    # Method to set the X axis offset. A test cut is taken and the diameter measured. 
    # Position is reported in Radius dimensions =  machine units (mm)
    def set_x_offset(self,axis, num):
        # Check if we have a tool loaded. 0 is not valid for non-random tool changers
        current_tool = TOOL.current_tool_num

        # If G43 is active, the current position is reported in Relative 
        # coordinates. 
        self.cancel_offsets()
        current_x_pos = STATUS.get_position()[0][0]
              
        if not STATUS.is_metric_mode():
            current_x_pos = current_x_pos * ( 1 / 25.4)
        
        if self.is_diameter_mode:
            current_x_pos = current_x_pos * 2

        # Calculate the required offset. 
        x_offset = current_x_pos - num

        # Set the tool table offset
        mdi_command = f"G10 L1 P{current_tool} X{x_offset:.4f}"
        ACTION.CALL_MDI(mdi_command)
        ACTION.CALL_MDI(f"G43 H{current_tool}")

    # Method to set the Z axis offset. This offset is measured from a fixed point
    # on the lathe. Usually the chuck. All tools are set to this point and then one
    # tool, the Master Tool can set the workpiece coordinate offset. All the other 
    # tools will be compensated accordingly.
    def set_z_offset(self,axis, num):
        current_tool = TOOL.current_tool_num
        self.cancel_offsets()
        current_z_pos = STATUS.get_position()[0][2]

        # If we are not in metric mode we need to convert the position to Imperial 
        if not STATUS.is_metric_mode():
            current_z_pos = current_z_pos * ( 1 / 25.4)
        
        # Calculate the Z offset position
        z_offset = current_z_pos - num
        
        # Format and call the MDI command
        mdi_command = f"G10 L1 P{current_tool} Z{z_offset:.4f}"
        ACTION.CALL_MDI(mdi_command)
        ACTION.CALL_MDI(f"G43 H{current_tool}")

    # Method to check if G43 tool offsets or work coordinate offsets are applied
    def cancel_offsets(self):
        self.g43 = True if 430 in STATUS.stat.gcodes else False
        print ("G43 Active: %s" % self.g43)

    ####################################################################################
    # G-Code Editor 
    #################################################################################### 

    def on_btn_edit_gcode_clicked(self, state):
        if state:
            self.w.gcode_editor.editMode()
            self.w.gcode_editor.topMenu.hide()
            self.w.gcode_editor.bottomMenu.show()
            
        else:
            self.w.gcode_editor.readOnlyMode()
            self.w.gcode_editor.topMenu.hide()
            self.w.gcode_editor.bottomMenu.hide()
    
    def on_btn_show_run_from_clicked(self,state):
        if state:
            self.w.frame_run_from.show()
        else:
            self.w.frame_run_from.hide()
            
    def on_btn_line_up_clicked(self):
        self.w.gcode_editor.select_lineup()
        self.get_line()

    def on_btn_line_down_clicked(self):
        self.w.gcode_editor.select_linedown()
        self.get_line()

    def on_btn_line_select_clicked(self):
        mess = {'NAME':'ENTRY', 
                'ID':'_LINESELECT',
                'TITLE':'ENTER LINE NUMBER'
                }
        ACTION.CALL_DIALOG(mess)

    def on_btn_run_from_line_clicked(self):
        self.get_line()
        mess = {'NAME':'MESSAGE',
                'ID':'_RUNFROMLINE',
                'MESSAGE':'RUN FROM LINE',
                'MORE':'DO YOU WANT TO RUN FROM LINE %d?' % self.current_line,
                'TYPE':'YESNO',
                'ICON':'QUESTION'
                }
        ACTION.CALL_DIALOG(mess)

    def get_line(self):
        self.current_line = self.w.gcode_editor.get_line()
        print("Current Line of G-code %s" % self.current_line)

    def set_line(self, line_num):
        self.w.gcode_editor.select_line(line_num)

    ###########################################################################
    # Tool Offset View 
    ###########################################################################

    def on_btn_tool_add_clicked(self):
        #self.w.tool_offsetview.add_lathe_tool()
        self.w.tool_offsetview.add_tool()

    def on_btn_tool_delete_clicked(self): 
        self.w.tool_offsetview.delete_tools()
                
    def on_btn_tool_save_clicked(self):
        self.w.tool_offsetview.save_tool_file()
        
    
    # Method to show only the tool number, and X and Z wear offset columns when
    # checked 
    def on_btn_show_wear_offsets_toggled(self, checked):
        pass
    """
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
"""

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

    def on_btn_clear_plot_clicked(self):
        ACTION.SET_GRAPHICS_VIEW('Y2')
        ACTION.SET_GRAPHICS_VIEW('clear')

    def on_btn_show_vel_toggled(self, state):
        print("show velocity")
        self.w.gcodegraphics.setProperty('_velocity', state)

    def on_btn_show_dtg_toggled(self, state):
        self.w.gcodegraphics.setProperty('_dtg', state)

    def on_btn_show_offsets_toggled(self, state):
        self.w.gcodegraphics.setProperty('_offsets', state)

    ###########################################################################
    # Spindle
    ###########################################################################
    # Use a line entry dialog to set G97 Sxxxx
    def on_btn_set_rpm_clicked(self):
        mess = {'NAME':'ENTRY',
                'ID':'_SETRPM',
                'TITLE':'SET RPM'
                }
        ACTION.CALL_DIALOG(mess)

    ###########################################################################
    # Turret/Tool Tab
    ###########################################################################
    #TODO: Currently unable to update the table to filter out rows 
    def on_btn_show_wear_offsets_toggled(self,state):
        if state:
            print("Showing wear offsets")
        else:
            print("Hiding Wear Offsets")

        
    ###########################################################################
    # Misc. functions 
    ###########################################################################
    def gcode_editMode(self):
        print("Edit G Code File")
    
    def gcode_readOnlyMode(self):
        print("Saving G Code File")

    def on_btn_launch_cl_clicked(self):
        print("Launching Classic Ladder")
        subprocess.Popen(["classicladder"])

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
