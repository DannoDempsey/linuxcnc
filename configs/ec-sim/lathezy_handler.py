#!/usr/bin/python
import sys,os,subprocess
import linuxcnc
import hal
import hal_glib
import gobject
import gtk
import gtk.glade
import gtksourceview2 as gtksourceview
from gladevcp.gladebuilder import GladeBuilder
import gladevcp.makepins
import pango
from hal_glib import GStat
import time
from time import strftime,localtime


# This is a handler file for using Gscreen's infrastructure
# to load a completely custom glade screen.
# Project - must be saved as a GTK builder project,
#         - the toplevel window is caller window1 (The default name) 
#         - connect an onwindow1_destroy signal else you can't close down linuxcnc 

#Constansts for mode identification
_MAN = 0; _MDI = 1; _AUTO = 2; _JOG = 3; _LOCKTOGGLE = 1
_INCH = 0
_MM = 1

# standard handler call
def get_handlers(halcomp,builder,useropts,gscreen):
     return [HandlerClass(halcomp,builder,useropts,gscreen)]

class HandlerClass:
    
    # self.emc is for control and status of linuxcnc
    # self.emc = emc_interface.emc_control(linuxcnc)
    # self.data is important data from gscreen and linuxcnc
    # self.widgets is all the widgets from the glade files
    # self.gscreen is for access to gscreens methods

    def __init__(self, halcomp,builder,useropts,gscreen):
        # access to nml commands via gscreen
        self.emc = gscreen.emc
        # access to gscreens data class
        self.data = gscreen.data
        # access to gscreens widgets
        self.widgets = gscreen.widgets
        # access to gscreen functions?pins?
        self.gscreen = gscreen
        # since we have a lot of custom button functions, we also need to have access to 
        # linuxcnc's command,status and error channels
        self.command = linuxcnc.command()
        self.status = linuxcnc.stat()
        self.error = linuxcnc.error_channel()
        self.gstat = GStat()
        
        # Global Variables
        # btn_mode related variables
        self._MAN = 0
        self._MDI = 1
        self._AUTO = 2
        self._JOG = 3
        self._MM = 1
        self._IMPERIAL = 0
        self.mode_order = (self._MAN,self._MDI,self._AUTO)
        self.mode_labels = [_("Manual Mode"),_("MDI Mode"),_("Auto Mode")]
       #lathe specific
        self.data.lathe_mode = True
        self.data.diameter_mode = True
        self.data.IPR_mode = True
        #machine units
        self.data.dro_units = self._MM
        self.data.machine_units = self._MM
        self.data.jog_increments = 0 
        self.jog_increment_units = self._MM
        self.data.machine_on = False
        self.data.or_limits = False
        self.data.homed = 0
        self.data.graphic_ypos = 0
        self.data.graphic_xpos = 0
        self.data.view = 2
        self.data.task_mode = 2
        self.data.estopped = True
        # spindle 
        self.data.spindle_dir = 0
        self.data.spindle_speed = 0
        
        self.data.spindle_start_rpm = 300
        self.data.spindle_preset = 0.0
        
        self.data.mode_labels = [_("MANUAL"),_(" MDI  "),_(" AUTO ")]
        self.spindle_preset = 0.0
        self.spindle_rpm_request = 0
        self.active_spindle_command = "" # spindle command setting
        self.active_feed_command = "" # feed command setting              

        # related to dialog boxes
        self.data.entry_dialog = None
        # embeded keyboard
        self.data.embedded_keyboard = True
        # Theme name
        self.data.theme_name = "expose"

        #
        self.tooleditor = ""
        self.tooltable = ""

        # Joint related data -------------------------------------------------------------
        # Homing and jogging are done in joint/free mode MODE_FREE = 0, MODE_COORD = 1, MODE_TELEOP = 2 
        self.motion_mode = 0
        
        # variable to hold the active joint, 
        self.active_joint = 0 
        
        # variable to hold the the jog active flag       
        self.active_jog_flag = 0
        
        # variable to hold the joint flag,
        self.joint_flag = True
        # variable to set the jog increment based on the combobox
        # combobox can be read in two ways 
            # 1) as columns 0-x, which you can assign values to or
            # 2) as the actual float values. For continuous jogging set increment = 0
        # the combobox is set to 0 by default in glade
        self.jog_increment = 0.0  
        self.jog_increment_units = 0      
        self.joint0_is_homed = False
        self.joint1_is_homed = False
        
        self.widgets.led_xaxis_selected.set_active(False)
        self.widgets.led_zaxis_selected.set_active(False)
        self.widgets.jog_button_label.set_label("JOG MODE OFF")
        
        self.test_value = 0.0
        
        self.motion_pin = int(0)
        
        # variables for homing routine
        self.joint0_timeout = 0.0
        self.joint1_timeout = 0.0  
        self.joint_homing_error = 0.0
        
        # entry clock
        gobject.timeout_add(1000, self.clock)

    def __getitem__(self, item):
        return getattr(self, item)
        
    def __setitem__(self, item, value):
        return setattr(self, item, value)

    # This connects siganals without using glade's autoconnect method
    # Widgets that are the same as the default gscreen use this method
    # Widgets that are user created are connected using glades auto-connect method
    def connect_signals(self,handlers):
        signal_list = [ ["window1","destroy", "on_window1_destroy"],
                        ["run_halshow","clicked", "on_halshow"],
                        ["run_status","clicked", "on_status"],
                        ["run_halmeter","clicked", "on_halmeter"],
                        ["run_halscope","clicked", "on_halscope"],
                        ["run_ladder","clicked", "on_ladder"],
                        ["pop_statusbar", "clicked", "on_pop_statusbar_clicked"],
                        ["theme_choice", "changed", "on_theme_choice_changed"],                        
                        ["button_search_fwd","clicked", "search_fwd"],
                        ["button_search_bwd","clicked", "search_bwd"],
                        ["button_replace_text","clicked", "replace_text"],
                        ["button_undo","clicked", "undo_edit"],
                        ["button_redo","clicked", "redo_edit"],
                        ["shut_down","clicked","on_window1_destroy"],
                        ["hide_cursor","clicked","on_hide_cursor"]
                                              
                        
                      ]

        for i in signal_list:
            if len(i) == 3:
                self.gscreen.widgets[i[0]].connect(i[1], self.gscreen[i[2]])
            elif len(i) == 4:
                self.gscreen.widgets[i[0]].connect(i[1], self.gscreen[i[2]],i[3])


    # NOTES ABOUT GSCREEN data
    # DATA                      SECTION         VARIABLE                DESC
    # self.data._maxvelocity    [TRAJ]          MAX_LINEAR_VELOCITY     Max velocity of machine units/min
    # self.data.max_jog_rate    [DISPLAY]       MAX_LINEAR_VELOCITY     Max jog rate unit/min
    # self.data.jog_rate        [DISPLAY]       DEFAULT_LINEAR_VELOCITY Default jog rate      
            

    # HOW TO push a message to the statusbar 
    #           - self.widgets.statusbar1.push(self.statusbar_id,message)           
    # HOW TO push an alarm entry to the alarm page in the diagnostic tab  
    #           - self.add_alarm_entry(("Your message here"))

