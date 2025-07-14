# motoeus motor control via tview
python3 -m moteus_gui.tview --devices=1
 Setting an option:
1> conf set servopos.position_min -100.0
1> conf write 

Making the motor spin at 4 turns / s:
1> d pos nan 4.0 nan

Making the motor spin the other way (cc)
1> d pos nan -4.0 nan

Stopping the motor:
1> d stop


Use accel limit and voltage limit to control the speed. 0.0 is the velocity after going to the position. 
 d pos 25.0 0.0 2.2 v2.0 a1.5