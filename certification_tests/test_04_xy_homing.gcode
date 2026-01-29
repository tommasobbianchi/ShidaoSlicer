; CERTIFICATION TEST 2.1: XY Homing
; Test homing assi X e Y

M117 Test 2.1: XY Homing
G28 X Y        ; Home X and Y axes
M117 XY homed - moving to center
G1 X100 Y100 F3000  ; Move to center position
G4 P2000       ; Pause 2 seconds
M117 Returning to home
G28 X Y        ; Home again for repeatability test
M117 Test 2.1 COMPLETE