########################################################################
# MODE BUTTONS
########################################################################

    def on_rbtn_manual_toggled(self,widget,data=None):
        if self.ok_to_switch_modes():
            self.command.mode(linuxcnc.MODE_MANUAL)
            self.command.wait_complete()
            self.hide_frames()
            self.widgets.notebook1.set_current_page(0)
                    
    def on_rbtn_mdi_toggled(self,widget,data=None):
        if self.ok_to_switch_modes():
            self.jog_disable()
            self.command.mode(linuxcnc.MODE_MDI)
            self.command.wait_complete()
            self.hide_frames()
            self.widgets.notebook1.set_current_page(1)
                
    def on_rbtn_auto_toggled(self,widget,data=None):
        if self.ok_to_switch_modes():
            self.jog_disable()          
            self.command.mode(linuxcnc.MODE_AUTO)
            self.command.wait_complete()
            self.hide_frames()
            self.widgets.notebook1.set_current_page(2)       

########################################################################
# Convience & Safety Functions
########################################################################

# Looks like ok_for_mdi_cmd and ok_to_switch_modes test the same conditions 
# but give different error messages...


    def ok_for_mdi_cmd(self):
        """ Function to check if is ok to issue an MDI command"""
        self.status.poll()
        if self.status.estop == 0 and self.status.interp_state == linuxcnc.INTERP_IDLE and self.status.enabled == 1:
            return True
        else:
            # throw up a warning dialog 
            message = _("INTERPRETER IS BUSY")
            self.gscreen.warning_dialog(message, True)            
            return False

    def ok_to_switch_modes(self):
        
        self.status.poll()
        
        # check for pre-conditions
            # interpreter is idle
            # not in estop
            # trajectory planner is enabled        
        if self.status.estop == 0 and self.status.interp_state == linuxcnc.INTERP_IDLE and self.status.enabled == 1:
            # make sure jog is no longer active and then continue on
            self.widgets.tbtn_activate_jog.set_active(False)
            return True
        else:
            # throw up a warning dialog 
            message = _("Not able to switch Modes!")
            self.gscreen.warning_dialog(message, True)            
            return False 
    
    def hide_frames(self): 
        self.status.poll()       
        task_mode = self.status.task_mode
        # MDI = 1, MAN = 3, AUTO = 2 
        # Hide the appropriate frames/boxes/tabs for each specific mode
        if task_mode == 3:
            self.widgets.auto_button_frame.hide()
            self.widgets.mdi_button_frame.show()
            self.widgets.manual_button_frame.hide()

        if task_mode == 1:
            self.widgets.auto_button_frame.hide()
            self.widgets.mdi_button_frame.hide()
            self.widgets.manual_button_frame.show()

        elif task_mode == 2:
            self.widgets.auto_button_frame.show()
            self.widgets.mdi_button_frame.hide()
            self.widgets.manual_button_frame.hide()

    """ Hide the manual spindle controls in manual mode to reduce the risk of accidentally
        starting the spindle while jogging"""
    def on_cbtn_show_man_spindle_toggled(self,widget,data=None):
        if self.widgets.cbtn_show_man_spindle.get_active():
            self.widgets.man_spindle_frame.hide()
        else:
            self.widgets.man_spindle_frame.show()


    """ The estop reset button uses vcp action estop reset for convience but we also want
        to make sure that the gui restarts in manual mode after an estop. We are going to 
        use an "extra" callback to make sure that this happens. """
    def on_estop_reset_button_clicked(self,widget,data=None):
        # see what mode we were in when the estop was pressed
        last_mode = self.status.task_mode
        #print "Last Mode = %s" % last_mode
        if last_mode!= 1 :
            #self.ok_to_switch_modes()
            self.command.mode(linuxcnc.MODE_MANUAL)
            self.command.wait_complete()
            self.hide_frames()
            self.widgets.notebook1.set_current_page(0)
            #print "mode set to MANUAL"
        # if we were in manual when the estop was hit than jogging may have 
        # been active    
        self.jog_disable()
            
    def on_btn_clear_mdi_history_clicked(self,widget,data=None):
        self.widgets.hal_mdihistory.model.clear()

