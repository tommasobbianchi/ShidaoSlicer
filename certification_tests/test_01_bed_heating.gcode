; CERTIFICATION TEST 1.1: Bed Heating
; Test riscaldamento letto a 80°C per PETG

M117 Test 1.1: Bed Heating
M140 S80       ; Set bed temperature to 80°C
M190 S80       ; Wait for bed to reach temperature
M117 Bed at 80C - holding
G4 P10000      ; Hold for 10 seconds
M140 S0        ; Turn off bed
M117 Test 1.1 COMPLETE
