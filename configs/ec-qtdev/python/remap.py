import linuxcnc
import emccanon
from interpreter import *
from stdglue import *
from util import lineno
import sys



# raises InterpreterException if execute() or read() fail
throw_exceptions = 1 

# Method to index lathe tools using Fanuc style tool change
# T0101 calls tool 1 and applies offset 1 + Wear Offset 1 if it exists
# T0100 calls tool 1. No offsets are applied
def index_lathe_tool(self,**words):
    # only run this if we are really moving the machine
    # skip this if running task for the screen
    if not self.task:
        yield INTERP_OK
    try:
        # check there is a tool number from the Gcode
        cblock = self.blocks[self.remap_level]
        if not cblock.t_flag:
            self.set_errormsg("T requires a tool number")
            yield INTERP_ERROR
        tool_raw = int(cblock.t_number)

        # Interpret the raw tool number into tool and wear number
        if tool_raw <100:
            tool_raw=tool_raw*100
        tool = int(tool_raw/100)
        wear = 10000 + tool_raw % 100

        # uncomment for debugging
        print('***tool#',cblock.t_number,'toolraw:',tool_raw,'tool split:',tool,'wear split',wear)

        if tool:
            # check for tool number entry in tool file
            (status, pocket) = self.find_tool_pocket(tool)
            if status != INTERP_OK:
                self.set_errormsg("T%d: tool entry not found" % (tool))
                yield status
        else:
            tool = -1
            pocket = -1
            wear = -1
        self.params["tool"] = tool
        self.params["pocket"] = pocket
        self.params["wear"] =  wear
        try:
            self.hal_tool_comp['tool']= tool_raw
            self.hal_tool_comp['wear']= wear
        except:
            pass
        # index tool immediately to tool number
        self.selected_tool = int(self.params["tool"])
        self.selected_pocket = int(self.params["pocket"])
        emccanon.SELECT_TOOL(self.selected_tool)
        if self.selected_pocket < 0:
            self.set_errormsg("T0 not valid")
            yield INTERP_ERROR
        if self.cutter_comp_side:
            self.set_errormsg("Cannot change tools with cutter radius compensation on")
            yield INTERP_ERROR
        self.params["tool_in_spindle"] = self.current_tool
        self.params["selected_tool"] = self.selected_tool
        self.params["current_pocket"] = self.current_pocket
        self.params["selected_pocket"] = self.selected_pocket

        # change tool
        try:
            self.selected_pocket =  int(self.params["selected_pocket"])
            emccanon.CHANGE_TOOL()
            self.current_pocket = self.selected_pocket
            self.selected_pocket = -1
            self.selected_tool = -1
            # cause a sync()
            self.set_tool_parameters()
            self.toolchange_flag = True
        except:
            self.set_errormsg("T change aborted (return code %.1f)" % (self.return_value))
            yield INTERP_ERROR

        # if the tool offset/wear offset is specified, apply it
        try:
            if wear>10000:
                self.execute("g43 h%d"% tool)
                self.execute("g43.2 h%d"% wear)
            yield INTERP_OK
        
        except:
            self.set_errormsg("Tool change aborted - No wear %d entry found in tool table" %wear)
            yield INTERP_ERROR
    except:
        self.set_errormsg("Tool change aborted (return code %.1f)" % (self.return_value))
        yield INTERP_ERROR

########################################################################
# Harmonic Spindle Speed Control
########################################################################
# NOTE: DO NOT use HSSC while threading, it will mess things up