########################################################################
# HOME/JOG BUTTONS
########################################################################

    # Special routine required for using the internal homing routine of the 
    # servo amps

    def on_btn_homex_clicked(self,widget,data=None):
        
        if self.status.task_mode == linuxcnc.MODE_MANUAL:
        
             # disable jogging
            self.jog_disable()
        
            # Turn off cutter compensation 
            self.turn_off_compensation()
        
            # Set the x-axis as the active joint
            self.active_joint = 0
        
            # Must be in joint mode for homing
            self.command.teleop_enable(0)
            self.command.wait_complete()
        
            # Start the Homing Routine
            print ("Homing X-Axis")
            self.command.home(0)
        
        else:        
            # Throw up a error message to switch the machine mode to manual
            message = _("Switch Machine to MANUAL Mode before homing")
            self.gscreen.warning_dialog(message, True)

    def on_btn_homez_clicked(self,widget,data=None):

        if self.status.task_mode == linuxcnc.MODE_MANUAL:
            # Check if x-axis has been homed first, if not bad things might happen.
            self.status.poll()        
            if self.status.joint[0]["homed"] == 1:
                # setup homing preconditions
                self.jog_disable()
                self.turn_off_compensation()
                self.active_joint = 1
                self.command.teleop_enable(0)
                self.command.wait_complete()
                # home Z-Axis
                print ("Homing Z-Axis")
                self.command.home(1)           
            else:
             # Throw up a error message to home x-axis first so that the turret
             # does not crash into the tailstock.
                message = _("Need to home X-Axis before homing Z-Axis")
                self.gscreen.warning_dialog(message, True)               
        else:
            # Throw up a error message to change the machine mode to manual.
            message = _("Switch Machine to MANUAL Mode before homing")
            self.gscreen.warning_dialog(message, True) 

        
    """ Function to turn off cutter compensation and tool length compensation.
        Toggling the radio buttons seems to prevent the GUI from jamming up """
    def turn_off_compensation(self):
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete()
        self.widgets.rbtn_mdi.set_active(True)
        self.command.mdi("G40")
        self.command.mdi("G49")
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.wait_complete()
        self.widgets.rbtn_manual.set_active(True)
        
    """ Function to disable jogging """
    def jog_disable(self):
        self.widgets.tbtn_activate_jog.set_active(False)
        self.widgets.led_jog_active.set_active(False) 
        self.widgets.jog_button_label.set_label("JOG MODE OFF")               
        self.active_jog_flag = 0


    # Set active joint based on the axis selection radio buttons
    def on_select_xaxis_button_toggled(self,widget,data=None):
        self.active_joint = 0            
           
    def on_select_zaxis_button_toggled(self,widget,data=None):
        self.active_joint = 1  

             
    # Enable jogging     
    def on_tbtn_activate_jog_toggled(self,widget,data=None):
     
        if self.widgets.tbtn_activate_jog.get_active():
            self.widgets.led_jog_active.set_active(True) 
            self.widgets.jog_button_label.set_label("JOG ACTIVE")    
            self.active_jog_flag = 1
            # set the motion mode to free
            self.status.poll()
            self.motion_mode = self.status.motion_mode
            if self.motion_mode != 0:
                self.command.teleop_enable(0)
                self.command.wait_complete()           
            
        else:
            self.widgets.led_jog_active.set_active(False) 
            self.widgets.jog_button_label.set_label("JOG MODE OFF")               
            self.active_jog_flag = 0

          
    # Set the float value of the jog increments based on a combobox               
    def on_combobox_jog_inc_changed(self,combobox, data=None):
        # Determine the value of the combobox
        temp = (combobox.hal_pin_f.get())
        print ("combobox value = %f" % temp)
        
        # poll the status channel 
        self.status.poll()
    
        # Metric
        if "G21" in self.data.active_gcodes:
            if temp != 0.0 and temp < 0.001 :
                # throw up an error message to let the operator know
                message = _("0.001 is the MINIMUM increment in Metric Mode")
                self.gscreen.warning_dialog(message, True)                
            
                # and then set the jog increment to the minimum = 0.001
                self.widgets.combobox_jog_inc.set_active(1)     
        
        # Inch
        if "G20" in self.data.active_gcodes:
            temp += temp * 25.4

        # Set the jog increment       
        self.jog_increment = temp
        
    def on_x_jog_plus_button_press_event(self,widget,data=None):
        if self.ok_to_jog():
            self.command.jog(linuxcnc.JOG_CONTINUOUS, self.joint_flag, 0, (self.data.jog_rate/60))            
 
    def on_x_jog_plus_button_release_event(self,widget,data=None):
        self.command.jog(linuxcnc.JOG_STOP, self.joint_flag, 0)

    def on_x_jog_minus_button_press_event(self,widget,data=None):
        if self.ok_to_jog():           
            self.command.jog(linuxcnc.JOG_CONTINUOUS, self.joint_flag, 0, (-1*(self.data.jog_rate/60))) 

    def on_x_jog_minus_button_release_event(self,widget,data=None):
        self.command.jog(linuxcnc.JOG_STOP, self.joint_flag, 0)

    def on_z_jog_plus_button_press_event(self,widget,data=None):
        if self.ok_to_jog():
            self.command.jog(linuxcnc.JOG_CONTINUOUS, self.joint_flag, 1, (self.data.jog_rate/60)) 

    def on_z_jog_plus_button_release_event(self,widget,data=None):
        self.command.jog(linuxcnc.JOG_STOP, self.joint_flag, 1)    

    def on_z_jog_minus_button_press_event(self,widget,data=None):
        if self.ok_to_jog():
            self.command.jog(linuxcnc.JOG_CONTINUOUS, self.joint_flag, 1, (-1*(self.data.jog_rate/60))) 

    def on_z_jog_minus_button_release_event(self,widget,data=None):
        self.command.jog(linuxcnc.JOG_STOP, self.joint_flag,1)

    def ok_to_jog(self):
        jog_active = self.widgets.tbtn_activate_jog.get_active()
        increments = self.jog_increment   
        if jog_active == 1 and increments == 0:
            return True
        else:
            message = _("Make sure jog button is active and jog increments is set to continuous")
            self.gscreen.warning_dialog(message,True)
    
