import linuxcnc
import emccanon
from interpreter import *
from stdglue import *
from util import lineno

# raises InterpreterException if execute() or read() fail
throw_exceptions = 1 

# HYD. Gear Change prolog; M36,M37,M39    
def spindle_run_inhibit(self,**words):
    # if in preview mode, do nothing 
    if self.task==0:
        return INTERP_OK
    try:
        self.status = linuxcnc.stat()
        self.status.poll()    
        print "start of gear change prolog"
        # spindle run inhibit
        spindle_status = self.params["_spindle_on"]
        print "spindle status:", spindle_status
        if spindle_status == 1:                 
            self.execute("M5", lineno())        
            self.execute("M66 P16 L3 Q5")       
            print "stop spindle command sent" 
        else:
            print"spindle stopped"        
        # zero speed
        # the spindle.0.at-speed pin must be connected to digital input 16
        self.status.poll()
        zero_speed_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(16,0)
        print "zero speed detect =" , zero_speed_status
        if zero_speed_status != 1:
                self.set_errormsg("spindle_run_inhibit error, spindle still running")
                return INTERP_ERROR        
        else:
            print "spindle_run_inhibit was successful"
            return INTERP_OK
        
    except InterpreterException,e:
        msg = "Danno look at this error : %d: '%s' - %s" % (e.line_number,e.line_text, e.error_message)
        self.set_errormsg(msg) # replace builtin error message
        print("%s" % msg)
        return INTERP_ERROR
    except:
        print "Unexpected error:", sys.exc_info()[0]
        raise        



def gear_shift_prolog(self,**words):
    print "start of gear shift prolog"
    # all we want to do here is determine which gear we are in and pass
    # it to m36.ngc
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw1_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(00,0)    
    lsw3_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(01,0)
    lsw4_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(02,0)
    
    # reset param 31 
    self.params[31] = abs(int(0))
    # neutral
    if lsw1_status == 1 :
        print "lsw1_status:",lsw1_status
        self.params[36] = 1.0
        # low    
    elif lsw3_status == 1:
        print "lsw3_status:",lsw3_status
        self.params[36] = 2.0
    # high
    elif lsw4_status == 1:
        print "lsw4_status:",lsw4_status        
        self.params[36] = 3.0
    # unknown state
    else:
        print "switch is in an indeterminate state"
        self.params[36] = 0.0
        
    return INTERP_OK

# A note about MXX epilogs: There is apparently no way to reference ini file 
# variables for motion in/out pins, see ngc procedures for the corresponding
# MXXX code. Therefore it is critical to make sure that you are checking the 
# correct pins

# Tailstock and Tail Sleeve epilogs
def m31_epilog(self,**words):
    print "Start of M31 epilog"
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw8_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(04,0)
    lsw10_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(06,0)
    print "Tailstock FWD lsw ",lsw8_status
    print "Tailsleeve FWD lsw ",lsw10_status   
    if lsw8_status != 1 or lsw10_status != 1:
        print "M31 Error"
        self.params[31] = abs(int(931))
        return INTERP_ERROR

    else:
        print "M31 Successful!"
        return INTERP_OK

def m32_epilog(self,**words):
    print "Start of M32 epilog"
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw9_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(05,0)
    lsw11_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(07,0)
    print "Tailstock REV lsw ",lsw9_status
    print "Tailsleeve FWD lsw ",lsw11_status   
    if lsw9_status != 1 or lsw11_status != 1:
        print "M32 Error"
        self.params[31] = abs(int(931))
        return INTERP_ERROR

    else:
        print "M32 Successful!"
        return INTERP_OK


# HYD. Gear Change epilogs M36/M37/M39      
def m36_epilog(self,**words):
    print "Start of M36 epilog"
    # look at the limit switch (lsw1 motion.digital.out-00) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw1_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(00,0)
    print "lsw1_status:",lsw1_status    
    if lsw1_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(936))
        return INTERP_ERROR

    else:
        print "M36 Successful!"
        return INTERP_OK

def m37_epilog(self,**words):
    print "start of m37 epilog"
    # look at the limit switch (lsw3 motion.digital.out-01) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw3_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(01,0)
    print "lsw3_status:",lsw3_status    
    if lsw3_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(937))
        return INTERP_ERROR

    else:
        print "M37 Successful!"
        return INTERP_OK

def m39_epilog(self,**words):
    print "start of m39 epilog"
    # look at the limit switch (lsw4 motion.digital.out-02) to see if the M-Code succeeded
    self.status = linuxcnc.stat()
    self.status.poll()
    lsw4_status = emccanon.GET_EXTERNAL_DIGITAL_INPUT(02,0)
    print "lsw4_status:",lsw4_status    
    if lsw4_status != 1:
        # if the m-code routine fails or times out we need to clean up gracefully.
        # pass the fault code to o<on_abort> using parameter 31
        # named parameters (even if they are gloabal) are not recognized at start up
        # numbered parameters are
        self.params[31] = abs(int(939))
        return INTERP_ERROR

    else:
        print "M39 Successful!"
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
    except Exception, e:
        self.set_errormsg("T%d/prepare_prolog: %s" % (int(words['t']), e))
        return INTERP_ERROR


########################################################################
# Harmonic Spindle Speed Control
########################################################################
# NOTE: DO NOT use HSSC while threading, it will mess things up .....

def M600_remap(self,**words):
    # determine what vaiables have been passed
    #for i in words:
    #    print("passing '%s' = %f") % (i, words[i]) 
        
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

    except Exception,e:
        self.set_errormsg("M600 HSSC: %s)" % (e))
        return INTERP_ERROR    
    return INTERP_OK

def M601_remap(self):
    # Turn off HSSC and reset the parameters to zero no matter what
    self.execute("M152")
