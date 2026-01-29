; CERTIFICATION TEST 3.3: Movement + Extrusion
; Test coordinated movement and extrusion

M117 Test 3.3: Move+Extrude
G28
M140 S80       ; Heat bed
M104 S235      ; Heat hotend
M190 S80       ; Wait for bed
M109 S235      ; Wait for hotend

M117 Drawing test line
G92 E0         ; Reset extruder
G1 Z0.5 F500   ; Lift to safe height
G1 X50 Y0.3 Z0.3 F3000  ; Move to start position
G1 X150 Y0.3 Z0.3 E5 F1500  ; Draw 100mm line with extrusion
M117 Line complete - retracting
G92 E0
G1 E-1.5 F1800 ; Retract
G1 Z10 F500    ; Lift

M104 S0        ; Cool down
M140 S0
M117 Test 3.3 COMPLETE
; VERIFY: Straight line, uniform width, good bed adhesion