########################################################################        
# Manual Spindle Frame Buttons 
########################################################################

    def on_btn_set_spindle_clicked(self,widget):  
        rpm ="0"      
        self.gscreen.launch_numerical_input("on_set_spindle_rpm_entry_return",rpm,None,"SET SPINDLE RPM")    
    
    def on_set_spindle_rpm_entry_return(self,widget,result,calc,rpm,userdata2):
        if result == gtk.RESPONSE_ACCEPT:
            value = calc.get_value()
            if value == None:
                value = 0.0
            # check to make sure that the value is  - within the acceptable range
            # 										- an absolute (positive) number
            # 										- an integer 
            # since we are going to use a gear change/ M03/M04 remap we need to make sure that 
            # the values for min and max are the same (values found in the ini file 
            message = "RPM NOT WITHIN RANGE"
            if value <= self.spindle_min_rpm:  
               self.gscreen.warning_dialog(message,True)
            if value >= self.spindle_max_rpm:
               self.gscreen.warning_dialog(message,True)
            
            else:
               self.spindle_rpm_request = value 
                                             
        # update the label
        text = _("%0.f") % self.spindle_rpm_request
        self.widgets.lbl_set_spindle.set_text(text)        
        widget.destroy()
        self.data.entry_dialog = None
            
    def on_btn_spindle_rev_clicked(self,widget,data=None):
        self.ok_to_turn_on_spindle()
        self._set_spindle("reverse")

    def on_btn_spindle_stop_clicked(self,widget,data=None):
        self._set_spindle("stop")
        
    def on_btn_spindle_fwd_clicked(self,widget,data=None):
        self.ok_to_turn_on_spindle()
        self._set_spindle("forward")
        
    def ok_to_turn_on_spindle(self):
        # check to see if the spindle is running
        self.status.poll()
        spindle_status = self.data.spindle_dir
        if spindle_status == -1 or spindle_status == 1:
            self._set_spindle("stop")
            self.command.wait_complete(5)
            print "stop spindle command sent"
            return
        elif spindle_status == 0:
            return
        else:
            message = _("Something went wrong, can't turn on spindle")
            self.gscreen.warning_dialog(message,True)

######################################################################## 
# OVERRIDES  
########################################################################
# Note: ini file settings are in units/sec vs gscreen units/min, 
# therefore we want to use the scaled-value
# No idea how/why these work(  ?,      ?,         ?)
    def on_feed_override_value_changed (self, widget, data=None):
        # Read the speedcontrol pins to determine values. 
        rate = self.gscreen.halcomp["feed_override.scaled-value"]
        self.emc.feed_override(rate)
        
    def on_spindle_override_value_changed (self, widget, data=None):
        # Read the speedcontrol pins to determine values. 
        spindle_rate = self.gscreen.halcomp["spindle_override.scaled-value"]
        self.emc.spindle_override(spindle_rate)       

    def on_rapid_override_value_changed (self, widget, data=None):
        # Read the speedcontrol pins to determine values. 
        rapid_scale = self.gscreen.halcomp["rapid_override.scaled-value"]
        #print rapid_scale
        self.emc.rapid_override(rapid_scale)

    def on_jog_override_value_changed (self, widget, data=None):
        # Read the speedcontrol pins to determine values. 
        jog_scale = self.gscreen.halcomp["jog_override.scaled-value"]
        jog_rate = (self.data.jog_rate_max*jog_scale)   
        self.data.jog_rate = jog_rate   
        self.emc.max_velocity(self.data.jog_rate)
           
########################################################################
# View Buttons
########################################################################

    def on_btn_zoom_plus_clicked(self,widget,data=None):
        self.widgets.gremlin.zoom_in()
        
    def on_btn_zoom_minus_clicked(self,widget):
        self.widgets.gremlin.zoom_out()

    def on_btn_pan_up_clicked(self,widget):
        self.data.graphic_ypos = self.data.graphic_ypos-8
        self.widgets.gremlin.pan(self.data.graphic_xpos,self.data.graphic_ypos)

    def on_btn_pan_down_clicked(self,widget):
        self.data.graphic_ypos = self.data.graphic_ypos+8
        self.widgets.gremlin.pan(self.data.graphic_xpos,self.data.graphic_ypos) 

    def on_btn_pan_right_clicked(self,widget):
        self.data.graphic_xpos = self.data.graphic_xpos+8
        self.widgets.gremlin.pan(self.data.graphic_xpos,self.data.graphic_ypos)

    def on_btn_pan_left_clicked(self,widget):
        self.data.graphic_xpos = self.data.graphic_xpos-8
        self.widgets.gremlin.pan(self.data.graphic_xpos,self.data.graphic_ypos)

    def on_btn_clear_view_clicked(self,widget):
        self.widgets.gremlin.clear_live_plotter()

    def on_tbtn_show_offsets_toggled(self,widget):
        if self.widgets.tbtn_show_offsets.get_active():
            self.widgets.gremlin.show_offsets = 1
        else:
            self.widgets.gremlin.show_offsets = 0       
            
    def on_spin_btn_grid_value_changed(self,widget):
        """ Function to set grid size of gremlin, and record it in the 
        preference file """
        data = widget.get_value()
        self.gscreen.data.grid_size = data
        self.widgets.gremlin.set_property('grid_size', data)
        self.gscreen.prefs.putpref('grid_size', data, float)
        
        
########################################################################
# Program Option Buttons
########################################################################

