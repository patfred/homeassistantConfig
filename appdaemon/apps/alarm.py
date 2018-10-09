import appdaemon.appapi as appapi
import os
import json
import datetime
      
class alarmclock(appapi.AppDaemon):
  
  # Created an initialization file just to mimic AD it's called from __init__
  def initialize(self):
      self.log("in initialize")
      # initialize variables
      self.filename=self.config["app_dir"] + "/" + "alarmclock.cfg"
      self.log("filename= {}".format(self.filename))
      self.alarms={}
      self.alarmhandles={}
      self.done=False
      self.loadalarms()   # load alarms from disk
      self.displayalarms() # display the alarms to the log just for grins

      # setup listeners
      self.listen_state(self.handle_input_slider, "input_slider", "home assistant")
      self.listen_state(self.handle_input_boolean, "input_boolean", "home assistant")
      self.listen_event(self.restartHA,"ha_started")

      # setup initial values in HA based on saved alarm settings
      self.updateHA()

  # handle HA restart
  def restartHA(self,event_name,data,kwargs):
      self.log("HA event {}".format(event_name))
      self.updateHA()

  # update initial values in HA after HA restart or AD restart
  def updateHA(self):
      for room in self.alarms:
        # set input sliders for hour and minutes
        self.select_value("input_slider.{}alarmhour".format(room),str(self.parse_time(self.alarms[room]["time"]+":00").hour))
        self.select_value("input_slider.{}alarmminutes".format(room),str(self.parse_time(self.alarms[room]["time"]+":00").minute))

        # set input boolean for alarm status
        if self.alarms[room]["active"] == "on" :
          self.turn_on("input_boolean.{}alarm".format(room))
        else:
          self.turn_off("input_boolean.{}alarm".format(room))

        # since this is being done as the result of either HA or AD restarting lets make sure all alarms schedules are in place
        self.schedulealarm(room)


  # Save alarms file to a json file
  def savealarms(self):
      self.log("in savealarms")
      fout=open(self.filename,"wt")
      self.displayalarms()
      json.dump(self.alarms,fout)
      fout.close()

  # Load alarms from the json file
  def loadalarms(self):
     self.log("checking on file {}".format(self.filename))
     if os.path.exists(self.filename) : 
         # file exists so open and load data
         fout=open(self.filename,"rt")
         self.alarms=json.load(fout)
         fout.close()
         # Set values on input sliders and activation switch in HA
     else:
         # file does not exist so initialize alarms
         self.alarms={}
      
  # add alarm to dictionary
  def addalarm(self,room,timeincrement,value):
      #initialize values for alarm
      self.attributes={"time":"0:0","active":"False"}
      self.alarms[room]=self.attributes
      # now just run update alarm with the new values
      self.updatealarm(room,timeincrement,value)
            
  # update existing alarm in dictionary
  def updatealarm(self,room,timeincrement,value):
      timevalue=self.alarms[room]["time"]
      savehour=timevalue[:timevalue.find(":")]
      saveminute=timevalue[timevalue.find(":")+1:]
      if timeincrement=="hour" : # handle hour input slider
         savehour=str(value)
      else :  # else it has to be the minute input slider so handle it
          saveminute=str(value)
      timevalue=savehour + ":" + saveminute
      self.alarms[room]["time"]=timevalue
      self.displayalarm(room)

  # input boolean for turning the alarm on or off
  def handle_input_boolean(self, entity, attribute, old, new, kwargs):
       self.log("in handle_input_boolean")
       room=entity[entity.find(".")+1:entity.find("alarm")].lower()
       if room in ['sam','charlie','master','guest']:
         self.alarms[room]["active"]=new
         self.log("room {} active set to {}".format(room,new))
         self.schedulealarm(room)
         self.savealarms()

  # This would be the callback function when an input_slider is changed
  def handle_input_slider(self, entity, attribute, old, new, kwargs):
       self.log("in handle_input_slider")
       room=entity[entity.find(".")+1:entity.find("alarm")].lower()
       timeincrement=entity[entity.find("alarm")+5:].lower()
       # the input slider keeps returning a float but we need an integer so convert string to float and float to integer.
       x=int(float(new))
       # manage variable range
       if timeincrement=="hour":
           maxvalue=23
       else :
           maxvalue=59

       if (x>=0) and (x <= maxvalue) :
          self.log("value good")
       if room in self.alarms :
          self.updatealarm(room,timeincrement,x)
       else :
          self.addalarm(room,timeincrement,x)

       # schedule and save the alarms
       self.schedulealarm(room)
       self.savealarms()

  def schedulealarm(self,room):
    self.log("In schedulealarm - {}".format(room))
    # if the alarm is active then schedule it
    if self.alarms[room]["active"] == "on":
      # make a valid time string
      timestr=self.alarms[room]["time"]+":00"
      alarmtime=self.parse_time(timestr)
      # if there isn't a current alarmhandle the just schedule the alarm, else cancel the current alarmhandle and create a new one
      if self.alarmhandles.get(room,"")=="":
        self.log("handle was empty")
        self.alarmhandles[room]=self.run_daily(self.alarm_lights,alarmtime,arg1=room)
      else:
        # an alarm handle already existed so delete it and create a new one with the corrected time.
        self.log("Handle already existed {}".format(self.alarmhandles[room]))
        self.cancel_timer(self.alarmhandles[room])
        handle=self.run_daily(self.alarm_lights,alarmtime,arg1=room)
        self.alarmhandles[room]=handle
    else:
      self.log("alarm for room {} is in state {}".format(room,self.alarms[room]["active"]))
      # the alarm is not on in this room, so if there is a current schedule for it, remove it.
      if room in self.alarmhandles :
        self.log("removing existing alarm from schedule")
        self.cancel_timer(self.alarmhandles[room])

  # right now, we only have one light in each room to turn on, and they are named consistently
  # in the future, there should be a list of devices to turn on in response to an alarm
  # also provide method of selecting days to run alarm possibly tied into calendar...
  def alarm_lights(self,kwargs):
    if datetime.datetime.today().weekday() < 5:
      self.turn_on("switch.{}_light_switch".format(kwargs["arg1"]))
      self.log("Lights should have been turned on switch.{}_light_switch".format(kwargs["arg1"]))
    else:
      self.log("Lights not turned on because its the weekend")

  # Display single alarm data
  def displayalarm(self,room):
      self.log("Room={}".format(room))
      self.log("Attribut  Value")
      for alarmattribute,value in self.alarms[room].items():
            self.log("{}{}".format(alarmattribute.ljust(10),value))
      self.log(" ")

  # Display all alarms by looping through all rooms and calling displayalarm above.
  def displayalarms(self):
      self.log("Displaying all alarms")
      for room,alarmdict in self.alarms.items() :
        self.displayalarm(room)