def M600_remap(self,**words):
    # determine what vaiables have been passed
    #for i in words:
    #    print("passing '%s' = %f") % (i, words[i]) 
    if self.task==0:
        return INTERP_OK
         
    try:
        cblock = self.blocks[self.remap_level]
        if not cblock.p_flag: 
            self.set_errormsg("HSSC requires a P value") 
            return INTERP_ERROR
        if not cblock.q_flag: 
            self.set_errormsg("HSSC requires a Q value") 
            return INTERP_ERROR            
        if not cblock.r_flag: 
            self.set_errormsg("HSSC requires a R value") 
            return INTERP_ERROR                    
        
        temp1 = float(cblock.p_number)
        temp2 = float(cblock.q_number)
        temp3 = float(cblock.r_number)
        
        # TODO; add conditions limiting P <= 25.5 and I =12.5
        
        # User Mcodes will only accept P and Q variables so we need M150 and M151
        # to set the parameters of HSSC in HAl 
        # M150 sets the period and the amplitude
        # M151 sets the interval and turns HSSC on
        # M152 turns HSSC off 
        self.execute("M150 P%f Q%f" % (temp1,temp2)) 
        self.execute("M151 P%f" % (temp3))     

    except Exception as e:
        self.set_errormsg("M600 HSSC: %s)" % (e))
        return INTERP_ERROR    
    return INTERP_OK

def M601_remap(self):
    # Turn off HSSC and reset the parameters to zero no matter what
    self.execute("M152")


########################################################################
# Spindle Run Inhibit
########################################################################

# HYD. Gear Change prolog; M36,M37,M39    
def spindle_run_inhibit(self,**words):
    # if in preview mode, do nothing 
    if self.task==0:
        return INTERP_OK
    try:
        self.status = linuxcnc.stat()
        self.status.poll()    
        print ("start of gear change prolog")
        # spindle run inhibit
        spindle_status = self.params["_spindle_on"]
        print ("spindle status:", spindle_status)
        if spindle_status == 1:                 
            self.execute("M5", lineno())        
            self.execute("M66 P16 L3 Q5")       
            print ("stop spindle command sent") 
        else:
            print ("spindle stopped")        
        # zero speed
        # the spindle.0.at-speed pin must be connected to digital input 16
        self.status.poll()
        zero_speed_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(16,0)
        print ("zero speed detect =" , zero_speed_status)
        if zero_speed_status != 1:
                self.set_errormsg("spindle_run_inhibit error, spindle still running")
                return INTERP_ERROR        
        else:
            print ("spindle_run_inhibit was successful")
            return INTERP_OK
        
    except InterpreterException as e:
        msg = "Danno look at this error : %d: '%s' - %s" % (e.line_number,e.line_text, e.error_message)
        self.set_errormsg(msg) # replace builtin error message
        print("%s" % msg)
        return INTERP_ERROR
    except:
        print ("Unexpected error:", sys.exc_info()[0])
        raise        

# HYD. Gear Change epilogs M36/M37/M39      
def m36_epilog(self,**words):
    print ("start of m36 epilog")
    # look at the limit switch (lsw1 motion.digital.out-00) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw1_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(00,0)
    print ("lsw1_status:",lsw1_status)    
    if lsw1_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(200))
        return INTERP_ERROR

    else:
        print ("M36 Successful!")
        return INTERP_OK

def m37_epilog(self,**words):
    print ("start of m37 epilog")
    # look at the limit switch (lsw3 motion.digital.out-01) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw1_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(1,0)
    print ("lsw1_status:",lsw1_status)    
    if lsw1_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(201))
        return INTERP_ERROR

    else:
        print ("M37 Successful!")
        return INTERP_OK

def m39_epilog(self,**words):
    print ("start of m39 epilog")
    # look at the limit switch (lsw4 motion.digital.out-02) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw1_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(2,0)
    print ("lsw1_status:",lsw1_status )   
    if lsw1_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(202))
        return INTERP_ERROR

    else:
        print ("M39 Successful!")
        return INTERP_OK




# Extract the T number into a parameter, but don't try anything else clever
def get_T_number(self,**words):
    try:
        cblock = self.blocks[self.remap_level]
        if not cblock.t_flag:
            self.set_errormsg("T requires a tool number")
            return INTERP_ERROR
        self.params["tool"] = cblock.t_number
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("T%d/prepare_prolog: %s" % (int(words['t']), e))
        return INTERP_ERROR