# WORKLIGHT, COOLANT, HSSC use HAL pins

    # function to set the optional stop to true for auto mode
    def on_tbtn_optional_stop_toggled (self,widget,data=None):
        op_stop = widget.get_active()
        self.command.set_optional_stop(op_stop)
        self.gscreen.prefs.putpref("opstop",op_stop)
        #print "on_tbtn_optional_stop_toggled() HAL pin value: %s" %(str(widget.hal_pin.get()))

    # function to set the block delete option
    def on_tbtn_block_delete_toggled(self,widget,data=None):
        op_block_delete = widget.get_active()
        self.command.set_block_delete(op_block_delete)
        self.gscreen.prefs.putpref("blockdel", op_block_delete)

    # function to set the feed and rapid overrides to a minimum value 
    def on_tbtn_dryrun_toggled(self,widget):
        # first we need to check the values of the overrides
        current_feed_override_value = self.widgets.feed_override.get_value()
        current_rapid_override_value = self.widgets.rapid_override.get_value()
        #print "current feed override value = %f" % current_feed_override_value
        #print "current rapid override value =%f" % current_rapid_override_value 
            
        if self.widgets.tbtn_dryrun.get_active():
            self.widgets.rapid_override.set_value(float(5.0))
            self.widgets.feed_override.set_value(float(5.0))
            self.widgets.spindle_override.set_value(float(60.0))
                    
        else:
            self.widgets.rapid_override.set_value(float(100.0))
            self.widgets.feed_override.set_value(float(100.0))
            self.widgets.spindle_override.set_value(float(100.0))
     
    # USER is responsible for closing keyboard when finished
    def on_btn_keyboard_clicked(self,widget,data=None):
        
        if  self.status.interp_state == linuxcnc.INTERP_IDLE:
            self.launch_keyboard(self)
        
        else:
            # throw up a warning dialog 
            message = _("INTERPRETER IS BUSY")
            self.gscreen.warning_dialog(message, True) 
        
        
    def launch_keyboard(self,widget,args="",x="",y=""):
        p = subprocess.Popen(["onboard"])
        pid = p.pid
        print "pid:",pid

        if self.status.task_mode == linuxcnc.MODE_MDI:
            self.widgets.hal_mdihistory.entry.grab_focus()

        elif self.status.task_mode == linuxcnc.MODE_AUTO:
            self.widgets.gcode_view.grab_focus()

        elif self.status.task_mode == linuxcnc.MODE_MANUAL:
            pass
    
        else:
            # unknown state 
            p.kill()
                    
########################################################################
# Turret Section
########################################################################
        
    def on_touch_off_x_button_clicked(self,widget):        
        axis = "X"
        # Use gscreens launch_numerical_input callback to launch an entry dialog
        #                                    ("custom callback",userdata, userdata2,title)
        self.gscreen.launch_numerical_input("on_x_offset_origin_entry_return",axis,None,"TOUCH OFF %s AXIS" % axis)

    def on_touch_off_z_button_clicked(self,widget):        
        axis = "Z"
        self.gscreen.launch_numerical_input("on_z_offset_origin_entry_return",axis,None,"TOUCH OFF %s AXIS" % axis)


    def on_x_offset_origin_entry_return(self,widget,result,calc,axis,userdata2):
        if result == gtk.RESPONSE_ACCEPT:
            value = calc.get_value()
            if value == None:
                value = 0.0
            else:
                axis = "x"
                 #retrieve the current tool number
                self.status.poll()
                current_tool = int(abs(self.status.tool_in_spindle))
                #set_tool_touchoff(tool,axis,value) 
                self.gstat.set_tool_touchoff(current_tool,axis,value)       
        widget.destroy()
        self.data.entry_dialog = None

    def on_z_offset_origin_entry_return(self,widget,result,calc,axis,userdata2):
        if result == gtk.RESPONSE_ACCEPT:
            value = calc.get_value()
            if value == None:
                value = 0.0
            else:
                axis = "z"
                #retrieve the current tool number
                self.status.poll()
                current_tool = int(abs(self.status.tool_in_spindle))
                #set_tool_touchoff(tool,axis,value) 
                self.gstat.set_tool_touchoff(current_tool,axis,value)
        widget.destroy()
        self.data.entry_dialog = None

    def on_cbox_turret_changed(self,combobox, data=None):
        print "combobox float value = %f" % (combobox.hal_pin_f.get()) 

    def on_btn_index_tool_clicked(self, widget):

        if self.status.task_mode != linuxcnc.MODE_MDI:
            message = _("Switch to MDI mode before changing tool")
            self.gscreen.warning_dialog(message,True)
        
        else: 
            self.ok_for_mdi_cmd()
            self.status.poll()
            current_tool = int(abs(self.status.tool_in_spindle))
            request_tool = int(abs(self.widgets.cbox_turret.hal_pin_f.get()))
            
            if current_tool == request_tool:
                # do nothing
                return
            
            else:
                # change tools
                self.gscreen.halcomp["manual-tool-change"] = True
                self.ok_for_mdi_cmd()
                self.command.mdi(("M6 T%s" % request_tool))
                self.command.wait_complete() 
                self.gscreen.halcomp["manual-tool-change"] = False

     
    def on_man_tool_change_mdi_command_start(self,widget):
        # set the manual tool change pin that we created true to signal
        # that we do not want to apply the fanuc style tool change
        self.gscreen.halcomp["manual-tool-change"] = True    

    def on_man_tool_change_mdi_command_stop(self,widget):
        # turn off the manual tool change pin 
        self.gscreen.halcomp["manual-tool-change"] = False    
        
########################################################################
# FILE EDITOR
########################################################################

    def on_button_load_clicked(self,widget, data=None):
        # this needs to happen after the file is loaded or preferrably by reacting to a halpin change
        print self.data.file      

    def on_tbtn_edit_gcode_toggled(self,widget,data=None):
        state = self.widgets.tbtn_edit_gcode.get_active()
        if not state:
            if self.widgets.gcode_view.buf.get_modified():
                    dialog = gtk.MessageDialog(self.widgets.window1,
                       gtk.DIALOG_DESTROY_WITH_PARENT,
                       gtk.MESSAGE_QUESTION, gtk.BUTTONS_YES_NO,"You edited the File. save edits?\n Choosing No will erase the edits.")
                    dialog.show_all()
                    result = dialog.run()
                    dialog.destroy()
                    if result == gtk.RESPONSE_YES:
                        self.widgets.vcp_action_saveas1.emit("activate")
                    else:
                        self.widgets.gcode_view.load_file()
        if state:
            self.launch_keyboard(self)
            self.widgets.search_box.show()
        else:
            self.widgets.search_box.hide()

    # convience function to check the parameter [5399] input timer time out status.
    # [5399] is a read only parameter and can only be reset by closing and restarting linuxcnc
    # once [5399]=True all subsequent m-codes will fail.
    def on_btn_mcode_reset_clicked(self,widget,data=None):
        self.status.poll()
        #print "value of input_timeout = " , self.status.input_timeout


