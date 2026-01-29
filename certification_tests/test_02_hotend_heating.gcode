; CERTIFICATION TEST 1.2: Hotend Heating
; Test riscaldamento ugello a 235°C per PETG

M117 Test 1.2: Hotend Heating
M104 S235      ; Set hotend temperature to 235°C
M109 S235      ; Wait for hotend to reach temperature
M117 Hotend at 235C - holding
G4 P10000      ; Hold for 10 seconds
M104 S0        ; Turn off hotend
M117 Test 1.2 COMPLETE