########################################################################    
# Functions called every 100ms and by Halpin changes
######################################################################## 

    # Convience function to update the whole screen every 100ms
    def update_all(self):
        self.status.poll()
        self.update_file_label()
        self.update_crt_dro()
        self.update_mpg_scale()
        self.update_mode_leds()
        self.update_jog_controls()
        self.clock()
        self.update_axis_leds()   
                
    def clock(self):
        self.widgets.entry_clock.set_text(strftime("%H:%M:%S"))

 
    def update_jog_controls(self):
        # continious jogging
        if self.jog_increment == 0:
            self.widgets.man_button_box.show()
            self.widgets.axis_selection_box.hide()
            if self.widgets.tbtn_activate_jog.get_active():
                self.widgets.led_joystick_active.set_active(True)
                self.gscreen.halcomp["mpg-active"] = False
                
            else:
                self.widgets.led_joystick_active.set_active(False)
                self.gscreen.halcomp["mpg-active"] = False             
        
        # incremental jogging                    
        else:
            self.widgets.man_button_box.hide()
            self.widgets.axis_selection_box.show()
            if self.widgets.tbtn_activate_jog.get_active():
                self.widgets.led_joystick_active.set_active(False)
                self.gscreen.halcomp["mpg-active"] = True
                
            else:
                self.widgets.led_joystick_active.set_active(False)
                self.gscreen.halcomp["mpg-active"] = False   
                             
    def update_mode_leds(self):        
        if self.status.task_mode == linuxcnc.MODE_MANUAL:
            self.widgets.led_manual.set_active(True)
            self.widgets.led_mdi.set_active(False)
            self.widgets.led_auto.set_active(False)
            
        if self.status.task_mode == linuxcnc.MODE_MDI:
            self.widgets.led_manual.set_active(False)
            self.widgets.led_mdi.set_active(True)
            self.widgets.led_auto.set_active(False)         
        
        if self.status.task_mode == linuxcnc.MODE_AUTO:
            self.widgets.led_manual.set_active(False)
            self.widgets.led_mdi.set_active(False)
            self.widgets.led_auto.set_active(True)        
    
    def update_lbl_set_rpm(self):
        if "G96" in self.data.active_gcodes:
            self.widgets.lbl_set_rpm.set_text("Set CSS")
        if "G97" in self.data.active_gcodes:
            self.widgets.lbl_set_rpm.set_text("Set RPM")

    def update_jog_velocity_label(self):
		#poll the status channel
        self.status.poll()
        # max velocity is based on max machine units/min and the max velocity scale
        velocity = self.data.jog_rate
        
        if self.data.dro_units == self.data._MM:
            text = _("%4.2f mm/min")% (velocity*25.4)
        else:
            text = _("%3.2f IPM")% (velocity)
        self.widgets.jog_velocity_label.set_text(text)

    def update_file_label(self):
        #ideally this would be updated by a hal signal value changed event not updated every 100 ms        
        filename = self.data.file
        temp = os.path.split(filename)
        #print temp        
        var = (os.path.basename(temp[0]), temp[1])
        #print (var)
        self.widgets.file_label.set_text(temp[1])

    # Automatically update the crt dro and gremlin widget to show either radius/diameter 
    # and units based on the active gcodes held in gscreen's data class.
    # Function also sets the units for the jog increments so that the machine will 
    # jog incrementally based on G20|G21 being active. 
    # example: if combobox = 0.1000, dia mode on, units = mm mpg will change the diameter by 0.1 mm
    # crt hal_dro widgets,
    #       - x_rel_dro, z_rel_dro
    #       - x_abs_dro, z_abs_dro
    #       - x_dtg_dro, z_dtg_dro
    # gremlin widget called gremlin

    def update_crt_dro(self):
        self.active_units()
        self.active_diameter_mode()
        
        
    def active_units(self):
        # Metric
        if "G21" in self.data.active_gcodes: 
            self.jog_increment_units = 1
            self.data.dro_units = 1
            self.widgets.x_rel_dro.set_property("display_units_mm",True)            
            self.widgets.x_abs_dro.set_property("display_units_mm",True) 
            self.widgets.x_dtg_dro.set_property("display_units_mm",True)
            self.widgets.z_rel_dro.set_property("display_units_mm",True)            
            self.widgets.z_abs_dro.set_property("display_units_mm",True) 
            self.widgets.z_dtg_dro.set_property("display_units_mm",True)
            self.widgets.gremlin.set_property("metric_units", True)
            self.widgets.label_units.set_label("UNITS: MM")
 
        # Imperial 
        if "G20" in self.data.active_gcodes: 
            self.jog_increment_units = 0
            self.data.dro_units = 0                   
            self.widgets.x_rel_dro.set_property("display_units_mm",False)            
            self.widgets.x_abs_dro.set_property("display_units_mm",False) 
            self.widgets.x_dtg_dro.set_property("display_units_mm",False)
            self.widgets.z_rel_dro.set_property("display_units_mm",False)            
            self.widgets.z_abs_dro.set_property("display_units_mm",False) 
            self.widgets.z_dtg_dro.set_property("display_units_mm",False)  
            self.widgets.gremlin.set_property("metric_units", False)
            self.widgets.label_units.set_label("UNITS: INCH")

    def active_diameter_mode(self):
        # Diameter Mode  
        if "G7" in self.data.active_gcodes:
            self.data.diameter_mode = 1
            self.widgets.x_rel_dro.set_property("diameter", True) 
            self.widgets.x_abs_dro.set_property("diameter", True) 
            self.widgets.x_dtg_dro.set_property("diameter", True)                       
            self.widgets.gremlin.set_property("show_lathe_radius", False)
            self.widgets.label_dia.set_label("DIAMETER")

        # Radius Mode
        if "G8" in self.data.active_gcodes: 
            self.data.diameter_mode = 0
            self.widgets.x_rel_dro.set_property("diameter", False) 
            self.widgets.x_abs_dro.set_property("diameter", False) 
            self.widgets.x_dtg_dro.set_property("diameter", False)                         
            self.widgets.gremlin.set_property("show_lathe_radius", True)
            self.widgets.label_dia.set_label("RADIUS")      


    def update_mpg_scale(self):
        # we want lathezy to set the scale of the jog increments for the mpg wheel 
        # based on  - G20/G21 (taken care of with update_crt_dro)
        #           - G07/G08 (taken care of with update_crt_dro
        #           - the joint/axis selected, 
        #           - assumes imperial as default
        # update only if the tbtn_activate_jog is active
        if self.widgets.tbtn_activate_jog.get_active() == True:
            # adjust the increments for either radius or diameter mode
            if self.data.diameter_mode == 0:
                joint0_increment = self.jog_increment
                #print "jog increment = %f radius mode"  % joint0_increment              
                self.gscreen.halcomp["joint0-jog-inc-out"] = joint0_increment 

            elif self.data.diameter_mode == 1:
                joint0_increment = (self.jog_increment/2) 
                #print " jog increment = %f diameter mode" % joint0_increment
                self.gscreen.halcomp["joint0-jog-inc-out"] = joint0_increment 

            if self.active_joint == 1:
                joint1_increment = self.jog_increment
                #print " z axis jog increment = %f" % joint1_increment
                self.gscreen.halcomp["joint1-jog-inc-out"] = joint1_increment

    def update_axis_leds(self):
        if self.widgets.select_xaxis_button.get_active():
            self.widgets.led_xaxis_selected.set_active(True)    
            self.widgets.led_zaxis_selected.set_active(False)
        
        if self.widgets.select_zaxis_button.get_active():
            self.widgets.led_xaxis_selected.set_active(False)    
            self.widgets.led_zaxis_selected.set_active(True)


# Callbacks based on halpin changes

    def _update_jog_pins(self):
        active_jog_flag = self.active_jog_flag         
        # if the jog button is on then we need to turn on the selected axis
        # and the leds
        if active_jog_flag == 1 :
            if self.active_joint == 0:
                self.gscreen.halcomp["joint0-jog-enable-out"] = True
                self.gscreen.halcomp["joint1-jog-enable-out"] = False
            if self.active_joint == 1:
                # print " flag = 1,, joint = 1"
                self.gscreen.halcomp["joint0-jog-enable-out"] = False
                self.gscreen.halcomp["joint1-jog-enable-out"] = True  
                                       
        # otherwise we disable both pins
        else:
            self.gscreen.halcomp["joint0-jog-enable-out"] = False
            self.gscreen.halcomp["joint1-jog-enable-out"] = False              



    def _set_spindle(self,command):
        self.status.poll()
        if self.status.task_state == linuxcnc.STATE_ESTOP:
            return
        if self.status.task_mode != linuxcnc.MODE_MANUAL:
            # throw up a warning daialog to tell the user to switch to manual mode
            self.gscreen.warning_dialog("SWITCH TO MANUAL MODE", True)
        
         # test to see what command we have recieved
        #print "spindle command recieved %s" % command
        #print "rpm requested = %f" % self.spindle_rpm_request
        rpm = self.spindle_rpm_request
        rpm_override = self.status.spindle[0]['override']
        try:
            rpm_out = rpm
        except:
            rpm_out = 0
       
        if command =="stop":
            self.command.spindle(0)
        elif command =="forward":
            self.command.spindle(1,rpm_out)
        elif command =="reverse":
            self.command.spindle(-1,rpm_out)
        else:
            print (_("Something went wrong .... oh shitttttttttt!"))

    def override_limits_value_changed(self,hal_object):
        
        #if self.status.task_mode == linuxcnc.MODE_MANUAL:    
        if self.status.task_mode == linuxcnc.MODE_MANUAL:
            if self.gscreen.halcomp["override-limits"] is True:
                print "Override Limits ON"
                self.emc.override_limits(1)
                self.widgets.led_ignore_limits.set_active(True)
        
            if self.gscreen.halcomp["override-limits"] is False:
                print " override limits OFF"
                self.emc.override_limits(0)
                self.widgets.led_ignore_limits.set_active(False)
                      
        else:
            pass

    # Not sure what is going on here. Seem useless...

    def x_ferror_value_changed(self,hal_object):
        if self.gscreen.halcomp["x-ferror"] is True:
            print "X following error is ON"
        if self.gscreen.halcomp["x-ferror"] is False:
            print "X following error is OFF"

    def z_ferror_value_changed(self,hal_object):
        if self.gscreen.halcomp["z-ferror"] is True:
            print "Z following error is ON"
        if self.gscreen.halcomp["z-ferror"] is False:
            print "Z following error is OFF"




                    
########################################################################
# We don't want Gscreen to initialize it's regular widgets because this custom
# screen doesn't have most of them. However, we do want to use some of the simpler 
# ones 
######################################################################## 

    def initialize_widgets(self):
        self.gscreen.init_show_windows()
        self.gscreen.init_embeded_terminal()
        self.gscreen.init_dynamic_tabs()
        self.gscreen.init_statusbar()
        self.gscreen.init_tooleditor()
        self.gscreen.init_themes()        
        self.gscreen.init_control_pins()
        #btn_mode
        self.init_mode()
        
        # set the initial view
        self.init_gremlin()

        # manual spindle controls
        self.init_manual_spindle_controls()
        
        #btn_optional_stop
        optional_stop = self.gscreen.prefs.getpref( "opstop", False, bool )
        self.widgets.tbtn_optional_stop.set_active( optional_stop )
        self.command.set_optional_stop( optional_stop )

        #tbtn_block_delete
        op_block_delete = self.gscreen.prefs.getpref("blockdel", False, bool)
        self.widgets.tbtn_block_delete.set_active(op_block_delete)
        self.command.set_block_delete(op_block_delete)

        # initial state of the edit_gcode_button
        self.init_edit_gcode()

    def initialize_preferences(self):	
        self.gscreen.init_general_pref()
        self.gscreen.init_theme_pref()			
		# get the values for the sliders
        self.jog_rate = float(self.gscreen.inifile.find("TRAJ", "DEFAULT_LINEAR_VELOCITY"))
        self.jog_rate_max = float(self.gscreen.inifile.find("TRAJ", "MAX_LINEAR_VELOCITY"))       
        self.data.feed_override_max = self.gscreen.inifile.find("DISPLAY", "MAX_FEED_OVERRIDE")      
        self.data.spindle_override_max = self.gscreen.inifile.find("DISPLAY", "MAX_SPINDLE_OVERRIDE")
        self.data.spindle_override_min = self.gscreen.inifile.find("DISPLAY", "MIN_SPINDLE_OVERRIDE")
        self.data.rapid_override_max = (self.gscreen.inifile.find("DISPLAY", "MAX_RAPID_OVERRIDE"))       
        # get the min/max values for the spindle
        self.spindle_max_rpm = int(self.gscreen.inifile.find("SPINDLE", "MAX_RPM")) 
        self.spindle_min_rpm = int(self.gscreen.inifile.find("SPINDLE", "MIN_RPM"))
        
        # set the default value for the jog_override slider (by default range = 100 %)
        # the scale is weird since the speed control widget has a default of 60
        #default_jog_slider_value = (self.jog_rate/self.jog_rate_max)*100
        #self.widgets.jog_override.set_value(float(default_jog_slider_value))
                              
        # set the min/max value of the overrides        
        self.widgets.feed_override.set_property("max",float(self.data.feed_override_max)*100)
        self.widgets.spindle_override.set_property("min",float(self.data.spindle_override_min)*100)
        self.widgets.spindle_override.set_property("max",float(self.data.spindle_override_max)*100)
                
        # set the increments of the speedcontrol sliders to increase/decrease per button press
        # for some reason glade doesn't seem to acknowledge the increment parameter changes ... 
        self.widgets.feed_override.set_property("increment",float(5.0))
        self.widgets.jog_override.set_property("increment",float(5.0))
        self.widgets.spindle_override.set_property("increment",float(5.0))
        self.widgets.rapid_override.set_property("increment",float(5.0))
        
        # get the values for the homing routine timeout
        #self.joint0_timeout = float(self.gscreen.inifile.find("JOINT_0", "HOME_TIMEOUT"))
        #self.joint1_timeout = float(self.gscreen.inifile.find("JOINT_1", "HOME_TIMEOUT"))
        
        self.gscreen.data.grid_size = self.gscreen.prefs.getpref('grid_size', 1.0 , float)
        
        

    def init_mode(self):
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.wait_complete()
        self.hide_frames()
        self.widgets.notebook1.set_current_page(0)
        self.widgets.tbtn_activate_jog.set_active(False)

    def init_gremlin(self):
        """ Initial settings of the gremlin plot """
        self.widgets.gremlin.set_property('view','Y2')
        self.widgets.spin_btn_grid.set_value(self.gscreen.data.grid_size)
        self.widgets.gremlin.grid_size = self.gscreen.data.grid_size       
             
    def init_edit_gcode(self):
        self.widgets.tbtn_edit_gcode.set_active(False)
        self.widgets.search_box.hide()        

    def init_manual_spindle_controls(self):
        # Set the requested spindle speed equal to the preset value
        spindle_preset = self.widgets.spindle_start_rpm.get_value()
        print ("Spindle Preset =" , spindle_preset)
        self.spindle_rpm_request = spindle_preset
        
        # Set the label
        text = _("%0.f") % spindle_preset
        self.widgets.lbl_set_spindle.set_text(text)
        
        # See if the manual spindle controls should be displayed or not
        if self.widgets.cbtn_show_man_spindle.get_active():
            self.widgets.man_spindle_frame.hide()
            
        else:
            self.widgets.man_spindle_frame.show()
           
    # Initialize hal-pins that we need access to from gscreen 
    def initialize_pins(self):

        self.gscreen.halcomp.newpin("joint0-jog-enable-out", hal.HAL_BIT, hal.HAL_OUT)
        self.gscreen.halcomp.newpin("joint1-jog-enable-out", hal.HAL_BIT, hal.HAL_OUT)
        # jog-increment pins
        self.gscreen.halcomp.newpin("joint0-jog-inc-out", hal.HAL_FLOAT, hal.HAL_OUT)
        self.gscreen.halcomp.newpin("joint1-jog-inc-out", hal.HAL_FLOAT, hal.HAL_OUT)
        
        # HSSC pins
        self.gscreen.halcomp.newpin("hssc-period", hal.HAL_FLOAT, hal.HAL_OUT)
        self.gscreen.halcomp.newpin("hssc-amplitude", hal.HAL_FLOAT, hal.HAL_OUT)
        self.gscreen.halcomp.newpin("hssc-interval", hal.HAL_FLOAT, hal.HAL_OUT)
        self.gscreen.halcomp.newpin("hssc-on", hal.HAL_BIT, hal.HAL_OUT)
        
        # MPG pins
        self.gscreen.halcomp.newpin("mpg-active", hal.HAL_BIT, hal.HAL_OUT)
        
        # this is how we make a pin that can be connected to a callback 
        pin =  self.gscreen.halcomp.newpin("override-limits", hal.HAL_BIT, hal.HAL_IN)
        hal_glib.GPin(pin).connect("value_changed", self.override_limits_value_changed)

        # Again, no idea what this is needed for
        # These pins are used to stop a running program gently in the event of a 
        # following error. Can be used as an alternative to joint.X.amp-fault-in 
        # which aborts with an estop
        pin =  self.gscreen.halcomp.newpin("x-ferror", hal.HAL_BIT, hal.HAL_IN)
        hal_glib.GPin(pin).connect("value_changed", self.x_ferror_value_changed)        
        pin =  self.gscreen.halcomp.newpin("z-ferror", hal.HAL_BIT, hal.HAL_IN)
        hal_glib.GPin(pin).connect("value_changed", self.z_ferror_value_changed)

    # every 100 milli seconds these functions get called
    def periodic(self):    
        self.gscreen.update_active_gcodes()
        self.gscreen.update_active_mcodes() 
        self.gscreen.update_tool_label()
        self.gscreen.update_feed_speed_label()   
        self.update_all()
        self._update_jog_pins()
        return True
        

# standard handler call
def get_handlers(halcomp,builder,useropts,gscreen):
     return [HandlerClass(halcomp,builder,useropts,gscreen)]




